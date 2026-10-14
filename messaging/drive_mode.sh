#!/usr/bin/env bash
# drive_mode.sh on|off|status — keep the laptop awake with the lid closed, and run
# the LoRa beacon (ping gateway every few seconds, alternating SF7/SF10).
set -u
export PATH="$HOME/.local/bin:$PATH"
case "${1:-status}" in
  on)
    # Omarchy desktop: also switch its idle/lock off (no-op elsewhere)
    command -v omarchy >/dev/null && { [ -e "$HOME/.local/state/omarchy/indicators/stay-awake" ] || omarchy toggle idle stay-awake >/dev/null 2>&1; }
    # 2) tell logind: ignore the lid, no sleep, no idle action — for 12 h or until 'off'
    systemctl --user is-active -q loralink-inhibit.service 2>/dev/null || \
      systemd-run --user --quiet --unit=loralink-inhibit \
        systemd-inhibit --what=handle-lid-switch:sleep:idle --who="loralink" --why="LoRa drive test" --mode=block sleep 12h
    # 3) the beacon, logging to ~/loralink_drive.log
    systemctl --user is-active -q loralink-beacon.service 2>/dev/null || \
      systemd-run --user --quiet --unit=loralink-beacon "$(dirname "$(readlink -f "$0")")/loralink.py" beacon --every 8
    echo "drive mode ON: $(date '+%H:%M:%S')" | tee -a "$HOME/loralink_drive.log"
    ;;
  off)
    systemctl --user stop loralink-beacon.service loralink-inhibit.service 2>/dev/null
    command -v omarchy >/dev/null && [ -e "$HOME/.local/state/omarchy/indicators/stay-awake" ] && omarchy toggle idle allow-idle >/dev/null 2>&1
    echo "drive mode OFF: $(date '+%H:%M:%S')" | tee -a "$HOME/loralink_drive.log"
    ;;
  status)
    echo "stay-awake: $([ -e "$HOME/.local/state/omarchy/indicators/stay-awake" ] && echo yes || echo no)"
    echo "lid/sleep inhibitor: $(systemctl --user is-active loralink-inhibit.service 2>/dev/null)"
    echo "beacon: $(systemctl --user is-active loralink-beacon.service 2>/dev/null)"
    echo "link daemon: $(systemctl --user is-active loralink.service 2>/dev/null)"
    tail -3 "$HOME/loralink_drive.log" 2>/dev/null
    ;;
  *) echo "usage: drive_mode.sh on|off|status"; exit 2 ;;
esac
