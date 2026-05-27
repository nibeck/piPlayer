import os
import threading
from pathlib import Path

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from .base import MusicProvider

BASE_DIR = Path(__file__).resolve().parent.parent


class SpotifyManager:
    """Manages Spotify credentials, OAuth, and the authenticated client."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.client_id = None
        self.client_secret = None
        self.username = None
        self.redirect_uri = None
        self.scope = "user-read-currently-playing user-modify-playback-state"
        self.spotify = None
        self.auth_manager = None
        self._spotify_lock = threading.Lock()
        self._load_credentials()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _load_credentials(self):
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.username = os.getenv("SPOTIFY_USERNAME")
        self.redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")

    def has_credentials(self):
        return all([self.client_id, self.client_secret, self.username])

    def is_authenticated(self):
        return self.spotify is not None

    def save_credentials(self, client_id, client_secret, username, redirect_uri):
        self.client_id = client_id
        self.client_secret = client_secret
        self.username = username
        self.redirect_uri = redirect_uri

        os.environ["SPOTIFY_CLIENT_ID"] = client_id
        os.environ["SPOTIFY_CLIENT_SECRET"] = client_secret
        os.environ["SPOTIFY_USERNAME"] = username
        os.environ["SPOTIFY_REDIRECT_URI"] = redirect_uri

        env_file = BASE_DIR / '.env'
        # Read existing lines to preserve non-Spotify settings
        existing = {}
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    existing[k.strip()] = v.strip()

        existing["SPOTIFY_CLIENT_ID"] = client_id
        existing["SPOTIFY_CLIENT_SECRET"] = client_secret
        existing["SPOTIFY_USERNAME"] = username
        existing["SPOTIFY_REDIRECT_URI"] = redirect_uri

        env_lines = [f"{k}={v}" for k, v in existing.items()]
        env_file.write_text("\n".join(env_lines) + "\n")

        with self._spotify_lock:
            self.spotify = None
            self.auth_manager = None

    def _build_auth_manager(self):
        cache_path = BASE_DIR / f".cache-{self.username}"
        return SpotifyOAuth(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scope=self.scope,
            username=self.username,
            cache_path=str(cache_path),
            open_browser=False,
        )

    def get_authorize_url(self):
        self.auth_manager = self._build_auth_manager()
        return self.auth_manager.get_authorize_url()

    def handle_callback(self, code):
        if self.auth_manager is None:
            self.auth_manager = self._build_auth_manager()
        token_info = self.auth_manager.get_access_token(code, as_dict=True)
        if token_info:
            with self._spotify_lock:
                self.spotify = spotipy.Spotify(auth_manager=self.auth_manager)
            return True
        return False

    def try_cached_auth(self):
        if not self.has_credentials():
            return False
        auth_manager = self._build_auth_manager()
        token_info = auth_manager.cache_handler.get_cached_token()
        if token_info:
            if auth_manager.is_token_expired(token_info):
                token_info = auth_manager.refresh_access_token(token_info["refresh_token"])
            with self._spotify_lock:
                self.auth_manager = auth_manager
                self.spotify = spotipy.Spotify(auth_manager=auth_manager)
            return True
        return False


class SpotifyProvider(MusicProvider):
    """Spotify implementation using spotipy and the Spotify Web API."""

    def __init__(self):
        self._manager = SpotifyManager.get_instance()

    @property
    def manager(self):
        return self._manager

    def get_name(self):
        return "Spotify"

    def get_id(self):
        return "spotify"

    def needs_credentials(self):
        return True

    def has_credentials(self):
        return self._manager.has_credentials()

    def is_authenticated(self):
        return self._manager.is_authenticated()

    def is_active(self):
        return self._manager.is_authenticated()

    def get_current_playing_info(self):
        if not self._manager.is_authenticated():
            return None
        current_track = self._manager.spotify.current_user_playing_track()
        if current_track is None:
            return None
        return {
            "artist": current_track['item']['artists'][0]['name'],
            "album": current_track['item']['album']['name'],
            "album_art": current_track['item']['album']['images'][0]['url'],
            "title": current_track['item']['name'],
        }

    def start_playback(self):
        if not self._manager.is_authenticated():
            return "Not authenticated"
        try:
            self._manager.spotify.start_playback()
        except spotipy.SpotifyException as e:
            return f"Error in starting playback: {str(e)}"

    def stop_playback(self):
        if not self._manager.is_authenticated():
            return "Not authenticated"
        try:
            self._manager.spotify.pause_playback()
        except spotipy.SpotifyException as e:
            return f"Error in stopping playback: {str(e)}"

    def next_track(self):
        if not self._manager.is_authenticated():
            return "Not authenticated"
        try:
            self._manager.spotify.next_track()
        except spotipy.SpotifyException as e:
            return f"Error in skipping to next track: {str(e)}"

    def previous_track(self):
        if not self._manager.is_authenticated():
            return "Not authenticated"
        try:
            self._manager.spotify.previous_track()
        except spotipy.SpotifyException as e:
            return f"Error in skipping to previous track: {str(e)}"

    def start(self):
        self._manager.try_cached_auth()

    def stop(self):
        pass
