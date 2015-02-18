#!/bin/sh
# Perform installation in DESTDIR

# Find the source directory from the script path
SRCDIR="$(dirname "$0")/.."

# Install everything
make -C "$SRCDIR" "DESTDIR=${DESTDIR:-}" install
make -C "$SRCDIR" "DESTDIR=${DESTDIR:-}" install-headers
make -C "$SRCDIR" "DESTDIR=${DESTDIR:-}" install-docs

# If /etc/selinux/config does not exist yet, create it
if ! [ -e "${DESTDIR:-}/etc/selinux/config" ]
then
    echo "Creating ${DESTDIR:-}/etc/selinux/config"
    cat > "${DESTDIR:-}/etc/selinux/config" << EOF
# This file controls the state of SELinux on the system.
# SELINUX= can take one of these three values:
#       enforcing - SELinux security policy is enforced.
#       permissive - SELinux prints warnings
#                       instead of enforcing.
#       disabled - No SELinux policy is loaded.
SELINUX=permissive

# SELINUXTYPE= takes the name of SELinux policy to
# be used.
SELINUXTYPE=${NAME:-refpolicy-patched}
EOF
fi

# Regenerate /var/lib/sepolgen/interface_info
sepolgen-ifgen -o "${DESTDIR:-}/var/lib/sepolgen/interface_info" -i "${DESTDIR:-}/usr/share/selinux/${NAME:-refpolicy-patched}"
