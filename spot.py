import os
from pathlib import Path
import threading
import spotipy
from spotipy.oauth2 import SpotifyOAuth


def load_env_file(env_path='.env'):
    cwd_path = Path(env_path)
    script_path = Path(__file__).resolve().parent / env_path
    if cwd_path.is_file():
        env_file = cwd_path
    elif script_path.is_file():
        env_file = script_path
    else:
        return
    content = env_file.read_text()
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, val = line.split('=', 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and val and key not in os.environ:
            os.environ[key] = val


load_env_file()


class SpotifyManager:
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
        self.redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "https://localhost:5000/callback")

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

        env_file = Path(__file__).resolve().parent / '.env'
        env_lines = [
            f"SPOTIFY_CLIENT_ID={client_id}",
            f"SPOTIFY_CLIENT_SECRET={client_secret}",
            f"SPOTIFY_USERNAME={username}",
            f"SPOTIFY_REDIRECT_URI={redirect_uri}",
        ]
        env_file.write_text("\n".join(env_lines) + "\n")

        with self._spotify_lock:
            self.spotify = None
            self.auth_manager = None

    def _build_auth_manager(self):
        cache_path = Path(__file__).resolve().parent / f".cache-{self.username}"
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


def get_current_playing_info():
    mgr = SpotifyManager.get_instance()
    if not mgr.is_authenticated():
        return None
    current_track = mgr.spotify.current_user_playing_track()
    if current_track is None:
        return None
    return {
        "artist": current_track['item']['artists'][0]['name'],
        "album": current_track['item']['album']['name'],
        "album_cover": current_track['item']['album']['images'][0]['url'],
        "title": current_track['item']['name'],
    }


def start_music():
    mgr = SpotifyManager.get_instance()
    if not mgr.is_authenticated():
        return "Not authenticated"
    try:
        mgr.spotify.start_playback()
    except spotipy.SpotifyException as e:
        return f"Error in starting playback: {str(e)}"


def stop_music():
    mgr = SpotifyManager.get_instance()
    if not mgr.is_authenticated():
        return "Not authenticated"
    try:
        mgr.spotify.pause_playback()
    except spotipy.SpotifyException as e:
        return f"Error in stopping playback: {str(e)}"


def skip_to_next():
    mgr = SpotifyManager.get_instance()
    if not mgr.is_authenticated():
        return "Not authenticated"
    try:
        mgr.spotify.next_track()
        return "Skipped to next track."
    except spotipy.SpotifyException as e:
        return f"Error in skipping to next track: {str(e)}"


def skip_to_previous():
    mgr = SpotifyManager.get_instance()
    if not mgr.is_authenticated():
        return "Not authenticated"
    try:
        mgr.spotify.previous_track()
        return "Skipped to previous track."
    except spotipy.SpotifyException as e:
        return f"Error in skipping to previous track: {str(e)}"
