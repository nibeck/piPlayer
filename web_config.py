import os
import socket
import ssl
import subprocess
import threading
from pathlib import Path
from flask import Flask, request, redirect, url_for, render_template, flash

from spot import SpotifyManager

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


@app.route("/")
def index():
    mgr = SpotifyManager.get_instance()
    if mgr.is_authenticated():
        return redirect(url_for("status"))
    return redirect(url_for("setup"))


@app.route("/setup", methods=["GET", "POST"])
def setup():
    mgr = SpotifyManager.get_instance()

    if request.method == "POST":
        client_id = request.form.get("client_id", "").strip()
        client_secret = request.form.get("client_secret", "").strip()
        username = request.form.get("username", "").strip()
        redirect_uri = request.form.get("redirect_uri", "").strip()

        if not client_secret and mgr.client_secret:
            client_secret = mgr.client_secret

        if not redirect_uri:
            redirect_uri = f"https://{get_local_ip()}:5000/callback"

        if not all([client_id, client_secret, username]):
            flash("Client ID, Client Secret, and Username are all required.", "error")
            return redirect(url_for("setup"))

        mgr.save_credentials(client_id, client_secret, username, redirect_uri)
        flash("Credentials saved.", "success")
        return redirect(url_for("authorize"))

    local_ip = get_local_ip()
    default_redirect = f"http://{local_ip}:5000/callback"

    return render_template(
        "setup.html",
        client_id=mgr.client_id or "",
        client_secret=mgr.client_secret or "",
        has_secret=bool(mgr.client_secret),
        username=mgr.username or "",
        redirect_uri=mgr.redirect_uri or default_redirect,
        local_ip=local_ip,
        has_credentials=mgr.has_credentials(),
        authenticated=mgr.is_authenticated(),
        authorize_url=None,
    )


@app.route("/authorize")
def authorize():
    mgr = SpotifyManager.get_instance()
    if not mgr.has_credentials():
        flash("Enter your Spotify credentials first.", "error")
        return redirect(url_for("setup"))

    authorize_url = mgr.get_authorize_url()
    local_ip = get_local_ip()

    return render_template(
        "setup.html",
        client_id=mgr.client_id or "",
        client_secret="",
        has_secret=bool(mgr.client_secret),
        username=mgr.username or "",
        redirect_uri=mgr.redirect_uri or "",
        local_ip=local_ip,
        has_credentials=mgr.has_credentials(),
        authenticated=mgr.is_authenticated(),
        authorize_url=authorize_url,
    )


@app.route("/manual_callback", methods=["POST"])
def manual_callback():
    mgr = SpotifyManager.get_instance()
    callback_url = request.form.get("callback_url", "").strip()
    if "code=" not in callback_url:
        flash("No authorization code found in that URL.", "error")
        return redirect(url_for("authorize"))
    code = callback_url.split("code=", 1)[1].split("&")[0]
    try:
        if mgr.handle_callback(code):
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
    mgr = SpotifyManager.get_instance()
    error = request.args.get("error")
    if error:
        flash(f"Authorization denied: {error}", "error")
        return redirect(url_for("setup"))

    code = request.args.get("code")
    if not code:
        flash("Authorization failed: no code received.", "error")
        return redirect(url_for("setup"))

    try:
        if mgr.handle_callback(code):
            flash("Successfully connected to Spotify!", "success")
            return redirect(url_for("status"))
        else:
            flash("Authorization failed: could not get access token.", "error")
            return redirect(url_for("setup"))
    except Exception as e:
        flash(f"Authorization error: {e}", "error")
        return redirect(url_for("setup"))


@app.route("/status")
def status():
    mgr = SpotifyManager.get_instance()
    if not mgr.is_authenticated():
        flash("Not connected to Spotify yet.", "info")
        return redirect(url_for("setup"))

    display_name = None
    now_playing = None
    try:
        user_info = mgr.spotify.current_user()
        display_name = user_info.get("display_name", mgr.username)
    except Exception:
        display_name = mgr.username

    try:
        from spot import get_current_playing_info
        now_playing = get_current_playing_info()
    except Exception:
        pass

    return render_template(
        "status.html",
        display_name=display_name,
        now_playing=now_playing,
    )


@app.route("/health")
def health():
    mgr = SpotifyManager.get_instance()
    return {"status": "ok", "authenticated": mgr.is_authenticated()}


def _ensure_ssl_cert():
    cert_file = BASE_DIR / "cert.pem"
    key_file = BASE_DIR / "key.pem"
    if cert_file.exists() and key_file.exists():
        return str(cert_file), str(key_file)
    local_ip = get_local_ip()
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048",
        "-keyout", str(key_file), "-out", str(cert_file),
        "-days", "365", "-nodes",
        "-subj", f"/CN={local_ip}",
        "-addext", f"subjectAltName=IP:{local_ip},DNS:piPlayer,DNS:localhost",
    ], check=True, capture_output=True)
    return str(cert_file), str(key_file)


def run_flask(host="0.0.0.0", port=5000):
    cert, key = _ensure_ssl_cert()
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(cert, key)
    app.run(host=host, port=port, debug=False, use_reloader=False, ssl_context=ssl_ctx)


def start_flask_background(host="0.0.0.0", port=5000):
    t = threading.Thread(target=run_flask, args=(host, port), daemon=True)
    t.start()
    return t
