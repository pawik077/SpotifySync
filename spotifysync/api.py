from typing import Any
import requests
from dataclasses import dataclass, field


@dataclass
class User:
    id: str = ""
    display_name: str = ""
    image_url: str = ""
    followers: int | None = None


@dataclass(eq=False)
class Album:
    title: str = ""
    artist: str = ""
    cover_url: str = ""
    release_date: str = ""
    total_tracks: int | None = None
    uri: str = ""

    def __eq__(self, o: object) -> bool:
        if isinstance(o, Album):
            return self.uri == o.uri
        return NotImplemented


@dataclass(eq=False)
class Track:
    title: str = ""
    artist: str = ""
    album: Album | None = None
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
    owner: User | None = None
    tracks: list[Track] = field(default_factory=list)
    snapshot_id: str = ""


class SpotifyClient:
    BASE_URL = "https://api.spotify.com/v1"

    def __init__(self, authKey: str, cache: dict | None = None) -> None:
        self._auth_key = authKey
        self._cache = cache

    @staticmethod
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

    def getCurrentUser(self) -> User:
        url = f"{self.BASE_URL}/me"
        headers = {"Authorization": self._auth_key}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return User(
            id=data["id"],
            display_name=data.get("display_name", data["id"]),
            image_url=data["images"][0]["url"] if data.get("images") else "",
            followers=data["followers"]["total"] if data.get("followers") else None,
        )

    def getCurrentUserPlaylists(self) -> list[Playlist]:
        playlists = []
        total = None
        url = f"{self.BASE_URL}/me/playlists"
        headers = {"Authorization": self._auth_key}
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
                        cover_url=(
                            item["images"][0]["url"] if item.get("images") else ""
                        ),
                        description=item.get("description", ""),
                        public=item.get("public"),
                        collaborative=item.get("collaborative"),
                        # important: no followers info in /me/playlists
                        owner=(
                            User(
                                id=item["owner"]["id"],
                                display_name=item["owner"]["display_name"],
                            )
                            if item.get("owner")
                            else None
                        ),
                    )
                )
            url = data["next"]
        if len(playlists) != total:
            raise RuntimeError(
                f"Incomplete response: expected {total} playlists, received {len(playlists)}"
            )
        return playlists

    def getPlaylistMetadata(self, playlistId: str) -> Playlist:
        url = f"{self.BASE_URL}/playlists/{playlistId}"
        if self._cache is None:
            self._cache = {}
        if self._cache.get("metadata", {}).get(playlistId):
            etag = self._cache["metadata"][playlistId].get("etag", "")
            headers = {"Authorization": self._auth_key, "If-None-Match": etag}
        else:
            headers = {"Authorization": self._auth_key}
        params = {
            "fields": "id,name,images(url),description,public,collaborative,followers.total,owner.id,owner.display_name,snapshot_id"
        }
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        if response.status_code == 304:
            try:
                data = self._cache["metadata"][playlistId]["data"]
            except KeyError:
                del self._cache["metadata"][playlistId]
                raise KeyError("Cache malformed - deleting")
        else:
            data = response.json()
            self._cache.setdefault("metadata", {}).setdefault(playlistId, {})
            self._cache["metadata"][playlistId]["etag"] = response.headers.get(
                "etag", ""
            )
            self._cache["metadata"][playlistId]["data"] = data
        return Playlist(
            id=playlistId,
            name=data.get("name", ""),
            cover_url=data["images"][0]["url"] if data.get("images") else "",
            description=data.get("description", ""),
            public=data.get("public"),
            collaborative=data.get("collaborative"),
            followers=data["followers"]["total"] if data.get("followers") else None,
            owner=(
                User(id=data["owner"]["id"], display_name=data["owner"]["display_name"])
                if data.get("owner")
                else None
            ),
            snapshot_id=data.get("snapshot_id", ""),
        )

    def getPlaylistContents(
        self, playlistId: str, snapshot_id: str = ""
    ) -> list[Track]:
        tracks = []
        total = None
        url = f"{self.BASE_URL}/playlists/{playlistId}/items"
        if self._cache is None:
            self._cache = {}
        if (
            snapshot_id
            and self._cache.get("contents", {}).get(playlistId, {}).get("snapshot_id")
            == snapshot_id
        ):
            try:
                total = len(self._cache["contents"][playlistId]["items"])
                for item in self._cache["contents"][playlistId]["items"]:
                    track = _parse_track(item)
                    if track is None:
                        total -= 1
                        continue
                    tracks.append(track)
                return tracks
            except KeyError:
                total = None
                tracks = []
                del self._cache["contents"][playlistId]  # malformed cache
        headers = {"Authorization": self._auth_key}
        params = {
            "fields": "total,next,items(track(name,uri,artists(name),album(images(url),name,release_date,total_tracks,uri,artists(name))))"
        }
        items = []
        while url is not None:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            items.extend(data["items"])
            if total is None:
                total = data["total"]
            for item in data["items"]:
                track = _parse_track(item)
                if track is None:
                    total -= 1
                    continue
                tracks.append(track)
            url = data["next"]
        if len(tracks) != total:
            raise RuntimeError(
                f"Incomplete response: expected {total} tracks for playlist {playlistId}, received {len(tracks)}"
            )
        self._cache.setdefault("contents", {})[playlistId] = {
            "snapshot_id": snapshot_id,
            "items": items,
        }
        return tracks

    def addToPlaylist(
        self, playlistId: str, uri: str, pos: int
    ) -> requests.models.Response:
        url = f"{self.BASE_URL}/playlists/{playlistId}/items"
        headers = {"Authorization": self._auth_key, "Content-Type": "application/json"}
        payload = {"uris": [uri], "position": pos}
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response

    def removeFromPlaylist(self, playlistId: str, uri: str) -> requests.models.Response:
        url = f"{self.BASE_URL}/playlists/{playlistId}/items"
        headers = {"Authorization": self._auth_key}
        payload: dict[str, Any] = {"items": [{"uri": uri}]}
        response = requests.delete(url, headers=headers, json=payload)
        response.raise_for_status()
        return response

    def reorderPlaylist(
        self, playlistId: str, initPos: int, endPos: int
    ) -> requests.models.Response:
        url = f"{self.BASE_URL}/playlists/{playlistId}/items"
        headers = {"Authorization": self._auth_key, "Content-Type": "application/json"}
        payload: dict[str, Any] = {"range_start": initPos, "insert_before": endPos}
        response = requests.put(url, headers=headers, json=payload)
        response.raise_for_status()
        return response


def _parse_track(item: dict) -> Track | None:
    if item.get("track") is None:
        return None
    return Track(
        title=item["track"].get("name", ""),
        artist=(
            ", ".join([artist["name"] for artist in item["track"]["artists"]])
            if item["track"].get("artists")
            else ""
        ),
        album=(
            Album(
                title=item["track"]["album"].get("name", ""),
                artist=(
                    ", ".join(
                        [artist["name"] for artist in item["track"]["album"]["artists"]]
                    )
                    if item["track"]["album"].get("artists")
                    else ""
                ),
                cover_url=(
                    item["track"]["album"]["images"][0]["url"]
                    if item["track"]["album"].get("images")
                    else ""
                ),
                release_date=item["track"]["album"].get("release_date", ""),
                total_tracks=item["track"]["album"].get("total_tracks", None),
                uri=item["track"]["album"]["uri"],
            )
            if item["track"].get("album")
            else None
        ),
        uri=item["track"].get("uri", ""),
    )
