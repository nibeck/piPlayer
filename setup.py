#!/usr/bin/env python3
"""Standalone setup server for piPlayer.
Run this for initial Spotify configuration before starting the player.
"""
import argparse
from web_config import run_flask, get_local_ip


def main():
    parser = argparse.ArgumentParser(description="piPlayer Setup Server")
    parser.add_argument("--port", type=int, default=5000, help="Port to run on (default: 5000)")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    args = parser.parse_args()

    ip = get_local_ip()
    print(f"piPlayer Setup Server")
    print(f"Open https://{ip}:{args.port} in your browser to configure Spotify.")
    print(f"(You'll see a certificate warning — click through it, the connection is still encrypted.)")
    print(f"Press Ctrl+C to stop.")
    run_flask(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
