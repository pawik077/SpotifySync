import sys
import json
import requests
import time
import logging

from .api import Playlist, SpotifyClient, SyncSummary
from .utils import setup_logger

logger = logging.getLogger("SpotifySync")


class SyncError(Exception):
    def __init__(self, message: str, code: int = -1):
        super().__init__(message)
        self.code = code


def load_settings(filename: str = "data/settings.json") -> dict:
    try:
        with open(filename, "r") as s:
            settings = json.load(s)
    except FileNotFoundError as e:
        raise SyncError(
            f"Error while reading settings file - {filename!r} not found", -2
        ) from e
    except json.decoder.JSONDecodeError as e:
        raise SyncError(
            "Error while reading settings file - JSON decoding failed", -3
        ) from e
    settings["filename"] = filename
    return settings


def save_settings(settings: dict, filename: str = "data/settings.json") -> None:
    with open(filename, "w") as s:
        json.dump({i: settings[i] for i in settings if i != "filename"}, s, indent=2)


def load_cache(filename: str = "data/cache.json") -> dict:
    try:
        with open(filename, "r") as c:
            cache = json.load(c)
    except FileNotFoundError:
        logger.debug("Cache file not found - creating new")
        cache = {}
    except json.decoder.JSONDecodeError:
        logger.warning("Error reading cache file - creating new")
        cache = {}
    return cache


def save_cache(cache: dict, filename: str = "data/cache.json") -> None:
    with open(filename, "w") as c:
        json.dump(cache, c, indent=None)


def getAuthKey(settings: dict) -> str:
    if int(time.time()) > settings.get("expires_at", 0) - 30 or not settings.get(
        "access_token"
    ):
        if not settings.get("refresh_token"):
            raise SyncError("Authentication error - missing refresh token", -1)
        if not settings.get("client_id"):
            raise SyncError("Authentication error - missing client id", -1)
        try:
            settings["access_token"], settings["refresh_token"], expires_in = (
                SpotifyClient.refresh(settings["refresh_token"], settings["client_id"])
            )
        except requests.exceptions.ConnectionError as e:
            raise SyncError(
                "Error while refreshing authorization token - Server connection error",
                -10,
            ) from e
        except requests.exceptions.HTTPError as e:
            raise SyncError(
                f"Error while refreshing authorization token - Server response: {e}", -1
            ) from e
        settings["expires_at"] = int(time.time()) + expires_in
        save_settings(settings, settings["filename"])
    return "Bearer " + settings["access_token"]


def getPlaylists(
    mergedPlaylistId: str, playlistIds: list[str], client: SpotifyClient
) -> tuple[Playlist, list[Playlist]]:
    playlists = []
    try:
        mergedPlaylist = client.getPlaylistMetadata(mergedPlaylistId)
        mergedPlaylist.tracks = client.getPlaylistContents(
            mergedPlaylistId, mergedPlaylist.snapshot_id
        )
    except requests.exceptions.HTTPError as e:
        raise SyncError(
            f"Error while downloading merged playlist {mergedPlaylistId} contents - Server response: {e}",
            -2,
        ) from e
    except KeyError:
        logger.warning("Playlist metadata cache malformed - retrying")
        try:
            mergedPlaylist = client.getPlaylistMetadata(mergedPlaylistId)
            mergedPlaylist.tracks = client.getPlaylistContents(
                mergedPlaylistId, mergedPlaylist.snapshot_id
            )
        except requests.exceptions.HTTPError as e:
            raise SyncError(
                f"Error while downloading merged playlist {mergedPlaylistId} contents - Server response: {e}",
                -2,
            ) from e
    for playlistId in playlistIds:
        try:
            playlist = client.getPlaylistMetadata(playlistId)
            playlist.tracks = client.getPlaylistContents(
                playlistId, playlist.snapshot_id
            )
            playlists.append(playlist)
        except requests.exceptions.HTTPError as e:
            raise SyncError(
                f"Error while downloading playlist {playlistId} contents - Server response: {e}",
                -2,
            ) from e
        except KeyError:
            logger.warning("Playlist metadata cache malformed - retrying")
            try:
                playlist = client.getPlaylistMetadata(playlistId)
                playlist.tracks = client.getPlaylistContents(
                    playlistId, playlist.snapshot_id
                )
                playlists.append(playlist)
            except requests.exceptions.HTTPError as e:
                raise SyncError(
                    f"Error while downloading playlist {playlistId} contents - Server response: {e}",
                    -2,
                ) from e
    return mergedPlaylist, playlists


def sync(
    mergedPlaylist: Playlist,
    playlists: list[Playlist],
    client: SpotifyClient,
    summary: SyncSummary,
):
    for track in list(mergedPlaylist.tracks):
        if not any(track in playlist.tracks for playlist in playlists):
            try:
                client.removeFromPlaylist(mergedPlaylist.id, track.uri)
            except requests.exceptions.HTTPError as status:
                warn_msg = f"Error while removing {track.title} by {track.artist} from merged playlist {mergedPlaylist.name} - Server response: {status}"
                logger.warning(warn_msg)
                summary.warnings.append(warn_msg)
                continue
            mergedPlaylist.tracks.remove(track)
            logger.info(
                f"Removed {track.title} by {track.artist} from merged playlist {mergedPlaylist.name}"
            )
            summary.removed.append(track)

    index = 0
    for playlist in playlists:
        for track in playlist.tracks:
            if track not in mergedPlaylist.tracks:
                try:
                    client.addToPlaylist(
                        mergedPlaylist.id,
                        track.uri,
                        index + playlist.tracks.index(track),
                    )
                except requests.exceptions.HTTPError as status:
                    warn_msg = f"Error while adding {track.title} by {track.artist} from {playlist.name} to merged playlist {mergedPlaylist.name} - Server response: {status}"
                    logger.warning(warn_msg)
                    summary.warnings.append(warn_msg)
                    continue
                mergedPlaylist.tracks.insert(
                    index + playlist.tracks.index(track), track
                )
                logger.info(
                    f"Added {track.title} by {track.artist} from {playlist.name} to merged playlist {mergedPlaylist.name}"
                )
                summary.added.append((track, playlist))
        index += len(playlist.tracks)

    index = 0
    for playlist in playlists:
        for track in playlist.tracks:
            if track not in mergedPlaylist.tracks:
                continue
            current_pos = mergedPlaylist.tracks.index(track)
            target_pos = index + playlist.tracks.index(track)
            if current_pos != target_pos:
                try:
                    client.reorderPlaylist(
                        mergedPlaylist.id,
                        current_pos,
                        target_pos,
                    )
                except requests.exceptions.HTTPError as status:
                    warn_msg = f"Error while moving {track.title} by {track.artist} from position {current_pos} to {target_pos} - Server response: {status}"
                    logger.warning(warn_msg)
                    summary.warnings.append(warn_msg)
                    continue
                mergedPlaylist.tracks.remove(track)
                mergedPlaylist.tracks.insert(
                    target_pos,
                    track,
                )
                logger.info(
                    f"Moved {track.title} by {track.artist} from position {current_pos} to {target_pos}"
                )
                summary.reordered.append((track, current_pos, target_pos))
        index += len(playlist.tracks)


def run_sync():
    setup_logger("data/sync.log")
    summary = SyncSummary()
    try:
        settings = load_settings()
    except SyncError as e:
        err_msg = str(e)
        logger.error(err_msg)
        summary.errors.append(err_msg)
        summary.exit_code = e.code
        return summary
    if not settings.get("merge_playlist"):
        err_msg = "Configuration error - merge playlist not set"
        logger.error(err_msg)
        summary.errors.append(err_msg)
        summary.exit_code = -4
        return summary
    if not settings.get("playlists"):
        err_msg = "Configuration error - source playlists not set"
        logger.error(err_msg)
        summary.errors.append(err_msg)
        summary.exit_code = -5
        return summary
    cache = load_cache()

    try:
        authKey = getAuthKey(settings)
    except SyncError as e:
        err_msg = str(e)
        logger.error(err_msg)
        summary.errors.append(err_msg)
        summary.exit_code = e.code
        return summary
    client = SpotifyClient(authKey, cache)

    try:
        mergedPlaylist, playlists = getPlaylists(
            settings["merge_playlist"], settings["playlists"], client
        )
    except SyncError as e:
        err_msg = str(e)
        logger.error(err_msg)
        summary.errors.append(err_msg)
        summary.exit_code = e.code
        return summary

    sync(mergedPlaylist, playlists, client, summary)
    save_cache(cache)
    return summary


def main():
    summary = run_sync()
    sys.exit(summary.exit_code)
