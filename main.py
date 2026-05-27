import pygame
import os
import random
import sys
import requests
import time
import math
import threading
from io import BytesIO
from providers import get_current_playing_info, start_music, stop_music, skip_to_next, skip_to_previous
from providers.manager import ProviderManager
from web_config import start_flask_background, get_local_ip, get_hostname
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def run(windowed=False):
    # Initialize Pygame
    pygame.init()

    # Skip audio mixer init — both Raspotify and shairport-sync handle their own audio
    # output, and pygame.mixer grabs the ALSA device exclusively, blocking them.
    mgr = ProviderManager.get_instance()
    active_provider = mgr.get_active()
    audio_available = False
    print("Skipping audio mixer init (music provider handles audio).", file=sys.stderr)
    flags = 0 if windowed else pygame.FULLSCREEN
    screen = pygame.display.set_mode((1080, 1080), flags)
    pygame.display.set_caption("piPlayer")
    # Hide mouse cursor (useful on touchscreens)
    pygame.mouse.set_visible(False)

    # Start web config server in the background
    start_flask_background()

    # Check active provider
    provider = mgr.get_active()
    hostname = get_hostname()
    if provider:
        if provider.get_id() == "spotify" and not provider.is_authenticated():
            print(f"Spotify not authenticated. Visit https://{hostname}:5001 to set up.", file=sys.stderr)
        elif provider.get_id() == "airplay":
            print("AirPlay mode active. Select this device as an AirPlay speaker.", file=sys.stderr)
    else:
        print(f"No music provider configured. Visit https://{hostname}:5001 to set up.", file=sys.stderr)

    # -------------------------------
    # Load & scale images (resources relative to script location)
    # -------------------------------
    record_dir = BASE_DIR / 'records'
    image_exts = {'.png', '.jpg', '.jpeg', '.bmp', '.gif'}
    record_files = [p for p in record_dir.iterdir() if p.is_file() and p.suffix.lower() in image_exts]
    random_record_path = random.choice(record_files)
    record_image = pygame.image.load(str(random_record_path))
    record_image = pygame.transform.scale(record_image, (int(1080 * 1.25), int(1080 * 1.25)))
    record_image = record_image.convert()  # convert to display format for faster blitting

    icons_dir = BASE_DIR / 'assets'
    play_btn  = pygame.image.load(str(icons_dir / 'play.png'))
    pause_btn = pygame.image.load(str(icons_dir / 'pause.png'))
    skip_btn  = pygame.image.load(str(icons_dir / 'skip.png'))
    prev_btn  = pygame.image.load(str(icons_dir / 'previous.png'))

    # Load provider logo for center of spinning record
    current_provider_id = active_provider.get_id() if active_provider else None

    def load_provider_logo(provider_id):
        """Load the logo for the given provider, or return None."""
        if not provider_id:
            return None
        if provider_id == "airplay":
            logo_file = icons_dir / "logo_apple_music.png"
        elif provider_id == "spotify":
            logo_file = icons_dir / "logo_spotify.png"
        else:
            logo_file = icons_dir / f"logo_{provider_id.replace(' ', '_')}.png"
        if logo_file.exists():
            logo = pygame.image.load(str(logo_file)).convert_alpha()
            return pygame.transform.scale(logo, (150, 150))
        return None

    provider_logo = load_provider_logo(current_provider_id)

    font = pygame.font.Font(None, 40)

    # -------------------------------
    # Load scratch sound effects
    # -------------------------------
    scratch_sounds = []
    if audio_available:
        sfx_dir = BASE_DIR / 'sfx'
        sfx_paths = [p for p in sfx_dir.iterdir() if p.is_file() and p.suffix.lower() == '.wav']
        scratch_sounds = [pygame.mixer.Sound(str(path)) for path in sfx_paths]

    # -------------------------------
    # State variables
    # -------------------------------
    clock = pygame.time.Clock()
    center = (540, 540)
    angle = 0
    angle_speed = -0.5
    is_playing = True
    dragging = False
    last_mouse_pos = None
    details = None
    album_img = None

    # Rotation cache — only re-rotate when the quantized angle changes
    cached_record_angle = None
    cached_record_surface = None
    cached_logo_angle = None
    cached_logo_surface = None

    # Helper to fetch and update track details and album image
    def update_details():
        nonlocal details, album_img
        try:
            new_details = get_current_playing_info()
        except Exception as e:
            print(f"Error fetching current playing info: {e}", file=sys.stderr)
            return
        if new_details:
            details = new_details
            try:
                art = details.get("album_art")
                if art is None:
                    pass  # keep existing album_img
                elif isinstance(art, bytes):
                    # Binary data from shairport-sync
                    img = pygame.image.load(BytesIO(art))
                    album_img = pygame.transform.scale(img, (137, 137))
                elif isinstance(art, str):
                    # URL from Spotify
                    r = requests.get(art)
                    img = pygame.image.load(BytesIO(r.content))
                    album_img = pygame.transform.scale(img, (137, 137))
            except Exception as e:
                print(f"Error loading album cover: {e}", file=sys.stderr)

    # Initial fetch of details
    update_details()

    # Background thread to periodically update details and detect provider changes
    def details_thread():
        nonlocal provider_logo, current_provider_id, details, album_img
        while True:
            time.sleep(5)
            try:
                # Check if provider changed via web UI
                new_id = mgr.get_active_id()
                if new_id != current_provider_id:
                    print(f"Provider changed: {current_provider_id} → {new_id}", file=sys.stderr)
                    current_provider_id = new_id
                    provider_logo = load_provider_logo(new_id)
                    details = None
                    album_img = None

                update_details()
            except Exception as e:
                print(f"Error in details_thread: {e}", file=sys.stderr)

    threading.Thread(target=details_thread, daemon=True).start()

    # Swipe detection
    swipe_start_pos = None
    swipe_start_time = None
    SWIPE_DIST  = 100    # Minimum pixels moved
    SWIPE_TIME  = 0.5

    while True:

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            # Exit on ESC
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return

            # Mouse down: record swipe start & handle clicks
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                swipe_start_pos = event.pos
                swipe_start_time = time.time()
                mx, my = event.pos

                # Compute control positions (must match drawing code)
                ctrl_box_h = 90
                ctrl_box_y = 1080 - 100 - ctrl_box_h  # edge_margin=100
                prev_w, prev_h   = prev_btn.get_width(), prev_btn.get_height()
                pause_w, pause_h = pause_btn.get_width(), pause_btn.get_height()
                skip_w, skip_h   = skip_btn.get_width(), skip_btn.get_height()

                btn_gap = 60
                btns_width = prev_w + pause_w + skip_w + (2 * btn_gap)
                btns_start_x = (1080 - btns_width) // 2
                ctrl_center_y = ctrl_box_y + ctrl_box_h // 2

                prev_x  = btns_start_x
                prev_y  = ctrl_center_y - prev_h // 2
                pause_x = prev_x + prev_w + btn_gap
                pause_y = ctrl_center_y - pause_h // 2
                skip_x  = pause_x + pause_w + btn_gap
                skip_y  = ctrl_center_y - skip_h // 2

                # Previous track
                if prev_x <= mx <= prev_x + prev_w and prev_y <= my <= prev_y + prev_h:
                    try:
                        skip_to_previous()
                    except Exception as e:
                        print(f"Error skipping to previous track: {e}", file=sys.stderr)
                    else:
                        threading.Thread(target=update_details, daemon=True).start()

                # Play/pause toggle
                elif pause_x <= mx <= pause_x + pause_w and pause_y <= my <= pause_y + pause_h:
                    if is_playing:
                        try:
                            stop_music()
                        except Exception as e:
                            print(f"Error stopping music: {e}", file=sys.stderr)
                        else:
                            is_playing = False
                            angle_speed = 0
                    else:
                        try:
                            start_music()
                        except Exception as e:
                            print(f"Error starting music: {e}", file=sys.stderr)
                        else:
                            is_playing = True
                            angle_speed = -0.5

                # Next track & load new record art
                elif skip_x <= mx <= skip_x + skip_w and skip_y <= my <= skip_y + skip_h:
                    try:
                        skip_to_next()
                    except Exception as e:
                        print(f"Error skipping to next track: {e}", file=sys.stderr)
                    else:
                        new_path = random.choice(record_files)
                        record_image = pygame.image.load(str(new_path))
                        record_image = pygame.transform.scale(record_image, (int(1080 * 1.25), int(1080 * 1.25)))
                        record_image = record_image.convert()
                        cached_record_angle = None  # force re-rotation
                        threading.Thread(target=update_details, daemon=True).start()

                # Otherwise, start dragging if click on record
                else:
                    if math.hypot(mx - center[0], my - center[1]) <= 540:
                        dragging = True
                        last_mouse_pos = event.pos

            # Mouse up: check for swipe & stop dragging
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if swipe_start_pos and swipe_start_time:
                    dx = event.pos[0] - swipe_start_pos[0]
                    dy = event.pos[1] - swipe_start_pos[1]
                    dist = math.hypot(dx, dy)
                    elapsed = time.time() - swipe_start_time
                    if dist > SWIPE_DIST and elapsed < SWIPE_TIME and scratch_sounds:
                        random.choice(scratch_sounds).play()

                dragging = False
                swipe_start_pos = None
                swipe_start_time = None

            # Dragging motion rotates the record
            elif event.type == pygame.MOUSEMOTION and dragging:
                dx = event.pos[0] - last_mouse_pos[0]
                angle -= dx * 0.1
                angle %= 360
                last_mouse_pos = event.pos

        # -------------------------------
        # Drawing
        # -------------------------------
        screen.fill((245, 230, 200))

        # Spinning record — only re-rotate when angle changes by 1°
        display_angle = round(angle) % 360
        if display_angle != cached_record_angle:
            cached_record_surface = pygame.transform.rotate(record_image, display_angle)
            cached_record_angle = display_angle
        screen.blit(cached_record_surface, cached_record_surface.get_rect(center=center))

        # Provider logo spinning at center of record
        if provider_logo:
            if display_angle != cached_logo_angle:
                cached_logo_surface = pygame.transform.rotate(provider_logo, display_angle)
                cached_logo_angle = display_angle
            screen.blit(cached_logo_surface, cached_logo_surface.get_rect(center=center))

        if is_playing:
            angle = (angle + angle_speed) % 360

        # --- Layout: symmetrical top/bottom boxes ---
        edge_margin = 100  # distance from screen edge
        ctrl_box_h = 90
        meta_box_h = 120
        ctrl_box_y = 1080 - edge_margin - ctrl_box_h  # bottom box
        meta_box_y = edge_margin                        # top box (mirrored)

        # --- Metadata box (album art + song info) ---
        meta_box_x = 60
        meta_box_w = 1080 - 120
        meta_surface = pygame.Surface((meta_box_w, meta_box_h), pygame.SRCALPHA)
        meta_surface.fill((0, 0, 0, 160))
        screen.blit(meta_surface, (meta_box_x, meta_box_y))

        album_w, album_h = (100, 100) if album_img else (0, 0)
        art_text_gap = 15

        # Pre-render text to measure widths for centering
        song_surf = None
        artist_surf = None
        text_block_w = 0
        if details:
            song_surf   = font.render(details["title"],  True, (255, 255, 255))
            artist_surf = font.render(details["artist"], True, (200, 200, 200))
            text_block_w = max(song_surf.get_width(), artist_surf.get_width())

        # Calculate total content width and center it
        content_w = album_w + (art_text_gap if album_img and text_block_w else 0) + text_block_w
        content_x = meta_box_x + (meta_box_w - content_w) // 2

        album_x = content_x
        album_y = meta_box_y + (meta_box_h - album_h) // 2

        if album_img:
            scaled_album = pygame.transform.scale(album_img, (album_w, album_h))
            screen.blit(scaled_album, (album_x, album_y))

        if details and song_surf and artist_surf:
            text_x = album_x + album_w + art_text_gap if album_img else content_x
            text_max_w = meta_box_x + meta_box_w - text_x - 15
            # Clip text if too wide
            if song_surf.get_width() > text_max_w:
                song_surf = song_surf.subsurface((0, 0, text_max_w, song_surf.get_height()))
            if artist_surf.get_width() > text_max_w:
                artist_surf = artist_surf.subsurface((0, 0, text_max_w, artist_surf.get_height()))
            text_total_h = song_surf.get_height() + 4 + artist_surf.get_height()
            text_y = meta_box_y + (meta_box_h - text_total_h) // 2
            screen.blit(song_surf,   (text_x, text_y))
            screen.blit(artist_surf, (text_x, text_y + song_surf.get_height() + 4))

        # --- Controls box (playback buttons) ---
        ctrl_box_x = 60
        ctrl_box_w = 1080 - 120
        ctrl_surface = pygame.Surface((ctrl_box_w, ctrl_box_h), pygame.SRCALPHA)
        ctrl_surface.fill((0, 0, 0, 160))
        screen.blit(ctrl_surface, (ctrl_box_x, ctrl_box_y))

        prev_w, prev_h   = prev_btn.get_width(), prev_btn.get_height()
        pause_w, pause_h = pause_btn.get_width(), pause_btn.get_height()
        skip_w, skip_h   = skip_btn.get_width(), skip_btn.get_height()

        btn_gap = 60
        btns_width = prev_w + pause_w + skip_w + (2 * btn_gap)
        btns_start_x = (1080 - btns_width) // 2
        ctrl_center_y = ctrl_box_y + ctrl_box_h // 2

        prev_x  = btns_start_x
        prev_y  = ctrl_center_y - prev_h // 2
        pause_x = prev_x + prev_w + btn_gap
        pause_y = ctrl_center_y - pause_h // 2
        skip_x  = pause_x + pause_w + btn_gap
        skip_y  = ctrl_center_y - skip_h // 2

        screen.blit(prev_btn,  (prev_x,  prev_y))
        screen.blit(pause_btn if is_playing else play_btn, (pause_x, pause_y))
        screen.blit(skip_btn,  (skip_x,  skip_y))

        pygame.display.flip()
        clock.tick(30)  # cap at 30 FPS — plenty for a spinning record

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="piPlayer")
    parser.add_argument('--windowed', action='store_true', help='Run in windowed mode (no fullscreen)')
    args = parser.parse_args()
    run(windowed=args.windowed)
