#!/bin/bash
# Auto-update webswitch agent from GitHub (2026 branch)
# Runs via cron every minute. Restarts the service only if the file changed.

REMOTE_URL="https://raw.githubusercontent.com/KChristman25/Light-the-Night/2026/rpi/webswitch_agent_2025.py"
LOCAL_FILE="/home/pi/webswitch/webswitch_agent_2025.py"
TMP_FILE="/tmp/webswitch_agent_new.py"

# Download latest from GitHub
curl -fsSL "$REMOTE_URL" -o "$TMP_FILE" || exit 1

# Compare checksums — only update if file actually changed
NEW_HASH=$(md5sum "$TMP_FILE" | cut -d' ' -f1)
OLD_HASH=$(md5sum "$LOCAL_FILE" 2>/dev/null | cut -d' ' -f1)

if [ "$NEW_HASH" != "$OLD_HASH" ]; then
  echo "[auto_update] New version detected — updating and restarting..."
  cp "$TMP_FILE" "$LOCAL_FILE"
  sudo systemctl restart webswitch
  echo "[auto_update] Done."
else
  echo "[auto_update] No change."
fi

rm -f "$TMP_FILE"
