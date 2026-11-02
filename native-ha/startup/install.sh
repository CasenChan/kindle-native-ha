#!/bin/sh
set -e
ROOT=/mnt/us/nativeha
PRIVATE=/var/local/nativeha
mkdir -p "$PRIVATE" "$ROOT/diagnostics"
chmod 700 "$PRIVATE"
exec >> "$ROOT/diagnostics/startup-install.log" 2>&1
printf '\nInstalling native HA startup %s\n' "$(date -u)"
test -s "$PRIVATE/device-key"
test -f "$ROOT/startup/nativeha.conf"
test -f "$ROOT/startup/autostart.sh"
test -d /etc/upstart
ls -l /bin/sh
grep '/mnt/' /proc/mounts || true
cp "$ROOT/startup/autostart.sh" "$PRIVATE/autostart.sh.new"
chmod 700 "$PRIVATE/autostart.sh.new"
mv "$PRIVATE/autostart.sh.new" "$PRIVATE/autostart.sh"
mntroot rw
trap 'mntroot ro' EXIT HUP INT TERM
if [ -f /etc/upstart/nativeha.conf ]; then
    cp /etc/upstart/nativeha.conf "$PRIVATE/nativeha.conf.previous"
fi
cp "$ROOT/startup/nativeha.conf" /etc/upstart/nativeha.conf.new
chmod 644 /etc/upstart/nativeha.conf.new
mv /etc/upstart/nativeha.conf.new /etc/upstart/nativeha.conf
sync
mntroot ro
trap - EXIT HUP INT TERM
printf 'Startup installed; disable with nativeha/disable-autostart on USB.\n'
eips 0 1 'HA startup installed. Restart.'
