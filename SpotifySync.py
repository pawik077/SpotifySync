import sys
import json
import requests
from SpotifyAPI import (
    refresh,
    getPlaylist,
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

    authKey = "Bearer " + refresh(
        settings["authorization_token"], settings["refresh_token"]
    )

    playlists = []

    mergedPlaylist = getPlaylist(settings["merge_playlist"], authKey)
    for playlist in settings["playlists"]:
        playlists.append((playlist["name"], getPlaylist(playlist["id"], authKey)))

    for track in mergedPlaylist:
        found = False
        for playlist in playlists:
            if track in playlist[1]:
                found = True
        if not found:
            try:
                removeFromPlaylist(
                    settings["merge_playlist"], track.uri, authKey
                ).raise_for_status()
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
                    ).raise_for_status()
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
                    ).raise_for_status()
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
