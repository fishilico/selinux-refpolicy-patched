#!/bin/sh
# Sync the repository with some "upstream" repositories:
# * https://github.com/TresysTechnology/refpolicy for upstream refpolicy
# * https://github.com/TresysTechnology/refpolicy-contrib for contrib modules
# * https://github.com/pebenito/refpolicy for pebenito refpolicy (with systemd)
# * https://github.com/pebenito/refpolicy-contrib for its systemd part

# Ensure we are working in the toplevel directory
cd "$(dirname -- "$0")" || exit $?

# Run the given command after displaying it
log_and_run() {
    tput bold
    echo "Running: $*"
    tput sgr0
    "$@"
}

# Add remote repositories
for REMOTE_PATH in \
    TresysTechnology/refpolicy \
    TresysTechnology/refpolicy-contrib \
    pebenito/refpolicy \
    pebenito/refpolicy-contrib
do
    REMOTE_NAME="$(echo "$REMOTE_PATH" | tr / _)"
    REMOTE_URL="https://github.com/$REMOTE_PATH.git"
    if ! (git remote show | grep -q "^$REMOTE_NAME\$")
    then
        log_and_run git remote add "$REMOTE_NAME" "$REMOTE_URL" || exit $?
    fi
    log_and_run git fetch "$REMOTE_NAME" || exit $?
done

# Merge things
MERGING_BRANCH='upstream-sync'
if git branch --all | grep -q " $MERGING_BRANCH\$"
then
    # Change branch in case we are already on $MERGING_BRANCH
    if [ "$(git rev-parse --abbrev-ref HEAD)" = "$MERGING_BRANCH" ]
    then
        log_and_run git checkout master || exit $?
    fi
    log_and_run git branch -D "$MERGING_BRANCH" || exit $?
fi

# Checkout upstream policy
echo "Create new branch $MERGING_BRANCH from upstream repositories..."
if ! log_and_run git checkout TresysTechnology_refpolicy/master -b "$MERGING_BRANCH"
then
    echo >&2 "Unable to checkout upstream policy in $MERGING_BRANCH"
    exit 1
fi

# Merge with pebenito repository
if ! log_and_run git merge --no-edit pebenito_refpolicy/master
then
    echo >&2 "Unable to merge pebenito policy in $MERGING_BRANCH"
    exit 1
fi

# Remove policy/modules/contrib submodule
if ! (log_and_run git rm .gitmodules policy/modules/contrib && log_and_run git commit -m 'Remove contrib submodule')
then
    echo >&2 "Unable to remove contrib submodule $MERGING_BRANCH"
    exit 1
fi

# Add a subtree for policy/modules/contrib
if ! log_and_run git subtree add --prefix=policy/modules/contrib TresysTechnology_refpolicy-contrib master
then
    echo >&2 "Unable to add upstream contrib policy in a subtree of $MERGING_BRANCH"
    exit 1
fi
if ! log_and_run git -c core.editor=true subtree merge --prefix=policy/modules/contrib pebenito_refpolicy-contrib/master
then
    echo >&2 "Unable to pull pebenito contrib policy in $MERGING_BRANCH"
    exit 1
fi

# All done, now rebase master, if it exists
if ! log_and_run git checkout master
then
    echo "Unable to checkout master, assuming it is because it does not exist."
    exit
fi
echo "Rebasing master on top of $MERGING_BRANCH"
log_and_run git rebase "$MERGING_BRANCH" || exit $?
