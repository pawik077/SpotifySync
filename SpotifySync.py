import sys
import json
import requests
import time
import logging
from SpotifyAPI import (
    Playlist,
    refresh,
    getPlaylistMetadata,
    getPlaylistContents,
    addToPlaylist,
    removeFromPlaylist,
    reorderPlaylist,
)
from utils import setup_logger

logger = logging.getLogger("SpotifySync")


def load_settings(filename: str = "settings.json"):
    try:
        with open(filename, "r") as s:
            settings = json.load(s)
    except FileNotFoundError:
        logger.error("Error while reading settings file - settings.json file not found")
        sys.exit(-2)
    except json.decoder.JSONDecodeError:
        logger.error("Error while reading settings file - JSON decoding failed")
        sys.exit(-3)
    settings["filename"] = filename
    return settings


def save_settings(settings, filename: str = "settings.json"):
    with open(filename, "w") as s:
        json.dump({i: settings[i] for i in settings if i != "filename"}, s, indent=2)


def getAuthKey(settings: dict):
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


def getPlaylists(settings: dict, authKey: str):
    playlists = []
    try:
        mergedPlaylist = getPlaylistMetadata(settings["merge_playlist"], authKey)
        mergedPlaylist.tracks = getPlaylistContents(settings["merge_playlist"], authKey)
    except requests.exceptions.HTTPError as status:
        logger.error(
            f"Error while downloading merged playlist {settings['merge_playlist']} contents - Server response: {status}"
        )
        sys.exit(-2)
    for playlistId in settings["playlists"]:
        try:
            playlist = getPlaylistMetadata(playlistId, authKey)
            playlist.tracks = getPlaylistContents(playlistId, authKey)
            playlists.append(playlist)
        except requests.exceptions.HTTPError as status:
            logger.error(
                f"Error while downloading playlist {playlistId} contents - Server response: {status}"
            )
            sys.exit(-2)
    return mergedPlaylist, playlists


def sync(mergedPlaylist: Playlist, playlists: list[Playlist], authKey: str):
    for track in mergedPlaylist.tracks:
        found = False
        for playlist in playlists:
            if track in playlist.tracks:
                found = True
        if not found:
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
            if mergedPlaylist.tracks.index(track) != index + playlist.tracks.index(
                track
            ):
                try:
                    reorderPlaylist(
                        mergedPlaylist.id,
                        mergedPlaylist.tracks.index(track),
                        index + playlist.tracks.index(track),
                        authKey,
                    )
                except requests.exceptions.HTTPError as status:
                    logger.warning(
                        f"Error while moving {track.title} by {track.artist} from position {mergedPlaylist.tracks.index(track)} to {index + playlist.tracks.index(track)} - Server response: {status}"
                    )
                    continue
                oldIndex = mergedPlaylist.tracks.index(track)
                mergedPlaylist.tracks.remove(track)
                mergedPlaylist.tracks.insert(
                    index + playlist.tracks.index(track), track
                )
                logger.info(
                    f"Moved {track.title} by {track.artist} from position {oldIndex} to {mergedPlaylist.tracks.index(track)}"
                )
        index += len(playlist.tracks)


def main():
    settings = load_settings()
    if not settings.get("merge_playlist"):
        logger.error("Configuration error - merge playlist not set")
        sys.exit(-4)
    if not settings.get("playlists"):
        logger.error("Configuration error - source playlists not set")
        sys.exit(-5)

    authKey = getAuthKey(settings)

    mergedPlaylist, playlists = getPlaylists(settings, authKey)

    sync(mergedPlaylist, playlists, authKey)


if __name__ == "__main__":
    setup_logger("sync.log")
    main()
