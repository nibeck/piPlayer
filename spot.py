"""Backward-compatibility shim. All logic has moved to providers/."""

from providers import (
    get_current_playing_info,
    start_music,
    stop_music,
    skip_to_next,
    skip_to_previous,
)
from providers.spotify_provider import SpotifyManager
from providers.manager import ProviderManager
