import json
import requests

from utils import logError

BASE_URL = "https://api.spotify.com/v1"


class Track:
    def __init__(self, title: str = "", artist: str = "", uri: str = "") -> None:
        self.artist = artist
        self.title = title
        self.uri = uri

    def __eq__(self, o: object) -> bool:
        if isinstance(o, Track):
            return self.uri == o.uri
        return NotImplemented


def refresh(authorization_token: str, refresh_token: str) -> str:
    url = "https://accounts.spotify.com/api/token"
    payload = "grant_type=refresh_token&refresh_token=" + refresh_token
    headers = {
        "Authorization": "Basic " + authorization_token,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        logError("Error while getting authorization key - Server connection error", -10)
    except requests.exceptions.HTTPError as status:
        logError(
            f"Error while getting authorization key - Server response: {status}", -1
        )
    return json.loads(response.text)["access_token"]


def getCurrentUser(authkey: str) -> str:
    url = f"{BASE_URL}/me"
    headers = {"Authorization": authkey}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.HTTPError as status:
        logError(f"Error while getting current user - Server response: {status}", -2)
    return json.loads(response.text)  # ["id"]


def getPlaylist(playlistId: str, authKey: str) -> list[Track]:
    playlist = []
    url = f"{BASE_URL}/playlists/" + playlistId + "/tracks"
    headers = {"Authorization": authKey}
    while url is not None:
        response = requests.get(url, headers=headers)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as status:
            logError(
                f"Error while downloading playlist contents - Server response: {status}",
                -2,
            )
        for item in json.loads(response.text)["items"]:
            track = Track(item["track"]["name"], "", item["track"]["uri"])
            artists = len(item["track"]["artists"])
            for artist in item["track"]["artists"]:
                track.artist += artist["name"]
                artists -= 1
                if artists != 0:
                    track.artist += ", "
            playlist.append(track)
        url = json.loads(response.text)["next"]
    return playlist


def addToPlaylist(
    playlistId: str, uri: str, pos: int, authKey: str
) -> requests.models.Response:
    url = (
        f"{BASE_URL}/playlists/"
        + playlistId
        + "/tracks?uris="
        + uri
        + "&position="
        + str(pos)
    )
    headers = {"Authorization": authKey}
    response = requests.post(url, headers=headers)
    return response


def removeFromPlaylist(
    playlistId: str, uri: str, authKey: str
) -> requests.models.Response:
    url = f"{BASE_URL}/playlists/" + playlistId + "/tracks"
    headers = {"Authorization": authKey}
    payload = (
        '{\
        "tracks": [\
            {\
                "uri": "'
        + uri
        + '"\
            }\
        ]\
    }'
    )
    response = requests.delete(url, headers=headers, data=payload)
    return response


def reorderPlaylist(
    playlistId: str, initPos: int, endPos: int, authKey: str
) -> requests.models.Response:
    url = f"{BASE_URL}/playlists/" + playlistId + "/tracks"
    headers = {"Authorization": authKey, "Content-Type": "application/json"}
    payload = (
        '{\
        "range_start": '
        + str(initPos)
        + ',\
        "insert_before": '
        + str(endPos)
        + "\
    }"
    )
    response = requests.put(url, headers=headers, data=payload)
    return response
