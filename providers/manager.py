import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional, List

from .base import MusicProvider

BASE_DIR = Path(__file__).resolve().parent.parent


class ProviderManager:
    """Singleton that manages music provider selection and lifecycle."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._providers = {}
        self._active_id = None
        self._register_providers()
        self._load_selection()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _register_providers(self):
        from .spotify_provider import SpotifyProvider
        from .airplay_provider import AirPlayProvider
        for p in [SpotifyProvider(), AirPlayProvider()]:
            self._providers[p.get_id()] = p

    def _load_selection(self):
        provider_id = os.getenv("MUSIC_PROVIDER", "spotify")
        if provider_id in self._providers:
            self._active_id = provider_id
            self._providers[provider_id].start()

    def get_available_providers(self) -> List[MusicProvider]:
        return list(self._providers.values())

    def get_provider(self, provider_id: str) -> Optional[MusicProvider]:
        return self._providers.get(provider_id)

    def get_active(self) -> Optional[MusicProvider]:
        if self._active_id:
            return self._providers.get(self._active_id)
        return None

    def get_active_id(self) -> Optional[str]:
        return self._active_id

    def set_active(self, provider_id: str):
        if provider_id not in self._providers:
            return
        if self._active_id == provider_id:
            return

        # Stop old provider
        if self._active_id and self._active_id in self._providers:
            self._providers[self._active_id].stop()

        # Switch audio daemons
        self._switch_daemons(provider_id)

        # Start new provider
        self._active_id = provider_id
        self._providers[provider_id].start()

        # Persist selection
        self._save_selection(provider_id)

    def _switch_daemons(self, new_provider_id):
        """Stop/start audio daemons based on the selected provider."""
        try:
            if new_provider_id == "spotify":
                subprocess.run(
                    ["sudo", "systemctl", "stop", "shairport-sync"],
                    capture_output=True, timeout=10,
                )
                subprocess.run(
                    ["sudo", "systemctl", "start", "raspotify"],
                    capture_output=True, timeout=10,
                )
            elif new_provider_id == "airplay":
                subprocess.run(
                    ["sudo", "systemctl", "stop", "raspotify"],
                    capture_output=True, timeout=10,
                )
                subprocess.run(
                    ["sudo", "systemctl", "start", "shairport-sync"],
                    capture_output=True, timeout=10,
                )
        except Exception as e:
            print(f"Error switching daemons: {e}", file=sys.stderr)

    def _save_selection(self, provider_id):
        """Update MUSIC_PROVIDER in the .env file."""
        env_file = BASE_DIR / '.env'
        existing = {}
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    existing[k.strip()] = v.strip()

        existing["MUSIC_PROVIDER"] = provider_id
        os.environ["MUSIC_PROVIDER"] = provider_id

        env_lines = [f"{k}={v}" for k, v in existing.items()]
        env_file.write_text("\n".join(env_lines) + "\n")
