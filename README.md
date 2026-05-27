# piPlayer

A vinyl record player interface for Raspberry Pi with a round LCD display. Supports both **Spotify** and **Apple Music** (via AirPlay). Spin the record, scratch for sound effects, and control playback from the touchscreen or your phone.

Based on the [Concept Bytes Record Player](https://github.com/Concept-Bytes/Record-Player).

## Features

- **Dual music provider support** -- switch between Spotify and Apple Music from a web UI
- Real-time display of currently playing track, artist, and album art
- Spinning vinyl record animation with provider logo (Spotify or Apple) at the center
- Scratch sound effects via swipe gesture
- Touchscreen playback controls: previous, play/pause, next
- Web-based setup and provider switching at `https://<hostname>.local:5001`
- Automatic service management -- switching providers starts/stops the correct audio daemon
- Network-agnostic access via mDNS hostname (works on WiFi or Ethernet)
- Optimized rendering with frame rate limiting and rotation caching for low CPU usage

## Requirements

### Hardware

- Raspberry Pi (tested on Pi 4/5)
- Round LCD display (1080x1080)
- USB audio output (speaker/DAC)

### Software

- Raspberry Pi OS with desktop (Wayland/labwc)
- Python 3.7+
- For Spotify: a Spotify Premium account and [Spotify Developer](https://developer.spotify.com/dashboard) app credentials
- For Apple Music: an iPhone or Mac on the same network

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/nibeck/piPlayer.git
cd piPlayer
./install.sh
```

The installer sets up:
- **Raspotify** (Spotify Connect receiver)
- **shairport-sync** (AirPlay receiver with metadata support)
- Python virtual environment and dependencies
- Desktop autostart entry for boot-on-startup
- Sudoers rules for passwordless audio daemon switching

### 2. Configure your music provider

```bash
venv/bin/python setup.py
```

Open `https://<your-pi-hostname>.local:5001` in your browser and choose Spotify or Apple Music.

**For Spotify:**
- Enter your Client ID, Client Secret, and username from the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
- Register `https://<your-pi-hostname>.local:5001/callback` as a Redirect URI in your Spotify app settings
- Complete the OAuth authorization flow

**For Apple Music (AirPlay):**
- No credentials needed
- Open the Music app on your iPhone, tap AirPlay, and select your Pi

### 3. Start the player

```bash
venv/bin/python main.py
```

Or in windowed mode for development:

```bash
venv/bin/python main.py --windowed
```

The player auto-starts on boot via the desktop autostart entry created by the installer.

## Controls

- **Touchscreen buttons**: previous, play/pause, next (bottom bar)
- **Drag on record**: manually spin the vinyl
- **Swipe on record**: scratch sound effect
- **ESC key**: exit the player
- **Web UI** (`https://<hostname>.local:5001/setup`): switch providers, update credentials

## Architecture

```
piPlayer/
  main.py                    # Pygame UI -- record animation, controls, metadata display
  web_config.py              # Flask web server for setup and provider switching
  setup.py                   # Standalone setup server for initial configuration
  install.sh                 # Full installer for Raspberry Pi
  providers/
    base.py                  # MusicProvider abstract base class
    spotify_provider.py      # Spotify via spotipy + Spotify Web API
    airplay_provider.py      # Apple Music via shairport-sync metadata pipe + D-Bus
    manager.py               # ProviderManager singleton -- provider lifecycle and daemon control
    __init__.py              # Convenience shim functions for main.py
  assets/                    # UI icons and provider logos
  records/                   # Vinyl record artwork (randomly selected)
  sfx/                       # Scratch sound effects (.wav)
  templates/                 # Flask HTML templates for web UI
```

### Provider abstraction

Both Spotify and Apple Music implement the `MusicProvider` interface. The `ProviderManager` singleton handles:
- Switching between providers at runtime
- Starting/stopping audio daemons (`raspotify` and `shairport-sync`)
- Persisting the selection to `.env`

The web UI at `/setup` lets you switch providers, which triggers daemon management automatically.

### How AirPlay works

- **shairport-sync** acts as an AirPlay receiver
- Metadata (track, artist, album art) is read from a named pipe at `/tmp/shairport-sync-metadata`
- Playback control (play/pause/skip) is sent via D-Bus to shairport-sync's RemoteControl interface
- Album art is received as raw bytes from the metadata pipe

### How Spotify works

- **Raspotify** (librespot) acts as a Spotify Connect receiver for audio
- The **Spotify Web API** (via spotipy) provides now-playing metadata and playback control
- OAuth tokens are cached locally for automatic re-authentication on restart

## Configuration

Configuration is stored in a `.env` file in the project root:

```bash
MUSIC_PROVIDER=spotify          # or "airplay"
SPOTIFY_CLIENT_ID=your_id
SPOTIFY_CLIENT_SECRET=your_secret
SPOTIFY_USERNAME=your_username
SPOTIFY_REDIRECT_URI=https://your-pi.local:5001/callback
```

The web UI manages this file automatically. You can also edit it directly.

## Physical Build

For instructions on building the physical record player enclosure, wiring diagrams, and parts list:

- [Concept Bytes](https://concept-bytes.com) (search for "Spotify Record Player")
- [Patreon](https://patreon.com/ConceptBytes)

## Acknowledgments

Original project by [Concept Bytes](https://github.com/Concept-Bytes/Record-Player). Apple Music/AirPlay support, provider abstraction, web UI, and performance optimizations added by [@nibeck](https://github.com/nibeck).
