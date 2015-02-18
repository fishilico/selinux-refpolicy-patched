#!/bin/sh
# Generate a semodule line which can be used to reinstall current refpolicy

BASEDIR="$(dirname $0)/.."
POLICY_NAME=$(sed -n 's/^.*NAME\s*=\s*\(.*\)$/\1/p' "$BASEDIR/build.conf")
CMDLINE="semodule -v -b base.pp -s $POLICY_NAME"
OTHER_MODS=""
for MODULE in $(semodule -l |cut -f1)
do
    FILE="$MODULE.pp"
    if [ -f "$BASEDIR/$FILE" ]
    then
        CMDLINE="$CMDLINE -i $FILE"
    else
        OTHER_MODS="$OTHER_MODS $MODULE"
    fi
done

echo "$CMDLINE"
if [ -n "$OTHER_MODS" ]
then
    echo "Other modules:$OTHER_MODS"
fi

# Use "-e" for "execute"
if [ "$1" = "-e" ]
then
    exec $CMDLINE
fi
