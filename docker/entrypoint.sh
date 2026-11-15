#!/bin/sh
set -eu

CONFIG_DIR=/config
# 4294967295 is (uid_t)-1, which setreuid reads as "leave unchanged".
MAX_ID=4294967294

# An empty value counts as unset, as it does for Tomarr's own variables.
PUID=${PUID:-1000}
PGID=${PGID:-1000}

fail() {
    echo "tomarr: $1" >&2
    exit 1
}

check_id() {
    case $2 in
        *[!0-9]* | 0?*) fail "$1 must be a whole number with no leading zero, got '$2'." ;;
    esac
    # The length check comes first, so the shell never compares a number it cannot hold.
    if [ "${#2}" -gt 10 ] || [ "$2" -gt "$MAX_ID" ]; then
        fail "$1 must be $MAX_ID or less, got '$2'."
    fi
}

check_id PUID "$PUID"
check_id PGID "$PGID"

mkdir -p "$CONFIG_DIR" || fail "Could not create $CONFIG_DIR."

# Only when the folder's owner differs, which is a first start or a changed PUID or PGID, so a
# normal start never walks the tree. -h changes a symlink itself, never what it points to.
if [ "$(stat -c '%u:%g' "$CONFIG_DIR")" != "$PUID:$PGID" ]; then
    echo "tomarr: Setting the owner of $CONFIG_DIR to $PUID:$PGID."
    chown -R -h "$PUID:$PGID" "$CONFIG_DIR" \
        || fail "Could not change the owner of $CONFIG_DIR to $PUID:$PGID. Check that the mount is writable and allows chown, or set PUID and PGID to its owner."
fi

echo "tomarr: Running as uid $PUID, gid $PGID."
exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups python -m tomarr
