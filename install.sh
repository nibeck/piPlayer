#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
SERVICE_NAME="piplayer"

echo "================================"
echo "  piPlayer Installer"
echo "================================"
echo ""

# 1. Install Raspotify
echo "[1/5] Installing Raspotify..."
if command -v raspotifyd &> /dev/null; then
    echo "  Raspotify is already installed, skipping."
else
    curl -sL https://dtcooper.github.io/raspotify/install.sh | sh
    echo "  Raspotify installed."
fi
sudo systemctl enable raspotify
sudo systemctl start raspotify
echo ""

# 2. Install system dependencies
echo "[2/5] Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3-full python3-venv openssl > /dev/null
echo "  System dependencies installed."
echo ""

# 3. Create Python virtual environment
echo "[3/5] Setting up Python virtual environment..."
if [ -d "$VENV_DIR" ]; then
    echo "  Virtual environment already exists, skipping creation."
else
    python3 -m venv "$VENV_DIR"
    echo "  Virtual environment created."
fi
echo ""

# 4. Install Python dependencies
echo "[4/5] Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"
echo "  Python dependencies installed."
echo ""

# 5. Set up systemd service
echo "[5/5] Setting up systemd service..."
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<EOF
[Unit]
Description=piPlayer Spotify Record Player
After=network-online.target sound.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$SCRIPT_DIR
ExecStart=$VENV_DIR/bin/python $SCRIPT_DIR/main.py
Restart=on-failure
RestartSec=5
Environment=SDL_VIDEODRIVER=kms
Environment=SDL_AUDIODRIVER=alsa

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
echo "  Systemd service '${SERVICE_NAME}' created and enabled."
echo ""

# Done
LOCAL_IP=$(hostname -I | awk '{print $1}')
echo "================================"
echo "  Installation Complete!"
echo "================================"
echo ""
echo "Next steps:"
echo "  1. Configure Spotify credentials:"
echo "     $VENV_DIR/bin/python $SCRIPT_DIR/setup.py"
echo "     Then open https://${LOCAL_IP}:5000 in your browser."
echo ""
echo "  2. After configuring, stop the setup server (Ctrl+C) and start the player:"
echo "     sudo systemctl start ${SERVICE_NAME}"
echo ""
echo "  3. The player will auto-start on boot from now on."
echo ""
echo "  Useful commands:"
echo "     sudo systemctl start ${SERVICE_NAME}    # Start the player"
echo "     sudo systemctl stop ${SERVICE_NAME}     # Stop the player"
echo "     sudo systemctl restart ${SERVICE_NAME}  # Restart the player"
echo "     sudo systemctl status ${SERVICE_NAME}   # Check status"
echo "     journalctl -u ${SERVICE_NAME} -f        # View logs"
echo ""
