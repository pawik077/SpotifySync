import sys
import json
import requests
import time
from SpotifyAPI import (
    refresh,
    getPlaylistContents,
    addToPlaylist,
    removeFromPlaylist,
    reorderPlaylist,
)
from utils import logError, log


def main():
    try:
        with open("settings.json", "r") as s:
            settings = json.load(s)
    except FileNotFoundError:
        logError("Error while reading settings file - settings.json file not found")
        sys.exit(-2)
    except json.decoder.JSONDecodeError:
        logError("Error while reading settings file - JSON decoding failed")
        sys.exit(-3)

    if not settings.get("merge_playlist"):
        logError("Configuration error - merge playlist not set")
        sys.exit(-4)
    if not settings.get("playlists"):
        logError("Configuration error - source playlists not set")
        sys.exit(-5)

    if int(time.time()) > settings.get("expires_at", 0) - 30 or not settings.get(
        "access_token"
    ):
        if not settings.get("refresh_token"):
            logError("Authentication error - missing refresh token")
            sys.exit(-1)
        if not settings.get("client_id"):
            logError("Authentication error - missing client id")
            sys.exit(-1)
        try:
            settings["access_token"], settings["refresh_token"], expires_in = refresh(
                settings["refresh_token"], settings["client_id"]
            )
        except requests.exceptions.ConnectionError:
            logError(
                "Error while refreshing authorization token - Server connection error"
            )
            sys.exit(-10)
        except requests.exceptions.HTTPError as status:
            logError(
                f"Error while refreshing authorization token - Server response: {status}"
            )
            sys.exit(-1)
        settings["expires_at"] = int(time.time()) + expires_in
        with open("settings.json", "w") as s:
            json.dump(settings, s, indent=2)

    authKey = "Bearer " + settings["access_token"]

    playlists = []

    try:
        mergedPlaylist = getPlaylistContents(settings["merge_playlist"], authKey)
    except requests.exceptions.HTTPError as status:
        logError(
            f"Error while downloading merged playlist  contents - Server response: {status}"
        )
        sys.exit(-2)
    for playlist in settings["playlists"]:
        try:
            playlists.append(
                (playlist["name"], getPlaylistContents(playlist["id"], authKey))
            )
        except requests.exceptions.HTTPError as status:
            logError(
                f"Error while downloading playlist {playlist['name']} contents - Server response: {status}"
            )
            sys.exit(-2)

    for track in mergedPlaylist:
        found = False
        for playlist in playlists:
            if track in playlist[1]:
                found = True
        if not found:
            try:
                removeFromPlaylist(settings["merge_playlist"], track.uri, authKey)
            except requests.exceptions.HTTPError as status:
                logError(
                    f"Error while removing {track.title} by {track.artist} from merged playlist - Server response: {status}",
                )
                continue
            mergedPlaylist.remove(track)
            log(f"Removed {track.title} by {track.artist} from merged playlist")

    index = 0
    for playlist in playlists:
        for track in playlist[1]:
            if track not in mergedPlaylist:
                try:
                    addToPlaylist(
                        settings["merge_playlist"],
                        track.uri,
                        index + playlist[1].index(track),
                        authKey,
                    )
                except requests.exceptions.HTTPError as status:
                    logError(
                        f"Error while adding {track.title} by {track.artist} from {playlist[0]} to merged playlist - Server response: {status}"
                    )
                    continue
                mergedPlaylist.insert(index + playlist[1].index(track), track)
                log(
                    f"Added {track.title} by {track.artist} from {playlist[0]} to merged playlist"
                )
        index += len(playlist[1])

    index = 0
    for playlist in playlists:
        for track in playlist[1]:
            if mergedPlaylist.index(track) != index + playlist[1].index(track):
                try:
                    reorderPlaylist(
                        settings["merge_playlist"],
                        mergedPlaylist.index(track),
                        index + playlist[1].index(track),
                        authKey,
                    )
                except requests.exceptions.HTTPError as status:
                    logError(
                        f"Error while moving {track.title} by {track.artist} from position {mergedPlaylist.index(track)} to {index + playlist[1].index(track)} - Server response: {status}"
                    )
                    continue
                oldIndex = mergedPlaylist.index(track)
                mergedPlaylist.remove(track)
                mergedPlaylist.insert(index + playlist[1].index(track), track)
                log(
                    f"Moved {track.title} by {track.artist} from position {oldIndex} to {mergedPlaylist.index(track)}"
                )
        index += len(playlist[1])


if __name__ == "__main__":
    main()
