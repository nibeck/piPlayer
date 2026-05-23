from abc import ABC, abstractmethod
from typing import Optional, Dict, Union


class MusicProvider(ABC):
    """Abstract base class that all music providers must implement."""

    @abstractmethod
    def get_name(self) -> str:
        """Return human-readable provider name, e.g. 'Spotify' or 'Apple Music'."""

    @abstractmethod
    def get_id(self) -> str:
        """Return machine identifier, e.g. 'spotify' or 'airplay'."""

    @abstractmethod
    def needs_credentials(self) -> bool:
        """Whether this provider requires user-supplied credentials."""

    @abstractmethod
    def has_credentials(self) -> bool:
        """Whether credentials are configured (always True for AirPlay)."""

    @abstractmethod
    def is_authenticated(self) -> bool:
        """Whether the provider is ready for playback control."""

    @abstractmethod
    def is_active(self) -> bool:
        """Whether a client is currently connected and streaming."""

    @abstractmethod
    def get_current_playing_info(self) -> Optional[Dict[str, Union[str, bytes]]]:
        """Return dict with keys: title, artist, album, album_art.
        album_art is either a URL string, bytes (raw image data), or None.
        Returns None if nothing is playing."""

    @abstractmethod
    def start_playback(self) -> Optional[str]:
        """Resume playback. Returns error string on failure, None on success."""

    @abstractmethod
    def stop_playback(self) -> Optional[str]:
        """Pause playback. Returns error string on failure, None on success."""

    @abstractmethod
    def next_track(self) -> Optional[str]:
        """Skip to next track. Returns error string on failure, None on success."""

    @abstractmethod
    def previous_track(self) -> Optional[str]:
        """Skip to previous track. Returns error string on failure, None on success."""

    def start(self):
        """Called when this provider becomes the active one.
        Override to start metadata listeners, daemon threads, etc."""
        pass

    def stop(self):
        """Called when this provider is deactivated.
        Override to clean up threads/resources."""
        pass
