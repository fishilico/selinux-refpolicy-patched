#!/usr/bin/env python
# -*- coding:UTF-8 -*-
# Copyright (C) 2014 Nicolas Iooss
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
"""
Parse .fc files and find those useful for the running system. This helps
deciding which modules to load when using the modular build of the policy

@author: Nicolas Iooss
@license: GPLv2
"""
import argparse
import glob
import os
import os.path
import sys

DEFAULT_POLICYPATH = os.path.join(os.path.dirname(__file__),
                                  os.path.pardir, 'policy')


class FilePatternParserError(Exception):

    def __init__(self, message):
        super(FilePatternParserError, self).__init__()
        self.message = message
        self.pattern = None


def parse_filepattern(pattern):
    """Build a syntax tree out of a string pattern for a file path"""
    # Use a state machine for each character
    is_backslashed = False
    is_in_charset = False
    current_buffer = ''
    stack = [[]]
    for cpat in str(pattern):
        if is_backslashed:
            current_buffer += cpat
            is_backslashed = False
        elif cpat == '\\':
            is_backslashed = True
        elif is_in_charset:
            if cpat == ']':
                if current_buffer:
                    if current_buffer[0] == '^':
                        stack[-1].append(('[^', current_buffer[1:]))
                    else:
                        stack[-1].append(('[', current_buffer))
                current_buffer = ''
                is_in_charset = False
            else:
                current_buffer += cpat
        elif cpat == '[':
            if current_buffer:
                stack[-1].append((None, current_buffer))
                current_buffer = ''
            is_in_charset = True
        elif cpat == '.':
            if current_buffer:
                stack[-1].append((None, current_buffer))
                current_buffer = ''
            stack[-1].append(('.', None))
        elif cpat == '(':
            if current_buffer:
                stack[-1].append((None, current_buffer))
                current_buffer = ''
            stack.append([])
        elif cpat == ')':
            if len(stack) == 1:
                raise FilePatternParserError("missing '('")
            if current_buffer:
                stack[-1].append((None, current_buffer))
                current_buffer = ''
            content = stack.pop()
            # If there has been a | in the content, fill it
            if len(stack[-1]) == 1 and stack[-1][0][0] == '|':
                stack.pop()
                content = [('|', content)]
            stack[-1].append(('(', content))
        elif cpat in '?*+':
            # Modifier affects the last character.
            # Right now, put everything on the stack, it'll be simplified later.
            if len(current_buffer) >= 2:
                stack[-1].append((None, current_buffer[:-1]))
                stack[-1].append((None, current_buffer[-1]))
            elif current_buffer:
                stack[-1].append((None, current_buffer))
            elif not stack[-1]:
                raise FilePatternParserError("nothing before '" + cpat + "'")
            current_buffer = ''
            # Change the last item of the stack
            stack[-1][-1] = (cpat, stack[-1][-1])
        elif cpat == '|':
            if current_buffer:
                stack[-1].append((None, current_buffer))
                current_buffer = ''
            # Add a level in the stack before the last, if it doesn't exist
            if len(stack) <= 2 or len(stack[-2]) < 1 or stack[-2][0][0] != '|':
                stack.insert(-1, [('|', None)])
        else:
            current_buffer += cpat

    if is_backslashed:
        raise FilePatternParserError("missing character after '\\'")
    if is_in_charset:
        raise FilePatternParserError("missing ']'")

    # Close opened things
    if current_buffer:
        stack[-1].append((None, current_buffer))
    if len(stack) == 2 and stack[0][0][0] == '|':
        return '|', stack[1]

    if len(stack) >= 2:
        raise FilePatternParserError("missing ')'")
    return stack[0]


def expand_syntree_node(node):
    """Expand one node in the syntax tree of a pattern"""
    if node[0] == '?':
        return '|', [(None, ''), expand_syntree_node(node[1])]
    elif node[0] == '[':
        char_range = node[1]
        char_range = char_range.replace('0-9', '0123456789')
        char_range = char_range.replace('a-z', 'abcdefghijklmnopqrstuvwxyz')
        char_range = char_range.replace('A-Z', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        return '|', [(None, c) for c in char_range]
    elif node[0] == '(':
        content = expand_syntax_tree(node[1])
        if len(content) == 1:
            return content[0]
        return '(', content
    elif node[0] == '|':
        return '|', [expand_syntree_node(subnode) for subnode in node[1]]
    return node


def expand_syntax_tree(tree):
    """Expand the syntax tree of a pattern to make it use less kinds of special symbols.

    NB: this function is recursive, with expand_syntree_node
    """
    for _ in range(10):
        # Expand each node
        result = []
        for node in tree:
            node = expand_syntree_node(node)

            # Destroy parenthesis
            if node[0] == '(':
                result += node[1]
            else:
                result.append(node)
        tree = result

        # 2nd pass, merge text
        result = []
        need_another_pass = False
        for node in tree:
            if not result:
                # Don't do anything with the first node
                result.append(node)
            elif node[0] is None and result[-1][0] is None:
                # Merge text and text
                result[-1] = (None, result[-1][1] + node[1])
            elif node[0] is None and result[-1][0] == '|':
                # Merge with alternatives, creating parenthesis at a higher level
                result[-1] = ('|', [('(', [x, node]) for x in result[-1][1]])
                need_another_pass = True
            elif node[0] == '|' and result[-1][0] is None:
                result[-1] = ('|', [('(', [result[-1], x]) for x in node[1]])
                need_another_pass = True
            elif node[0] == '|' and result[-1][0] == '|':
                result[-1] = ('|', [('(', [x, y]) for x in result[-1][1] for y in node[1]])
                need_another_pass = True
            else:
                result.append(node)
        tree = result
        if not need_another_pass:
            return tree
    raise FilePatternParserError("Infinite loop while expanding the pattern")


def exists_treefile(pat_tree):
    """Test wether an expanded syntax tree of a pattern refers to an existing file.

    Returns True, False or None, like is_pattern_installed.
    """
    if len(pat_tree) != 1:
        # Pattern is too complex
        return None
    # pat_tree may be a file...
    if pat_tree[0][0] is None:
        return os.path.exists(pat_tree[0][1])
    # ... or a list of files
    if pat_tree[0][0] == '|':
        are_all_pathes = True
        for choice in pat_tree[0][1]:
            if choice[0] is not None:
                are_all_pathes = False
                break
            elif os.path.exists(choice[1]):
                return True
        # If the list of file contains only non-existing files, return False
        if are_all_pathes:
            return False
    return None


def get_globs_from_tree(pat_tree):
    """Transform a pattern syntax tree to a list of glob patterns"""
    glob_pat = ['']

    # List of translations
    patterns_from_glob = [
        (('[^', '/'), '?'), # [^/] => ?
        (('*', ('[^', '/')), '*'), # [^/]* => *
        (('+', ('[^', '/')), '*?'), # [^/]+ => *?
        # "." can match "/" in the pattern, contrary to the resulting glob.
        # This is a limitation of the translation
        (('.', None), '?'), # . => ?
        (('*', ('.', None)), '*'), # .* => *
        (('+', ('.', None)), '*?'), # .+ => *?
    ]

    for node in pat_tree:
        if node[0] is None:
            # Add a static part to every globs
            for i in range(len(glob_pat)):
                glob_pat[i] += node[1]
        elif node[0] == '(':
            globs_paren = get_globs_from_tree(node[1])
            # If the pattern is too complex, return None
            if globs_paren is None:
                return None
            glob_pat += [x + y for x in glob_pat for y in globs_paren]
        elif node[0] == '|':
            new_globpat = []
            for choice in node[1]:
                globs_choice = get_globs_from_tree([choice])
                # If the pattern is too complex, return None
                if globs_choice is None:
                    return None
                new_globpat += [x + y for x in glob_pat for y in globs_choice]
            glob_pat = new_globpat
        else:
            # Translate leafs
            has_matched = False
            for known_node, known_glob in patterns_from_glob:
                if node == known_node:
                    has_matched = True
                    for i in range(len(glob_pat)):
                        glob_pat[i] += known_glob
                    break
            # If the pattern is too complex, return None
            if not has_matched:
                return None
    return glob_pat


def is_pattern_installed(pattern, pass_number):
    """Test wether a file pattern refers to an existing file

    Parameters:
    * pattern: a file pattern in a file context file
    * pass_number: tell the precision to use:
      - #1: only check explicit paths
      - #2: transform pattern into a file glob

    Returns:
    * True if an existing file matches the pattern
    * False if no file matches the pattern
    * None if the pattern is too complex
    """
    # Trim the end of the pattern before the analysis
    for ending in ('(/.*)?', '/.*'):
        if pattern.endswith(ending):
            pattern = pattern[:-len(ending)]
            if not pattern:
                return True

    # HOME_DIR always exists
    if pattern == 'HOME_DIR':
        return True
    # Files in HOME_DIR are never assumed to exist
    if pattern.startswith('HOME_DIR'):
        return False

    try:
        pat_tree = parse_filepattern(pattern)
        assert pat_tree
        pat_tree = expand_syntax_tree(pat_tree)
    except FilePatternParserError as exc:
        # Re-raise the exception with the pattern
        exc.pattern = pattern
        raise exc

    result = exists_treefile(pat_tree)
    if result is not None or pass_number <= 1:
        return result

    # Try glob patterns in pass #2
    glob_patterns = get_globs_from_tree(pat_tree)
    if glob_patterns is not None:
        for gpat in glob_patterns:
            if len(glob.glob(gpat)):
                return True
        # The pattern has been translated into a list of globs and nothing matched
        return False

    # Still a too complex pattern
    return


def is_fcfile_installed(filename):
    """Test wether some file patterns in the given .fc file are applicable"""
    all_patterns = []
    with open(filename) as fd:
        for line in fd:
            line = line.strip()
            if not line or line[0] == '#' or line.startswith(('ifdef(`', 'ifndef(`', '\', `', '\')')):
                continue
            pattern = line.split()[0]
            if not pattern:
                continue
            existing_state = is_pattern_installed(pattern, 1)
            # If an existing file matches the pattern, return True.
            # If the pattern is more complex, add it to all_patterns.
            if existing_state:
                return True
            elif existing_state is None:
                all_patterns.append(pattern)
    if not all_patterns:
        return False

    # Second pass
    all_patterns2 = []
    for pattern in all_patterns:
        existing_state = is_pattern_installed(pattern, 2)
        if existing_state:
            return True
        elif existing_state is None:
            all_patterns2.append(pattern)
    if not all_patterns2:
        return False

    # By default, ignore too strange patterns where nothing else matches
    return False


def get_base_modules(policypath):
    """Yield modules in base.pp from the modules.conf file in policypath"""
    with open(os.path.join(policypath, 'modules.conf'), 'r') as fd:
        for line in fd:
            if '=' in line:
                modname, category = line.split('=', 1)
                if category.strip() == 'base':
                    yield modname.strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Get a list of useful SELinux modules")
    parser.add_argument('-p', '--path', type=str,
                        help="set the path where to search policy files")
    parser.add_argument('-b', '--base', action='store_true',
                        help="include base modules")
    parser.add_argument('-c', '--cmdline', action='store_true',
                        help="print a semodule command line to load modules")

    args = parser.parse_args(argv)
    path = args.path or DEFAULT_POLICYPATH
    basemodules = frozenset([] if args.base else get_base_modules(path))

    # Intialize the list with the default user modules
    modules = ['staff', 'sysadm', 'unprivuser']
    for dirpath, _, filenames in os.walk(path):
        for fc_file in filenames:
            if fc_file.endswith('.fc') and fc_file[:-3] not in basemodules:
                filename = os.path.join(dirpath, fc_file)
                try:
                    if is_fcfile_installed(filename):
                        modules.append(fc_file[:-3])
                except FilePatternParserError as exc:
                    sys.stderr.write(
                        "Pattern parser error: {} (pattern: {}, file: {})\n"
                        .format(exc.message, exc.pattern, filename))
                    return 1

    modules.sort()
    if args.cmdline:
        cmdline = 'semodule -v -b base.pp'
        # Read the policy name
        buildconf = os.path.join(path, '..', 'build.conf')
        if os.path.exists(buildconf):
            with open(buildconf, 'r') as fd:
                for line in fd:
                    line = line.strip()
                    if line.startswith('NAME'):
                        polname = line.split('=')[1].strip()
                        cmdline += ' -s ' + polname
                        break
        cmdline += ''.join(' -i {}.pp'.format(modname) for modname in modules)
        print(cmdline)
    else:
        for modname in modules:
            print(modname)
    return 0

if __name__ == '__main__':
    sys.exit(main())
