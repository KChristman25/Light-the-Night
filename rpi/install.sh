#!/bin/bash
# Run this once on the Pi to install the webswitch agent as a system service.
# It will auto-start on boot and auto-restart if it crashes.
#
# Usage:
#   cd /path/to/rpi
#   chmod +x install.sh
#   sudo ./install.sh

set -e

INSTALL_DIR="/home/pi/webswitch"
SERVICE_NAME="webswitch"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== LTN Web Switch — Install ==="

# 1. Create install directory and copy files
echo "[1/4] Copying files to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/webswitch_agent_2025.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/engine.py"               "$INSTALL_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR/editor_agent.py"         "$INSTALL_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR/editor_server.py"        "$INSTALL_DIR/" 2>/dev/null || true
chown -R pi:pi "$INSTALL_DIR"

# 2. Install service file
echo "[2/4] Installing systemd service..."
cp "$SCRIPT_DIR/webswitch.service" "$SERVICE_FILE"
systemctl daemon-reload

# 3. Enable (auto-start on boot)
echo "[3/4] Enabling service (auto-start on boot)..."
systemctl enable "$SERVICE_NAME"

# 4. Copy auto_update.sh
echo "[4/5] Installing auto-update script..."
cp "$SCRIPT_DIR/auto_update.sh" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/auto_update.sh"
chown pi:pi "$INSTALL_DIR/auto_update.sh"

# 5. Start (or restart) right now
echo "[5/5] Starting service now..."
systemctl restart "$SERVICE_NAME"

# Set up cron job to auto-pull from GitHub every minute (runs as pi user)
CRON_LINE="* * * * * bash /home/pi/webswitch/auto_update.sh >> /home/pi/webswitch/update.log 2>&1"
crontab -u pi -l 2>/dev/null | grep -qF "auto_update.sh" || \
  (crontab -u pi -l 2>/dev/null; echo "$CRON_LINE") | crontab -u pi -
echo "[cron] Auto-update cron installed for pi user."

echo ""
echo "=== Done! ==="
systemctl status "$SERVICE_NAME" --no-pager -l
echo ""
echo "Useful commands:"
echo "  sudo systemctl status webswitch    # check if running"
echo "  sudo journalctl -u webswitch -f    # live log output"
echo "  sudo systemctl restart webswitch   # restart manually"
echo "  sudo systemctl stop webswitch      # stop"
echo "  tail -f /home/pi/webswitch/update.log   # watch auto-update log"
