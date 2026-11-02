#!/bin/sh
if [ "$(id -u)" != "0" ]; then
    exec /var/local/mkk/su -s /bin/sh -c '/bin/sh /mnt/us/extensions/nativeha/launch.sh'
fi
export KINDLE_NATIVE_HA=1
umask 077
LOCK=/tmp/nativeha-launch.lock
if ! mkdir "$LOCK" 2>/dev/null; then
    if [ -f "$LOCK/pid" ] && kill -0 "$(cat "$LOCK/pid")" 2>/dev/null; then
        exit 0
    fi
    rm -f "$LOCK/pid"
    rmdir "$LOCK" 2>/dev/null || exit 1
    mkdir "$LOCK" || exit 1
fi
printf '%s\n' "$$" > "$LOCK/pid"
trap 'lipc-set-prop com.lab126.powerd preventScreenSaver 0 >/dev/null 2>&1; rm -f /tmp/nativeha-launch.lock/pid; rmdir /tmp/nativeha-launch.lock 2>/dev/null' EXIT HUP INT TERM
/bin/sh /mnt/us/koreader/koreader.sh --kual
