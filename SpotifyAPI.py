import requests
from dataclasses import dataclass, field

BASE_URL = "https://api.spotify.com/v1"


# TODO: expand class with additional data
@dataclass(eq=False)
class Track:
    title: str = ""
    artist: str = ""
    uri: str = ""

    def __eq__(self, o: object) -> bool:
        if isinstance(o, Track):
            return self.uri == o.uri
        return NotImplemented


@dataclass
class Playlist:
    id: str
    name: str = ""
    cover_url: str = ""
    description: str = ""
    public: bool | None = None
    collaborative: bool | None = None
    followers: int | None = None
    owner: dict = field(default_factory=dict)
    tracks: list[Track] = field(default_factory=list)


def refresh(refresh_token: str, client_id: str) -> tuple[str, str, int]:
    url = "https://accounts.spotify.com/api/token"
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }
    response = requests.post(url, headers=headers, data=payload)
    response.raise_for_status()
    data = response.json()
    return data["access_token"], data["refresh_token"], data["expires_in"]


def getCurrentUser(authkey: str) -> dict:
    url = f"{BASE_URL}/me"
    headers = {"Authorization": authkey}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()  # ["id"]


def getCurrentUserPlaylists(authKey: str) -> list[Playlist]:
    playlists = []
    total = None
    url = f"{BASE_URL}/me/playlists"
    headers = {"Authorization": authKey}
    params = {
        "fields": "total,next,items(id,name,images(url),description,public,collaborative,owner.id,owner.display_name)"
    }
    while url is not None:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        if total is None:
            total = data["total"]
        for item in data["items"]:
            playlists.append(
                Playlist(
                    id=item["id"],
                    name=item.get("name", ""),
                    cover_url=item["images"][0]["url"] if item.get("images") else "",
                    description=item.get("description", ""),
                    public=item.get("public"),
                    collaborative=item.get("collaborative"),
                    # followers=(
                    #     item["followers"]["total"] if item.get("followers") else 0
                    # ), # no followers info in /me/playlists
                    owner=(
                        {
                            "id": item["owner"]["id"],
                            "display_name": item["owner"]["display_name"],
                        }
                        if item.get("owner")
                        else {}
                    ),
                )
            )
        url = data["next"]
    if len(playlists) != total:
        raise RuntimeError(
            f"Incomplete response: expected {total} playlists, received {len(playlists)}"
        )
    return playlists


def getPlaylistMetadata(playlistId: str, authKey: str) -> Playlist:
    url = f"{BASE_URL}/playlists/{playlistId}"
    headers = {"Authorization": authKey}
    params = {
        "fields": "id,name,images(url),description,public,collaborative,followers.total,owner.id,owner.display_name"
    }
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()
    return Playlist(
        id=playlistId,
        name=data.get("name", ""),
        cover_url=data["images"][0]["url"] if data.get("images") else "",
        description=data.get("description", ""),
        public=data.get("public"),
        collaborative=data.get("collaborative"),
        followers=data["followers"]["total"] if data.get("followers") else None,
        owner=(
            {"id": data["owner"]["id"], "display_name": data["owner"]["display_name"]}
            if data.get("owner")
            else {}
        ),
    )


def getPlaylistContents(playlistId: str, authKey: str) -> list[Track]:
    playlist = []
    total = None
    url = f"{BASE_URL}/playlists/{playlistId}/items"
    headers = {"Authorization": authKey}
    params = {"fields": "total,next,items(track(name,uri,artists(name)))"}
    while url is not None:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        if total is None:
            total = data["total"]
        for item in data["items"]:
            if item.get("track") is None:
                total -= 1
                continue
            track = Track(
                title=item["track"]["name"], artist="", uri=item["track"]["uri"]
            )
            artists = len(item["track"]["artists"])
            for artist in item["track"]["artists"]:
                track.artist += artist["name"]
                artists -= 1
                if artists != 0:
                    track.artist += ", "
            playlist.append(track)
        url = data["next"]
    if len(playlist) != total:
        raise RuntimeError(
            f"Incomplete response: expected {total} tracks for playlist {playlistId}, received {len(playlist)}"
        )
    return playlist


def addToPlaylist(
    playlistId: str, uri: str, pos: int, authKey: str
) -> requests.models.Response:
    url = f"{BASE_URL}/playlists/{playlistId}/items"
    headers = {"Authorization": authKey, "Content-Type": "application/json"}
    payload = {"uris": [uri], "position": pos}
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response


def removeFromPlaylist(
    playlistId: str, uri: str, authKey: str
) -> requests.models.Response:
    url = f"{BASE_URL}/playlists/{playlistId}/items"
    headers = {"Authorization": authKey}
    payload = {"items": [{"uri": uri}]}
    response = requests.delete(url, headers=headers, json=payload)
    response.raise_for_status()
    return response


def reorderPlaylist(
    playlistId: str, initPos: int, endPos: int, authKey: str
) -> requests.models.Response:
    url = f"{BASE_URL}/playlists/{playlistId}/items"
    headers = {"Authorization": authKey, "Content-Type": "application/json"}
    payload = {"range_start": initPos, "insert_before": endPos}
    response = requests.put(url, headers=headers, json=payload)
    response.raise_for_status()
    return response
