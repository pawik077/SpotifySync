# SpotifySync

Merges multiple Spotify playlists into one and keeps them in sync. Tracks removed from all source playlists are removed from the merged playlist; new tracks are added and ordered to match the source playlists.

## Prerequisites

- Python 3.10+
- A [Spotify Developer application](https://developer.spotify.com/dashboard) (free)

## Setup

### 1. Create a Spotify application

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and create a new application.
2. In the application settings, add `http://127.0.0.1:8888/callback` to the **Redirect URIs** list.
3. Copy the **Client ID** — you will need it in the next step.

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Authenticate

Launch the GUI and follow the on-screen steps:

```bash
python run.py
```

1. In the **Authentication** tab, click **Configure Client ID…** and enter the Client ID from step 1.
2. Click **Authenticate** — your browser will open the Spotify login page.
3. After approving access, the tab will show **Authenticated**.

### 4. Configure playlists

Switch to the **Playlists** tab:

1. Click **+ Add** to select one or more source playlists from your library.
2. Click **Change…** next to Merge Playlist to select the playlist that will be kept in sync.
3. Click **Save Settings**.

The merge playlist must be owned by you or collaborative. Source playlists can be any playlist you follow.

## Running a sync

**GUI:** click **Run Sync** in the bottom bar.

**Headless** (e.g. from a cron job or script):

```bash
python run.py --sync
```

The headless mode reads from `data/settings.json` and refreshes the access token automatically. Authenticate via the GUI at least once before using headless mode.

## Logs

Sync activity is written to `data/sync.log`. The **Log** tab in the GUI shows the log in reverse-chronological order with live updates and search.
