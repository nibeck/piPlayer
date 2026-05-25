import base64
import os
import re
import select
import shutil
import subprocess
import threading
import sys

from .base import MusicProvider

METADATA_PIPE = "/tmp/shairport-sync-metadata"


class AirPlayProvider(MusicProvider):
    """Apple Music / AirPlay implementation using shairport-sync."""

    def __init__(self):
        self._lock = threading.Lock()
        self._current_track = {}
        self._album_art_bytes = None
        self._connected = False
        self._playing = False
        self._reader_thread = None
        self._stop_event = threading.Event()

    def get_name(self):
        return "Apple Music"

    def get_id(self):
        return "airplay"

    def needs_credentials(self):
        return False

    def has_credentials(self):
        return True

    def is_authenticated(self):
        return True

    def is_active(self):
        return self._connected

    def get_current_playing_info(self):
        with self._lock:
            if not self._current_track.get("title"):
                return None
            return {
                "title": self._current_track.get("title", ""),
                "artist": self._current_track.get("artist", ""),
                "album": self._current_track.get("album", ""),
                "album_art": self._album_art_bytes,
            }

    def start_playback(self):
        return self._dbus_command("Play")

    def stop_playback(self):
        return self._dbus_command("Pause")

    def next_track(self):
        return self._dbus_command("Next")

    def previous_track(self):
        return self._dbus_command("Previous")

    def start(self):
        self._stop_event.clear()
        if self._reader_thread is None or not self._reader_thread.is_alive():
            self._reader_thread = threading.Thread(
                target=self._metadata_reader_loop, daemon=True
            )
            self._reader_thread.start()

    def stop(self):
        self._stop_event.set()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=3)
            self._reader_thread = None
        with self._lock:
            self._current_track = {}
            self._album_art_bytes = None
            self._connected = False
            self._playing = False

    def _dbus_command(self, method):
        try:
            subprocess.run(
                [
                    "dbus-send", "--system",
                    "--type=method_call",
                    "--dest=org.gnome.ShairportSync",
                    "/org/gnome/ShairportSync",
                    f"org.gnome.ShairportSync.RemoteControl.{method}",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            return None
        except FileNotFoundError:
            return "dbus-send not found"
        except subprocess.CalledProcessError as e:
            return f"D-Bus error: {e.stderr.strip()}"

    def _metadata_reader_loop(self):
        """Continuously read the shairport-sync metadata pipe."""
        while not self._stop_event.is_set():
            if not os.path.exists(METADATA_PIPE):
                print(
                    f"Metadata pipe {METADATA_PIPE} not found, retrying in 5s...",
                    file=sys.stderr,
                )
                self._stop_event.wait(5)
                continue

            try:
                fd = os.open(METADATA_PIPE, os.O_RDONLY | os.O_NONBLOCK)
                pipe = os.fdopen(fd, "rb")
            except OSError as e:
                print(f"Error opening metadata pipe: {e}", file=sys.stderr)
                self._stop_event.wait(5)
                continue

            try:
                self._read_pipe(pipe)
            except Exception as e:
                print(f"Metadata pipe error: {e}", file=sys.stderr)
            finally:
                try:
                    pipe.close()
                except OSError:
                    pass

            if not self._stop_event.is_set():
                self._stop_event.wait(2)

    def _read_pipe(self, pipe):
        """Parse the metadata stream from shairport-sync."""
        buffer = b""

        while not self._stop_event.is_set():
            ready, _, _ = select.select([pipe], [], [], 1.0)
            if not ready:
                continue

            try:
                chunk = pipe.read(65536)
            except OSError:
                break

            if not chunk:
                break

            buffer += chunk
            buffer = self._process_buffer(buffer)

    def _process_buffer(self, buffer):
        """Extract complete <item>...</item> blocks from the buffer."""
        while True:
            start = buffer.find(b"<item>")
            end = buffer.find(b"</item>")

            if start == -1 or end == -1 or end < start:
                break

            item_data = buffer[start:end + len(b"</item>")]
            buffer = buffer[end + len(b"</item>"):]
            self._parse_item(item_data)

        # Prevent unbounded buffer growth
        if len(buffer) > 1048576:
            buffer = buffer[-65536:]

        return buffer

    def _parse_item(self, item_data):
        """Parse a single metadata item and update state."""
        try:
            text = item_data.decode("utf-8", errors="replace")
        except Exception:
            return

        type_match = re.search(r"<type>(.*?)</type>", text)
        code_match = re.search(r"<code>(.*?)</code>", text)
        data_match = re.search(r"<data encoding=\"base64\">(.*?)</data>", text, re.DOTALL)

        if not type_match or not code_match:
            return

        # Type and code are hex-encoded ASCII (e.g., "636f7265" → "core")
        item_type_hex = type_match.group(1).strip()
        item_code_hex = code_match.group(1).strip()
        try:
            item_type = bytes.fromhex(item_type_hex).decode("ascii")
        except (ValueError, UnicodeDecodeError):
            item_type = item_type_hex
        try:
            item_code = bytes.fromhex(item_code_hex).decode("ascii")
        except (ValueError, UnicodeDecodeError):
            item_code = item_code_hex

        data_bytes = None
        if data_match:
            try:
                raw = data_match.group(1).strip()
                data_bytes = base64.b64decode(raw)
            except Exception:
                data_bytes = None

        self._handle_metadata(item_type, item_code, data_bytes)

    def _handle_metadata(self, item_type, item_code, data_bytes):
        """Update internal state based on metadata type/code."""
        with self._lock:
            if item_type == "ssnc":
                if item_code == "pbeg":
                    self._connected = True
                elif item_code == "pend":
                    self._connected = False
                    self._playing = False
                    self._current_track = {}
                    self._album_art_bytes = None
                elif item_code == "prsm":
                    self._playing = True
                elif item_code == "pfls":
                    self._playing = False
                elif item_code == "PICT" and data_bytes:
                    self._album_art_bytes = data_bytes
            elif item_type == "core":
                if item_code == "minm" and data_bytes:
                    self._current_track["title"] = data_bytes.decode("utf-8", errors="replace")
                elif item_code == "asar" and data_bytes:
                    self._current_track["artist"] = data_bytes.decode("utf-8", errors="replace")
                elif item_code == "asal" and data_bytes:
                    self._current_track["album"] = data_bytes.decode("utf-8", errors="replace")

    def get_service_status(self):
        """Return shairport-sync service status for the web config UI."""
        installed = shutil.which("shairport-sync") is not None
        running = False
        if installed:
            result = subprocess.run(
                ["systemctl", "is-active", "shairport-sync"],
                capture_output=True,
                text=True,
            )
            running = result.stdout.strip() == "active"
        pipe_exists = os.path.exists(METADATA_PIPE)
        device_name = self._get_device_name()
        return {
            "installed": installed,
            "running": running,
            "pipe_exists": pipe_exists,
            "device_name": device_name,
        }

    def _get_device_name(self):
        """Read the AirPlay device name from shairport-sync config."""
        conf_path = "/etc/shairport-sync.conf"
        try:
            if os.path.exists(conf_path):
                content = open(conf_path).read()
                match = re.search(r'name\s*=\s*"([^"]+)"', content)
                if match:
                    return match.group(1)
        except Exception:
            pass
        try:
            return subprocess.check_output(["hostname"], text=True).strip()
        except Exception:
            return "Unknown"
