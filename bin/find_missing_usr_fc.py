#!/usr/bin/env python
"""
Archlinux only uses /usr/bin folder. /bin, /sbin and /usr/sbin are symlinks to it.
This program read all .fc files and find /bin, /sbin and /usr/sbin definitions
which don't have a matching /usr/bin definition.

Same thing applies to /usr/lib and /lib folders
"""
import re
import os
import os.path


def analyze_fc_file(filename):
    """Analyze a .fc file"""
    definitions = {'bin': {}, 'sbin': {}, 'usr/bin': {}, 'usr/sbin': {},
                   'lib': {}, 'usr/lib': {}}

    # Read file
    ifdef_level = 0
    with open(filename, 'r') as f:
        for line in f:
            # Skip optional blocks
            if line.startswith('ifdef(') or line.startswith('ifndef('):
                ifdef_level += 1
            elif line.startswith('\')'):
                ifdef_level -= 1
            if ifdef_level > 0:
                continue

            # /bin, /sbin, /usr/bin and /usr/sbin
            matches = re.match(r'^/(?P<dir>(usr/)?s?bin)/(?P<path>\S+)\s+(?P<ftype>-.)?\s+(?P<context>\S+)', line.strip())
            if matches is not None:
                d, p, t, c = matches.group('dir', 'path', 'ftype', 'context')
                # Ignore /bin/.* and /sbin/.* definitions
                if p != '.*':
                    definitions[d][p] = (t, c)
                continue

            # /lib, /usr/lib
            matches = re.match(r'^/(?P<dir>(usr/)?lib)/(?P<path>\S+)\s+(?P<ftype>-.)?\s+(?P<context>\S+)', line.strip())
            if matches is not None:
                d, p, t, c = matches.group('dir', 'path', 'ftype', 'context')
                # Ignore /lib/.* and /lib/.* definitions
                # and /lib/ld-[^/]*\.so(\.[^/]*)* and /lib/security/pam_poldi\.so
                if p not in ('.*', 'ld-[^/]*\\.so(\\.[^/]*)*', 'security/pam_poldi\\.so'):
                    definitions[d][p] = (t, c)
                continue

            # /usr/s?bin and /usr/(s)?bin
            matches = re.match(r'^/(usr/(s|\(s\))\?bin)/(?P<path>\S+)\s+(?P<ftype>-.)?\s+(?P<context>\S+)', line.strip())
            if matches is not None:
                p, t, c = matches.group('path', 'ftype', 'context')
                definitions['usr/bin'][p] = (t, c)
                definitions['usr/sbin'][p] = (t, c)
                continue

    if ifdef_level != 0:
        print("{}: invalid ifdef level at end of file, {}".format(filename, ifdef_level))
        return

    # Check binary folder
    bindef = definitions['usr/bin']
    # Quirk to be able to treat refpolicy before changing /usr/sbin to /usr/s?bin
    bindef.update(definitions['usr/sbin'])
    for bindir in 'bin', 'sbin', 'usr/sbin':
        for path, data in sorted(definitions[bindir].items()):
            ftype, context = data
            data2 = bindef.get(path)
            if data2 is None:
                print("{}: missing policy (from {}): /usr/bin/{} {} {}"
                      .format(filename, bindir, path, ftype or '', context))
            elif data != data2:
                ftype2, context2 = data2
                print("{}: mismatching policy: <{}/{} {} {}> vs. </usr/bin/{} {} {}>"
                      .format(filename, bindir, path, ftype or '', context, path, ftype2 or '', context2))

    # Check library folder
    libdef = definitions['usr/lib']
    for path, data in sorted(definitions['lib'].items()):
        ftype, context = data
        data2 = libdef.get(path)
        if data2 is None:
            print("{}: missing policy (from lib): /usr/lib/{} {} {}".format(filename, path, ftype or '', context))
        elif data != data2:
            ftype2, context2 = data2
            print("{}: mismatching policy: </lib/{} {} {}> vs. </usr/lib/{} {} {}>"
                  .format(filename, path, ftype or '', context, path, ftype2 or '', context2))


def analyze_all_fc(dirname):
    """Analyze all .fc files in the specified directory"""
    for dirpath, _, files in os.walk(dirname):
        for filename in files:
            if filename.endswith('.fc'):
                analyze_fc_file(os.path.join(dirpath, filename))


if __name__ == '__main__':
    BASE_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
    analyze_all_fc(os.path.join(BASE_DIR, 'policy'))
