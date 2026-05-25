#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
SERVICE_NAME="piplayer"

echo "================================"
echo "  piPlayer Installer"
echo "================================"
echo ""

# 1. Install Raspotify (Spotify Connect)
echo "[1/7] Installing Raspotify..."
if command -v raspotifyd &> /dev/null; then
    echo "  Raspotify is already installed, skipping."
else
    curl -sL https://dtcooper.github.io/raspotify/install.sh | sh
    echo "  Raspotify installed."
fi
sudo systemctl enable raspotify
sudo systemctl start raspotify
echo ""

# 2. Install shairport-sync (AirPlay)
echo "[2/7] Installing shairport-sync..."
if command -v shairport-sync &> /dev/null; then
    echo "  shairport-sync is already installed, skipping."
else
    sudo apt-get update -qq
    sudo apt-get install -y -qq shairport-sync > /dev/null
    echo "  shairport-sync installed."
fi

# Configure metadata pipe and device name
SHAIRPORT_CONF="/etc/shairport-sync.conf"
if [ -f "$SHAIRPORT_CONF" ]; then
    # Enable metadata if not already configured
    if ! grep -q 'metadata' "$SHAIRPORT_CONF" 2>/dev/null; then
        sudo bash -c "cat >> $SHAIRPORT_CONF" <<'METADATA'

metadata = {
    enabled = "yes";
    include_cover_art = "yes";
    pipe_name = "/tmp/shairport-sync-metadata";
};
METADATA
        echo "  Metadata pipe enabled in shairport-sync config."
    fi
    # Set AirPlay device name if not already configured
    if ! grep -q 'general' "$SHAIRPORT_CONF" 2>/dev/null; then
        sudo sed -i '1i general = {\n  name = "piPlayer";\n};' "$SHAIRPORT_CONF"
        echo "  AirPlay device name set to 'piPlayer'."
    fi
fi
sudo systemctl enable shairport-sync
# Don't start shairport-sync by default -- let the provider manager handle it
sudo systemctl stop shairport-sync 2>/dev/null || true
echo ""

# 3. Install system dependencies
echo "[3/7] Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3-full python3-venv openssl dbus > /dev/null
echo "  System dependencies installed."
echo ""

# 4. Create Python virtual environment
echo "[4/7] Setting up Python virtual environment..."
if [ -d "$VENV_DIR" ]; then
    echo "  Virtual environment already exists, skipping creation."
else
    python3 -m venv "$VENV_DIR"
    echo "  Virtual environment created."
fi
echo ""

# 5. Install Python dependencies
echo "[5/7] Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"
echo "  Python dependencies installed."
echo ""

# 6. Disable old systemd service if present
if systemctl is-enabled ${SERVICE_NAME} &> /dev/null; then
    echo "[6/7] Removing old systemd service..."
    sudo systemctl stop ${SERVICE_NAME} 2>/dev/null || true
    sudo systemctl disable ${SERVICE_NAME} 2>/dev/null || true
    sudo rm -f /etc/systemd/system/${SERVICE_NAME}.service
    sudo systemctl daemon-reload
else
    echo "[6/7] No old systemd service to remove."
fi

# 6. Set up desktop autostart
echo "[7/7] Setting up autostart..."
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
cat > "$AUTOSTART_DIR/${SERVICE_NAME}.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=piPlayer
Comment=Spotify and Apple Music Record Player
Exec=bash -c '$VENV_DIR/bin/python $SCRIPT_DIR/main.py >> $SCRIPT_DIR/piPlayer.log 2>&1'
Path=$SCRIPT_DIR
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
echo "  Desktop autostart entry created."
echo ""

# Configure Raspotify to run as current user (required for PipeWire audio access)
RASPOTIFY_OVERRIDE_DIR="/etc/systemd/system/raspotify.service.d"
if [ ! -f "$RASPOTIFY_OVERRIDE_DIR/override.conf" ]; then
    CURRENT_USER=$(whoami)
    CURRENT_UID=$(id -u)
    sudo mkdir -p "$RASPOTIFY_OVERRIDE_DIR"
    sudo bash -c "cat > $RASPOTIFY_OVERRIDE_DIR/override.conf" <<OVERRIDE
[Service]
User=$CURRENT_USER
ProtectHome=no
Environment=XDG_RUNTIME_DIR=/run/user/$CURRENT_UID
OVERRIDE
    sudo systemctl daemon-reload
    sudo systemctl restart raspotify
    echo "  Raspotify configured to run as $CURRENT_USER (PipeWire access)."
fi
echo ""

# Configure sudoers for daemon switching (allows piPlayer to start/stop audio services)
SUDOERS_FILE="/etc/sudoers.d/piplayer"
if [ ! -f "$SUDOERS_FILE" ]; then
    CURRENT_USER=$(whoami)
    sudo bash -c "cat > $SUDOERS_FILE" <<SUDOERS
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl start raspotify
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop raspotify
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl start shairport-sync
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop shairport-sync
SUDOERS
    sudo chmod 440 "$SUDOERS_FILE"
    echo "  Sudoers configured for audio daemon switching."
fi
echo ""

# Done
LOCAL_IP=$(hostname -I | awk '{print $1}')
echo "================================"
echo "  Installation Complete!"
echo "================================"
echo ""
echo "Next steps:"
echo "  1. Configure your music service:"
echo "     $VENV_DIR/bin/python $SCRIPT_DIR/setup.py"
echo "     Then open https://${LOCAL_IP}:5000 in your browser."
echo ""
echo "  2. Choose Spotify or Apple Music (AirPlay) from the setup page."
echo ""
echo "  3. After configuring, stop the setup server (Ctrl+C) and start the player:"
echo "     $VENV_DIR/bin/python $SCRIPT_DIR/main.py"
echo ""
echo "  4. The player will auto-start on boot from now on."
echo ""
