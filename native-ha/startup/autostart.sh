#!/bin/sh
# This file lives on the system data partition; USB mass storage may unmount /mnt/us.
sleep 15
attempt=0
while [ "$attempt" -lt 90 ]; do
    if awk '$2 == "/mnt/us" && $4 ~ /(^|,)rw(,|$)/ { found=1 } END { exit !found }' /proc/mounts; then
        break
    fi
    sleep 2
    attempt=$((attempt + 1))
done
[ "$attempt" -lt 90 ] || exit 0
[ -f /mnt/us/nativeha/disable-autostart ] && exit 0
[ -f /tmp/nativeha_manual_exit ] && exit 0
[ -s /var/local/nativeha/device-key ] || exit 0
[ -f /mnt/us/koreader/plugins/nativeha.koplugin/main.lua ] || exit 0
[ -f /mnt/us/extensions/nativeha/launch.sh ] || exit 0
mkdir -p /mnt/us/nativeha/diagnostics
printf '\nNative HA autostart %s\n' "$(date -u)" >> /mnt/us/nativeha/diagnostics/autostart.log
/bin/sh /mnt/us/extensions/nativeha/launch.sh >> /mnt/us/nativeha/diagnostics/autostart.log 2>&1
result=$?
printf 'Native HA exited %s\n' "$result" >> /mnt/us/nativeha/diagnostics/autostart.log
exit "$result"
