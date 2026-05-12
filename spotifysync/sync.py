import sys
import json
import requests
import time
import logging

from .api import (
    Playlist,
    refresh,
    getPlaylistMetadata,
    getPlaylistContents,
    addToPlaylist,
    removeFromPlaylist,
    reorderPlaylist,
)
from .utils import setup_logger

logger = logging.getLogger("SpotifySync")


def load_settings(filename: str = "data/settings.json") -> dict:
    try:
        with open(filename, "r") as s:
            settings = json.load(s)
    except FileNotFoundError:
        logger.error(f"Error while reading settings file - {filename!r} not found")
        sys.exit(-2)
    except json.decoder.JSONDecodeError:
        logger.error("Error while reading settings file - JSON decoding failed")
        sys.exit(-3)
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
            logger.error("Authentication error - missing refresh token")
            sys.exit(-1)
        if not settings.get("client_id"):
            logger.error("Authentication error - missing client id")
            sys.exit(-1)
        try:
            settings["access_token"], settings["refresh_token"], expires_in = refresh(
                settings["refresh_token"], settings["client_id"]
            )
        except requests.exceptions.ConnectionError:
            logger.error(
                "Error while refreshing authorization token - Server connection error"
            )
            sys.exit(-10)
        except requests.exceptions.HTTPError as status:
            logger.error(
                f"Error while refreshing authorization token - Server response: {status}"
            )
            sys.exit(-1)
        settings["expires_at"] = int(time.time()) + expires_in
        save_settings(settings, settings["filename"])
    return "Bearer " + settings["access_token"]


def getPlaylists(
    mergedPlaylistId: str, playlistIds: list[str], authKey: str, cache: dict
) -> tuple[Playlist, list[Playlist]]:
    playlists = []
    try:
        mergedPlaylist = getPlaylistMetadata(mergedPlaylistId, authKey, cache)
        mergedPlaylist.tracks = getPlaylistContents(
            mergedPlaylistId, authKey, cache, mergedPlaylist.snapshot_id
        )
    except requests.exceptions.HTTPError as status:
        logger.error(
            f"Error while downloading merged playlist {mergedPlaylistId} contents - Server response: {status}"
        )
        sys.exit(-2)
    except KeyError:
        logger.warning("Playlist metadata cache malformed - retrying")
        try:
            mergedPlaylist = getPlaylistMetadata(mergedPlaylistId, authKey, cache)
            mergedPlaylist.tracks = getPlaylistContents(
                mergedPlaylistId, authKey, cache, mergedPlaylist.snapshot_id
            )
        except requests.exceptions.HTTPError as status:
            logger.error(
                f"Error while downloading merged playlist {mergedPlaylistId} contents - Server response: {status}"
            )
            sys.exit(-2)
    for playlistId in playlistIds:
        try:
            playlist = getPlaylistMetadata(playlistId, authKey, cache)
            playlist.tracks = getPlaylistContents(
                playlistId, authKey, cache, playlist.snapshot_id
            )
            playlists.append(playlist)
        except requests.exceptions.HTTPError as status:
            logger.error(
                f"Error while downloading playlist {playlistId} contents - Server response: {status}"
            )
            sys.exit(-2)
        except KeyError:
            logger.warning("Playlist metadata cache malformed - retrying")
            try:
                playlist = getPlaylistMetadata(playlistId, authKey, cache)
                playlist.tracks = getPlaylistContents(
                    playlistId, authKey, cache, playlist.snapshot_id
                )
                playlists.append(playlist)
            except requests.exceptions.HTTPError as status:
                logger.error(
                    f"Error while downloading playlist {playlistId} contents - Server response: {status}"
                )
                sys.exit(-2)
    return mergedPlaylist, playlists


def sync(mergedPlaylist: Playlist, playlists: list[Playlist], authKey: str) -> None:
    for track in list(mergedPlaylist.tracks):
        if not any(track in playlist.tracks for playlist in playlists):
            try:
                removeFromPlaylist(mergedPlaylist.id, track.uri, authKey)
            except requests.exceptions.HTTPError as status:
                logger.warning(
                    f"Error while removing {track.title} by {track.artist} from merged playlist {mergedPlaylist.name} - Server response: {status}",
                )
                continue
            mergedPlaylist.tracks.remove(track)
            logger.info(
                f"Removed {track.title} by {track.artist} from merged playlist {mergedPlaylist.name}"
            )

    index = 0
    for playlist in playlists:
        for track in playlist.tracks:
            if track not in mergedPlaylist.tracks:
                try:
                    addToPlaylist(
                        mergedPlaylist.id,
                        track.uri,
                        index + playlist.tracks.index(track),
                        authKey,
                    )
                except requests.exceptions.HTTPError as status:
                    logger.warning(
                        f"Error while adding {track.title} by {track.artist} from {playlist.name} to merged playlist {mergedPlaylist.name} - Server response: {status}"
                    )
                    continue
                mergedPlaylist.tracks.insert(
                    index + playlist.tracks.index(track), track
                )
                logger.info(
                    f"Added {track.title} by {track.artist} from {playlist.name} to merged playlist {mergedPlaylist.name}"
                )
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
                    reorderPlaylist(
                        mergedPlaylist.id,
                        current_pos,
                        target_pos,
                        authKey,
                    )
                except requests.exceptions.HTTPError as status:
                    logger.warning(
                        f"Error while moving {track.title} by {track.artist} from position {current_pos} to {target_pos} - Server response: {status}"
                    )
                    continue
                mergedPlaylist.tracks.remove(track)
                mergedPlaylist.tracks.insert(
                    target_pos,
                    track,
                )
                logger.info(
                    f"Moved {track.title} by {track.artist} from position {current_pos} to {target_pos}"
                )
        index += len(playlist.tracks)


def main():
    setup_logger("data/sync.log")
    settings = load_settings()
    if not settings.get("merge_playlist"):
        logger.error("Configuration error - merge playlist not set")
        sys.exit(-4)
    if not settings.get("playlists"):
        logger.error("Configuration error - source playlists not set")
        sys.exit(-5)
    cache = load_cache()

    authKey = getAuthKey(settings)

    mergedPlaylist, playlists = getPlaylists(
        settings["merge_playlist"], settings["playlists"], authKey, cache
    )

    sync(mergedPlaylist, playlists, authKey)
    save_cache(cache)
