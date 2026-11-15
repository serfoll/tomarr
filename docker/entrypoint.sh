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

# Every entry with another owner is fixed, not only the folder itself, so a file copied in as root
# cannot stop the start. Entries that already match are left alone. -h changes a symlink itself,
# never what it points to.
wrong_owner() {
    find "$CONFIG_DIR" \( ! -uid "$PUID" -o ! -gid "$PGID" \) "$@"
}

if [ -n "$(wrong_owner -print -quit)" ]; then
    echo "tomarr: Setting the owner of $CONFIG_DIR to $PUID:$PGID."
    wrong_owner -exec chown -h "$PUID:$PGID" {} + \
        || fail "Could not change the owner of $CONFIG_DIR to $PUID:$PGID. Check that the mount is writable and allows chown, or set PUID and PGID to its owner."
fi

echo "tomarr: Running as uid $PUID, gid $PGID."
exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups python -m tomarr
