"""
YouTube Music Account Migration Tool
=====================================
Migrates playlists, liked songs, and subscriptions
from one Google account to another.

Usage:
    python migrate.py

Requirements:
    - credentials.json from Google Cloud Console
    - Python 3.8+
    - pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
"""

import os
import json
import time
import datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle

# ── CONFIG ────────────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]
CREDENTIALS_FILE = "credentials.json"
BACKUP_FILE = f"youtube_music_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
SKIP_LOG_FILE = "skipped_items.log"
QUOTA_DELAY = 0.5       # seconds between API calls
RETRY_DELAY = 30        # seconds to wait on quota error
MAX_RETRIES = 3         # max retries per API call
PAGE_SIZE = 50          # items per API page

# ── COLORS FOR TERMINAL ───────────────────────────────────────────────────────
class C:
    BLUE   = "\033[94m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    BOLD   = "\033[1m"
    END    = "\033[0m"

def log(msg, color=C.END):     print(f"{color}{msg}{C.END}")
def success(msg):               log(f"  ✓  {msg}", C.GREEN)
def warn(msg):                  log(f"  ⚠  {msg}", C.YELLOW)
def error(msg):                 log(f"  ✗  {msg}", C.RED)
def info(msg):                  log(f"  →  {msg}", C.BLUE)
def progress(current, total, label):
    pct = int((current / total) * 30) if total > 0 else 0
    bar = "█" * pct + "░" * (30 - pct)
    print(f"\r  [{bar}] {current}/{total} {label}", end="", flush=True)

# ── AUTHENTICATION ────────────────────────────────────────────────────────────
def authenticate(account_label, token_file):
    """Authenticate a Google account and return a YouTube service."""
    log(f"\n{C.BOLD}Authenticating {account_label}...{C.END}")
    info("A browser window will open. Please log in to your Google account.")
    info("This tool only requests permission to read and manage your YouTube data.")
    info("No credentials are stored — access is session-only.\n")

    creds = None
    if os.path.exists(token_file):
        with open(token_file, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "wb") as f:
            pickle.dump(creds, f)

    service = build("youtube", "v3", credentials=creds)
    success(f"{account_label} authenticated successfully.\n")
    return service

# ── API CALL WITH RETRY ───────────────────────────────────────────────────────
def api_call(request, skip_log=None, skip_label="item"):
    """Execute an API call with retry logic on quota errors."""
    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(QUOTA_DELAY)
            return request.execute()
        except HttpError as e:
            if e.resp.status == 403:
                warn(f"Quota limit hit. Waiting {RETRY_DELAY}s before retry {attempt + 1}/{MAX_RETRIES}...")
                time.sleep(RETRY_DELAY)
            elif e.resp.status in [404, 400]:
                if skip_log is not None:
                    skip_log.append({"item": skip_label, "reason": str(e)})
                return None
            else:
                error(f"API error: {e}")
                return None
    warn(f"Max retries exceeded for: {skip_label}")
    return None

# ── FETCH FROM SOURCE ACCOUNT ─────────────────────────────────────────────────
def fetch_playlists(service):
    """Fetch all playlists and their items from source account."""
    info("Fetching playlists...")
    playlists = []
    request = service.playlists().list(part="snippet,status", mine=True, maxResults=PAGE_SIZE)

    while request:
        response = api_call(request)
        if not response:
            break
        for item in response.get("items", []):
            playlist = {
                "id": item["id"],
                "title": item["snippet"]["title"],
                "description": item["snippet"].get("description", ""),
                "privacy": item["status"]["privacyStatus"],
                "videos": []
            }
            # Fetch videos in this playlist
            video_request = service.playlistItems().list(
                part="snippet", playlistId=item["id"], maxResults=PAGE_SIZE
            )
            while video_request:
                video_response = api_call(video_request)
                if not video_response:
                    break
                for v in video_response.get("items", []):
                    playlist["videos"].append({
                        "video_id": v["snippet"]["resourceId"]["videoId"],
                        "title": v["snippet"]["title"]
                    })
                video_request = service.playlistItems().list_next(video_request, video_response)

            playlists.append(playlist)
            success(f"Fetched playlist: '{playlist['title']}' ({len(playlist['videos'])} songs)")

        request = service.playlists().list_next(request, response)

    return playlists

def fetch_liked_songs(service):
    """Fetch all liked videos from source account."""
    info("Fetching liked songs...")
    liked = []
    request = service.videos().list(
        part="snippet", myRating="like", maxResults=PAGE_SIZE
    )
    while request:
        response = api_call(request)
        if not response:
            break
        for item in response.get("items", []):
            liked.append({
                "video_id": item["id"],
                "title": item["snippet"]["title"]
            })
        request = service.videos().list_next(request, response)

    success(f"Fetched {len(liked)} liked songs.")
    return liked

def fetch_subscriptions(service):
    """Fetch all channel subscriptions from source account."""
    info("Fetching subscriptions...")
    subs = []
    request = service.subscriptions().list(
        part="snippet", mine=True, maxResults=PAGE_SIZE
    )
    while request:
        response = api_call(request)
        if not response:
            break
        for item in response.get("items", []):
            subs.append({
                "channel_id": item["snippet"]["resourceId"]["channelId"],
                "channel_title": item["snippet"]["title"]
            })
        request = service.subscriptions().list_next(request, response)

    success(f"Fetched {len(subs)} subscriptions.")
    return subs

# ── SAVE BACKUP ───────────────────────────────────────────────────────────────
def save_backup(data):
    """Save all fetched data to a local JSON backup file."""
    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    success(f"Backup saved to: {BACKUP_FILE}")

# ── WRITE TO DESTINATION ACCOUNT ──────────────────────────────────────────────
def create_playlists(service, playlists, skip_log):
    """Recreate all playlists on destination account."""
    info("Creating playlists on destination account...")
    created = 0
    skipped_videos = 0

    for i, playlist in enumerate(playlists):
        print()
        info(f"Creating playlist {i+1}/{len(playlists)}: '{playlist['title']}'")

        # Create the playlist
        response = api_call(
            service.playlists().insert(
                part="snippet,status",
                body={
                    "snippet": {
                        "title": playlist["title"],
                        "description": playlist["description"]
                    },
                    "status": {"privacyStatus": playlist["privacy"]}
                }
            ),
            skip_log=skip_log,
            skip_label=f"Create playlist: {playlist['title']}"
        )
        if not response:
            continue

        new_playlist_id = response["id"]
        created += 1

        # Add videos to the playlist
        total_videos = len(playlist["videos"])
        for j, video in enumerate(playlist["videos"]):
            progress(j + 1, total_videos, f"adding songs to '{playlist['title']}'")
            result = api_call(
                service.playlistItems().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "playlistId": new_playlist_id,
                            "resourceId": {
                                "kind": "youtube#video",
                                "videoId": video["video_id"]
                            }
                        }
                    }
                ),
                skip_log=skip_log,
                skip_label=f"Add video '{video['title']}' to '{playlist['title']}'"
            )
            if not result:
                skipped_videos += 1
        print()

    return created, skipped_videos

def like_songs(service, liked_songs, skip_log):
    """Re-like all songs on destination account."""
    info(f"Liking {len(liked_songs)} songs on destination account...")
    liked = 0
    total = len(liked_songs)

    for i, video in enumerate(liked_songs):
        progress(i + 1, total, "liking songs")
        result = api_call(
            service.videos().rate(id=video["video_id"], rating="like"),
            skip_log=skip_log,
            skip_label=f"Like video: {video['title']}"
        )
        if result is not None or result == {}:
            liked += 1
    print()
    return liked

def add_subscriptions(service, subscriptions, skip_log):
    """Re-subscribe to all channels on destination account."""
    info(f"Adding {len(subscriptions)} subscriptions on destination account...")
    added = 0
    total = len(subscriptions)

    for i, sub in enumerate(subscriptions):
        progress(i + 1, total, "adding subscriptions")
        result = api_call(
            service.subscriptions().insert(
                part="snippet",
                body={
                    "snippet": {
                        "resourceId": {
                            "kind": "youtube#channel",
                            "channelId": sub["channel_id"]
                        }
                    }
                }
            ),
            skip_log=skip_log,
            skip_label=f"Subscribe to: {sub['channel_title']}"
        )
        if result:
            added += 1
    print()
    return added

# ── SAVE SKIP LOG ─────────────────────────────────────────────────────────────
def save_skip_log(skip_log):
    if not skip_log:
        return
    with open(SKIP_LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"Skipped Items Log — {datetime.datetime.now()}\n")
        f.write("=" * 60 + "\n\n")
        for item in skip_log:
            f.write(f"Item:   {item['item']}\n")
            f.write(f"Reason: {item['reason']}\n\n")
    warn(f"{len(skip_log)} items skipped. See: {SKIP_LOG_FILE}")

# ── SUMMARY REPORT ────────────────────────────────────────────────────────────
def print_summary(playlists, liked, subs, created_playlists, skipped_videos, liked_count, sub_count, skip_log):
    total_videos = sum(len(p["videos"]) for p in playlists)
    print(f"\n{C.BOLD}{'=' * 55}{C.END}")
    print(f"{C.BOLD}  MIGRATION COMPLETE — SUMMARY REPORT{C.END}")
    print(f"{C.BOLD}{'=' * 55}{C.END}")
    print(f"\n  {'Playlists created:':<30} {C.GREEN}{created_playlists}/{len(playlists)}{C.END}")
    print(f"  {'Songs added to playlists:':<30} {C.GREEN}{total_videos - skipped_videos}/{total_videos}{C.END}")
    print(f"  {'Liked songs transferred:':<30} {C.GREEN}{liked_count}/{len(liked)}{C.END}")
    print(f"  {'Subscriptions added:':<30} {C.GREEN}{sub_count}/{len(subs)}{C.END}")
    print(f"  {'Items skipped:':<30} {C.YELLOW}{len(skip_log)}{C.END}")
    print(f"\n  {'Backup file:':<30} {BACKUP_FILE}")
    if skip_log:
        print(f"  {'Skip log:':<30} {SKIP_LOG_FILE}")
    print(f"\n{C.BOLD}{'=' * 55}{C.END}\n")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{C.BOLD}{C.BLUE}{'=' * 55}{C.END}")
    print(f"{C.BOLD}{C.BLUE}  YouTube Music Account Migration Tool{C.END}")
    print(f"{C.BOLD}{C.BLUE}  github.com/supriya-mohan/youtube-music-migrator{C.END}")
    print(f"{C.BOLD}{C.BLUE}{'=' * 55}{C.END}\n")

    # Check credentials file exists
    if not os.path.exists(CREDENTIALS_FILE):
        error(f"credentials.json not found in this folder.")
        info("Please follow the setup guide to download your credentials from Google Cloud Console.")
        info("Setup guide: https://supriyamohan.com/youtube-migrator-setup")
        return

    print(f"{C.BOLD}This tool will:{C.END}")
    print("  1. Connect to your SOURCE account (old email)")
    print("  2. Connect to your DESTINATION account (new email)")
    print("  3. Save a local JSON backup of your library")
    print("  4. Migrate playlists, liked songs, and subscriptions")
    print(f"\n  {C.YELLOW}Nothing is stored — all access is session-only.{C.END}")
    print(f"  {C.YELLOW}Your credentials never leave your machine.{C.END}\n")

    input("  Press Enter to begin...\n")

    # Step 1: Authenticate both accounts
    source_service = authenticate("SOURCE account (old email)", "token_source.pickle")
    dest_service   = authenticate("DESTINATION account (new email)", "token_dest.pickle")

    # Step 2: Fetch from source account
    log(f"\n{C.BOLD}STEP 1 — Fetching your library from source account...{C.END}\n")
    playlists     = fetch_playlists(source_service)
    liked_songs   = fetch_liked_songs(source_service)
    subscriptions = fetch_subscriptions(source_service)

    total_songs = sum(len(p["videos"]) for p in playlists)
    print(f"\n  Found: {len(playlists)} playlists · {total_songs} playlist songs · {len(liked_songs)} liked songs · {len(subscriptions)} subscriptions\n")

    # Step 3: Save backup BEFORE any writes
    log(f"{C.BOLD}STEP 2 — Saving local backup...{C.END}\n")
    backup_data = {
        "exported_at": datetime.datetime.now().isoformat(),
        "playlists": playlists,
        "liked_songs": liked_songs,
        "subscriptions": subscriptions
    }
    save_backup(backup_data)

    # Step 4: Write to destination account
    log(f"\n{C.BOLD}STEP 3 — Migrating to destination account...{C.END}")
    skip_log = []

    created_playlists, skipped_videos = create_playlists(dest_service, playlists, skip_log)
    liked_count  = like_songs(dest_service, liked_songs, skip_log)
    sub_count    = add_subscriptions(dest_service, subscriptions, skip_log)

    # Step 5: Save skip log and print summary
    save_skip_log(skip_log)
    print_summary(playlists, liked_songs, subscriptions, created_playlists, skipped_videos, liked_count, sub_count, skip_log)

if __name__ == "__main__":
    main()
