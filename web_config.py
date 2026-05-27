import os
import socket
import ssl
import subprocess
import threading
from pathlib import Path
from flask import Flask, request, redirect, url_for, render_template, flash

from providers.manager import ProviderManager
from providers.spotify_provider import SpotifyManager

BASE_DIR = Path(__file__).resolve().parent

app = Flask(__name__, template_folder=str(BASE_DIR / 'templates'))
app.secret_key = os.urandom(24)


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def get_hostname():
    """Return the mDNS hostname (e.g. 'pi-player.local') for network-agnostic access."""
    try:
        hostname = socket.gethostname()
        if not hostname.endswith(".local"):
            hostname += ".local"
        return hostname
    except Exception:
        return "localhost"


# --- Provider selection ---

@app.route("/")
def index():
    mgr = ProviderManager.get_instance()
    provider = mgr.get_active()
    if provider and provider.is_authenticated() and provider.get_id() == "spotify":
        return redirect(url_for("status"))
    return redirect(url_for("setup"))


@app.route("/setup")
def setup():
    mgr = ProviderManager.get_instance()
    spotify = mgr.get_provider("spotify")
    airplay = mgr.get_provider("airplay")
    active_id = mgr.get_active_id()

    airplay_status = {"installed": False, "running": False, "pipe_exists": False, "device_name": "Unknown"}
    if airplay:
        airplay_status = airplay.get_service_status()

    spotify_authenticated = spotify.is_authenticated() if spotify else False

    return render_template(
        "setup.html",
        active_provider=active_id,
        spotify_authenticated=spotify_authenticated,
        airplay_status=airplay_status,
    )


@app.route("/select/<provider_id>")
def select_provider(provider_id):
    mgr = ProviderManager.get_instance()
    if provider_id not in ["spotify", "airplay"]:
        flash("Unknown provider.", "error")
        return redirect(url_for("setup"))

    mgr.set_active(provider_id)
    flash(f"Switched to {mgr.get_active().get_name()}.", "success")

    if provider_id == "spotify":
        return redirect(url_for("setup_spotify"))
    else:
        return redirect(url_for("setup_airplay"))


# --- Spotify-specific routes ---

@app.route("/setup/spotify", methods=["GET", "POST"])
def setup_spotify():
    sm = SpotifyManager.get_instance()

    if request.method == "POST":
        client_id = request.form.get("client_id", "").strip()
        client_secret = request.form.get("client_secret", "").strip()
        username = request.form.get("username", "").strip()
        redirect_uri = request.form.get("redirect_uri", "").strip()

        if not client_secret and sm.client_secret:
            client_secret = sm.client_secret

        if not redirect_uri:
            redirect_uri = f"https://{get_hostname()}:5001/callback"

        if not all([client_id, client_secret, username]):
            flash("Client ID, Client Secret, and Username are all required.", "error")
            return redirect(url_for("setup_spotify"))

        sm.save_credentials(client_id, client_secret, username, redirect_uri)
        flash("Credentials saved.", "success")
        return redirect(url_for("authorize"))

    hostname = get_hostname()
    default_redirect = f"https://{hostname}:5001/callback"

    return render_template(
        "setup_spotify.html",
        client_id=sm.client_id or "",
        client_secret=sm.client_secret or "",
        has_secret=bool(sm.client_secret),
        username=sm.username or "",
        redirect_uri=sm.redirect_uri or default_redirect,
        hostname=hostname,
        has_credentials=sm.has_credentials(),
        authenticated=sm.is_authenticated(),
        authorize_url=None,
    )


@app.route("/authorize")
def authorize():
    sm = SpotifyManager.get_instance()
    if not sm.has_credentials():
        flash("Enter your Spotify credentials first.", "error")
        return redirect(url_for("setup_spotify"))

    authorize_url = sm.get_authorize_url()
    hostname = get_hostname()

    return render_template(
        "setup_spotify.html",
        client_id=sm.client_id or "",
        client_secret="",
        has_secret=bool(sm.client_secret),
        username=sm.username or "",
        redirect_uri=sm.redirect_uri or "",
        hostname=hostname,
        has_credentials=sm.has_credentials(),
        authenticated=sm.is_authenticated(),
        authorize_url=authorize_url,
    )


@app.route("/manual_callback", methods=["POST"])
def manual_callback():
    sm = SpotifyManager.get_instance()
    callback_url = request.form.get("callback_url", "").strip()
    if "code=" not in callback_url:
        flash("No authorization code found in that URL.", "error")
        return redirect(url_for("authorize"))
    code = callback_url.split("code=", 1)[1].split("&")[0]
    try:
        if sm.handle_callback(code):
            flash("Successfully connected to Spotify!", "success")
            return redirect(url_for("status"))
        else:
            flash("Authorization failed: could not get access token.", "error")
            return redirect(url_for("authorize"))
    except Exception as e:
        flash(f"Authorization error: {e}", "error")
        return redirect(url_for("authorize"))


@app.route("/callback")
def callback():
    sm = SpotifyManager.get_instance()
    error = request.args.get("error")
    if error:
        flash(f"Authorization denied: {error}", "error")
        return redirect(url_for("setup_spotify"))

    code = request.args.get("code")
    if not code:
        flash("Authorization failed: no code received.", "error")
        return redirect(url_for("setup_spotify"))

    try:
        if sm.handle_callback(code):
            flash("Successfully connected to Spotify!", "success")
            return redirect(url_for("status"))
        else:
            flash("Authorization failed: could not get access token.", "error")
            return redirect(url_for("setup_spotify"))
    except Exception as e:
        flash(f"Authorization error: {e}", "error")
        return redirect(url_for("setup_spotify"))


# --- AirPlay-specific routes ---

@app.route("/setup/airplay")
def setup_airplay():
    mgr = ProviderManager.get_instance()
    airplay = mgr.get_provider("airplay")
    status = airplay.get_service_status() if airplay else {}

    return render_template(
        "setup_airplay.html",
        status=status,
    )


# --- Provider-agnostic routes ---

@app.route("/status")
def status():
    mgr = ProviderManager.get_instance()
    provider = mgr.get_active()
    if not provider:
        flash("No music provider configured.", "info")
        return redirect(url_for("setup"))

    display_name = None
    now_playing = None
    provider_name = provider.get_name()
    provider_id = provider.get_id()

    if provider_id == "spotify" and provider.is_authenticated():
        try:
            user_info = provider.manager.spotify.current_user()
            display_name = user_info.get("display_name", provider.manager.username)
        except Exception:
            display_name = provider.manager.username

    try:
        now_playing = provider.get_current_playing_info()
    except Exception:
        pass

    return render_template(
        "status.html",
        provider_name=provider_name,
        provider_id=provider_id,
        display_name=display_name,
        now_playing=now_playing,
    )


@app.route("/health")
def health():
    mgr = ProviderManager.get_instance()
    provider = mgr.get_active()
    return {
        "status": "ok",
        "provider": provider.get_id() if provider else None,
        "authenticated": provider.is_authenticated() if provider else False,
    }


# --- SSL and server ---

def _ensure_ssl_cert():
    cert_file = BASE_DIR / "cert.pem"
    key_file = BASE_DIR / "key.pem"
    if cert_file.exists() and key_file.exists():
        return str(cert_file), str(key_file)
    local_ip = get_local_ip()
    hostname = get_hostname()
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048",
        "-keyout", str(key_file), "-out", str(cert_file),
        "-days", "365", "-nodes",
        "-subj", f"/CN={hostname}",
        "-addext", f"subjectAltName=IP:{local_ip},DNS:{hostname},DNS:piPlayer,DNS:localhost",
    ], check=True, capture_output=True)
    return str(cert_file), str(key_file)


def run_flask(host="0.0.0.0", port=5001):
    cert, key = _ensure_ssl_cert()
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(cert, key)
    app.run(host=host, port=port, debug=False, use_reloader=False, ssl_context=ssl_ctx)


def start_flask_background(host="0.0.0.0", port=5001):
    t = threading.Thread(target=run_flask, args=(host, port), daemon=True)
    t.start()
    return t
