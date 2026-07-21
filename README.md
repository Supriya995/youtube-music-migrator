# YouTube Music Account Migration Tool

Migrate your YouTube Music library — playlists, liked songs, and subscriptions — from one Google account to another in a single automated run.

Built by [Supriya Mohan](https://supriyamohan.com) | [LinkedIn](https://linkedin.com/in/supriya-mohan)

---

## What it migrates

| Data | Supported |
|------|-----------|
| Playlists (with song order) | ✅ |
| Liked songs | ✅ |
| Channel subscriptions | ✅ |
| Watch history | ❌ Not accessible via API |
| Recommendation algorithm | ❌ Google internal only |

---

## Privacy & Security

- **Nothing is stored on any server.** The tool runs entirely on your machine.
- **OAuth 2.0 authentication** — you log in via Google's own browser flow. Your password is never seen by this tool.
- **Session-only access** — tokens are held in memory for the duration of the run only.
- **Local JSON backup** — a backup of your library is saved to your machine before any writes begin.

---

## Setup Guide (10 minutes)

### Step 1 — Install Python
Make sure you have Python 3.8 or higher installed.
```
python --version
```

### Step 2 — Install dependencies
```
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### Step 3 — Set up Google Cloud Console

1. Go to [https://console.cloud.google.com](https://console.cloud.google.com)
2. Click **"Select a project"** → **"New Project"** → name it anything (e.g. "YT Migrator")
3. Click **"Enable APIs and Services"**
4. Search for **"YouTube Data API v3"** and click **Enable**
5. Go to **"Credentials"** in the left sidebar
6. Click **"Create Credentials"** → **"OAuth 2.0 Client ID"**
7. If prompted, configure the OAuth consent screen:
   - User type: **External**
   - App name: anything
   - Add your two Google emails as **Test users**
8. Application type: **Desktop App**
9. Click **Create** → **Download JSON**
10. Rename the downloaded file to **`credentials.json`**
11. Place `credentials.json` in the same folder as `migrate.py`

### Step 4 — Run the tool
```
python migrate.py
```

The tool will:
1. Open your browser to authenticate your **old account** (source)
2. Open your browser again to authenticate your **new account** (destination)
3. Fetch your library and save a local backup
4. Migrate everything to the new account
5. Print a summary report

---

## API Quota

The YouTube Data API has a **10,000 unit daily limit** by default.

| Library size | Estimated quota usage |
|---|---|
| Small (< 100 songs, < 5 playlists) | ~2,000 units |
| Medium (100–300 songs, 5–15 playlists) | ~5,000–8,000 units |
| Large (300+ songs, 15+ playlists) | May exceed daily quota |

If you hit the quota limit, the tool will automatically wait and retry. For very large libraries, you may need to request a quota increase in Google Cloud Console or run the migration over two days.

---

## Output files

| File | Description |
|------|-------------|
| `youtube_music_backup_YYYYMMDD_HHMMSS.json` | Full backup of your source library |
| `skipped_items.log` | Items that couldn't be transferred (deleted/private/region-locked videos) |

---

## Known limitations

- Watch history is not accessible via the YouTube Data API and cannot be migrated
- YouTube's recommendation algorithm ("For You") cannot be transferred — it rebuilds naturally over time on the new account
- Very large libraries (500+ songs) may hit the default API quota and require a multi-day migration
- Private videos in playlists may not transfer if they are not accessible to the tool

---

## License
MIT — free to use, modify, and share.

---

## Built by
Supriya Mohan — Product Manager  
[supriyamohan.com](https://supriyamohan.com) · [LinkedIn](https://linkedin.com/in/supriya-mohan)
