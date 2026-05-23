import os
from pathlib import Path


def load_env_file(env_path='.env'):
    """Load environment variables from a .env file if present."""
    cwd_path = Path(env_path)
    script_path = Path(__file__).resolve().parent.parent / env_path
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


# Load .env on import
load_env_file()


# --- Convenience shim functions ---
# These mirror the old spot.py module-level API so main.py can import them.

from .manager import ProviderManager


def get_current_playing_info():
    provider = ProviderManager.get_instance().get_active()
    if provider is None:
        return None
    return provider.get_current_playing_info()


def start_music():
    provider = ProviderManager.get_instance().get_active()
    if provider is None:
        return "No provider active"
    return provider.start_playback()


def stop_music():
    provider = ProviderManager.get_instance().get_active()
    if provider is None:
        return "No provider active"
    return provider.stop_playback()


def skip_to_next():
    provider = ProviderManager.get_instance().get_active()
    if provider is None:
        return "No provider active"
    return provider.next_track()


def skip_to_previous():
    provider = ProviderManager.get_instance().get_active()
    if provider is None:
        return "No provider active"
    return provider.previous_track()
