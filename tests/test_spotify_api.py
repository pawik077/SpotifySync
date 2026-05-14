import pytest
from unittest.mock import patch, MagicMock
from requests.exceptions import HTTPError
from spotifysync.api import (
    Track,
    Album,
    Playlist,
    User,
    SpotifyClient,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def mock_response(data: dict):
    m = MagicMock()
    m.json.return_value = data
    m.raise_for_status.return_value = None
    return m


def mock_http_error(status_code: int = 400):
    m = MagicMock()
    m.raise_for_status.side_effect = HTTPError(str(status_code))
    return m


def mock_pages(*pages):
    """Return a side_effect list for paginating requests — each call returns the next page."""
    return [mock_response(p) for p in pages]


PLAYLIST_ID = "pl123"
AUTH = "Bearer test_token"

# ── object equality ───────────────────────────────────────────────────────────


def test_track_equal_uris():
    track1 = Track("track1", "artist1", None, "uri")
    track2 = Track("track2", "artist2", None, "uri")

    assert track1 == track2


def test_album_equal_uris():
    album1 = Album("title1", "artist1", "cover1", "date1", 1, "uri")
    album2 = Album("title2", "artist2", "cover2", "date2", 2, "uri")

    assert album1 == album2


# ── refresh ───────────────────────────────────────────────────────────────────


def test_refresh_returns_token_tuple():
    data = {
        "access_token": "new_access",
        "refresh_token": "new_refresh",
        "expires_in": 3600,
    }
    with patch("requests.post", return_value=mock_response(data)):
        result = SpotifyClient.refresh("old_refresh", "client_id")
    assert result == ("new_access", "new_refresh", 3600)


def test_refresh_propagates_http_error():
    with patch("requests.post", return_value=mock_http_error(401)):
        with pytest.raises(HTTPError):
            SpotifyClient.refresh("token", "client_id")


# ── getPlaylistMetadata ───────────────────────────────────────────────────────

METADATA_RESPONSE = {
    "id": PLAYLIST_ID,
    "name": "My Playlist",
    "description": "A description",
    "images": [{"url": "http://cover.jpg"}],
    "public": True,
    "collaborative": False,
    "followers": {"total": 42},
    "owner": {"id": "user1", "display_name": "User One"},
}


def test_getPlaylistMetadata_fields_mapped_correctly():
    client = SpotifyClient(AUTH)
    with patch("requests.get", return_value=mock_response(METADATA_RESPONSE)):
        pl = client.getPlaylistMetadata(PLAYLIST_ID)

    assert pl.id == PLAYLIST_ID
    assert pl.name == "My Playlist"
    assert pl.description == "A description"
    assert pl.cover_url == "http://cover.jpg"
    assert pl.public is True
    assert pl.collaborative is False
    assert pl.followers == 42
    assert pl.owner == User(id="user1", display_name="User One")


def test_getPlaylistMetadata_empty_images_gives_empty_cover_url():
    client = SpotifyClient(AUTH)
    data = {**METADATA_RESPONSE, "images": []}
    with patch("requests.get", return_value=mock_response(data)):
        pl = client.getPlaylistMetadata(PLAYLIST_ID)
    assert pl.cover_url == ""


def test_getPlaylistMetadata_propagates_http_error():
    client = SpotifyClient(AUTH)
    with patch("requests.get", return_value=mock_http_error(404)):
        with pytest.raises(HTTPError):
            client.getPlaylistMetadata(PLAYLIST_ID)


def test_getPlaylistMetadata_no_owner_returns_none():
    client = SpotifyClient(AUTH)
    data = {**METADATA_RESPONSE, "owner": None}
    with patch("requests.get", return_value=mock_response(data)):
        pl = client.getPlaylistMetadata(PLAYLIST_ID)

    assert pl.owner is None


# ── getCurrentUserPlaylists ───────────────────────────────────────────────────

PLAYLIST_LIST_ITEM = {
    "id": "pl1",
    "name": "Playlist One",
    "description": "desc",
    "images": [{"url": "http://img.jpg"}],
    "public": True,
    "collaborative": False,
    "owner": {"id": "u1", "display_name": "User"},
}


def test_getCurrentUserPlaylists_returns_playlist_objects():
    client = SpotifyClient(AUTH)
    page = {"total": 1, "next": None, "items": [PLAYLIST_LIST_ITEM]}
    with patch("requests.get", return_value=mock_response(page)):
        result = client.getCurrentUserPlaylists()

    assert len(result) == 1
    assert isinstance(result[0], Playlist)
    assert result[0].id == "pl1"
    assert result[0].name == "Playlist One"
    assert result[0].cover_url == "http://img.jpg"
    assert result[0].tracks == []


def test_getCurrentUserPlaylists_follows_pagination():
    client = SpotifyClient(AUTH)
    page1 = {"total": 2, "next": "http://next-page", "items": [PLAYLIST_LIST_ITEM]}
    page2 = {"total": 2, "next": None, "items": [{**PLAYLIST_LIST_ITEM, "id": "pl2"}]}
    with patch("requests.get", side_effect=mock_pages(page1, page2)):
        result = client.getCurrentUserPlaylists()

    assert len(result) == 2
    assert result[1].id == "pl2"


def test_getCurrentUserPlaylists_count_mismatch_raises():
    client = SpotifyClient(AUTH)
    page = {"total": 5, "next": None, "items": [PLAYLIST_LIST_ITEM]}
    with patch("requests.get", return_value=mock_response(page)):
        with pytest.raises(RuntimeError, match="expected 5"):
            client.getCurrentUserPlaylists()


def test_getCurrentUserPlaylists_no_owner_returns_none():
    client = SpotifyClient(AUTH)
    page = {"total": 1, "next": None, "items": [{**PLAYLIST_LIST_ITEM, "owner": None}]}
    with patch("requests.get", return_value=mock_response(page)):
        result = client.getCurrentUserPlaylists()

    assert result[0].owner is None


# ── getPlaylistContents ───────────────────────────────────────────────────────

PLAYLIST_ITEM = {
    "track": {
        "name": "Test Track",
        "uri": "spotify:track:abc",
        "artists": [{"name": "Artist A"}, {"name": "Artist B"}],
        "album": {
            "name": "Test Album",
            "uri": "spotify:album:xyz",
            "release_date": "2020-01-01",
            "total_tracks": 10,
            "images": [{"url": "http://cover.jpg"}],
            "artists": [{"name": "Album Artist"}],
        },
    }
}


def test_getPlaylistContents_returns_playlist_contents():
    client = SpotifyClient(AUTH)
    page = {"total": 1, "next": None, "items": [PLAYLIST_ITEM]}
    with patch("requests.get", return_value=mock_response(page)):
        result = client.getPlaylistContents(PLAYLIST_ID)

    assert len(result) == 1
    assert isinstance(result[0], Track)
    assert result[0].title == "Test Track"
    assert result[0].uri == "spotify:track:abc"
    assert isinstance(result[0].album, Album)
    assert result[0].album.title == "Test Album"
    assert result[0].album.artist == "Album Artist"
    assert result[0].album.cover_url == "http://cover.jpg"
    assert result[0].album.release_date == "2020-01-01"
    assert result[0].album.total_tracks == 10
    assert result[0].album.uri == "spotify:album:xyz"


def test_getPlaylistContents_artist_join():
    client = SpotifyClient(AUTH)
    page = {"total": 1, "next": None, "items": [PLAYLIST_ITEM]}
    with patch("requests.get", return_value=mock_response(page)):
        result = client.getPlaylistContents(PLAYLIST_ID)

    assert result[0].artist == "Artist A, Artist B"


def test_getPlaylistContents_follows_pagination():
    client = SpotifyClient(AUTH)
    page1 = {"total": 2, "next": "http://next-page", "items": [PLAYLIST_ITEM]}
    page2 = {
        "total": 2,
        "next": None,
        "items": [
            {
                **PLAYLIST_ITEM,
                "track": {**PLAYLIST_ITEM["track"], "uri": "spotify:track:def"},
            }
        ],
    }
    with patch("requests.get", side_effect=mock_pages(page1, page2)):
        result = client.getPlaylistContents(PLAYLIST_ID)

    assert len(result) == 2
    assert result[1].uri == "spotify:track:def"


def test_getPlaylistContents_null_track_matches_total():
    client = SpotifyClient(AUTH)
    page = {"total": 2, "next": None, "items": [PLAYLIST_ITEM, {"track": None}]}
    with patch("requests.get", return_value=mock_response(page)):
        result = client.getPlaylistContents(PLAYLIST_ID)

    assert len(result) == 1


def test_getPlaylistContents_count_mismatch_raises():
    client = SpotifyClient(AUTH)
    page = {"total": 5, "next": None, "items": [PLAYLIST_ITEM]}
    with patch("requests.get", return_value=mock_response(page)):
        with pytest.raises(RuntimeError, match="expected 5"):
            client.getPlaylistContents(PLAYLIST_ID)


def test_getPlaylistContents_no_album_returns_none():
    client = SpotifyClient(AUTH)
    page = {
        "total": 1,
        "next": None,
        "items": [
            {**PLAYLIST_ITEM, "track": {**PLAYLIST_ITEM["track"], "album": None}}
        ],
    }
    with patch("requests.get", return_value=mock_response(page)):
        result = client.getPlaylistContents(PLAYLIST_ID)

    assert result[0].album is None


# ── getCurrentUser ────────────────────────────────────────────────────────────


USER_RESPONSE = {
    "display_name": "User 1",
    "followers": {"total": 10},
    "id": "user1",
    "images": [{"url": "http://image.jpg"}],
}


def test_getCurrentUser_propagates_http_error():
    client = SpotifyClient(AUTH)
    with patch("requests.get", return_value=mock_http_error(404)):
        with pytest.raises(HTTPError):
            client.getCurrentUser()


def test_getCurrentUser_returns_user_correctly():
    client = SpotifyClient(AUTH)
    with patch("requests.get", return_value=mock_response(USER_RESPONSE)):
        result = client.getCurrentUser()

    assert result.id == "user1"
    assert result.display_name == "User 1"
    assert result.image_url == "http://image.jpg"
    assert result.followers == 10


def test_getCurrentUser_empty_images_gives_empty_image_url():
    client = SpotifyClient(AUTH)
    data = {**USER_RESPONSE, "images": []}
    with patch("requests.get", return_value=mock_response(data)):
        result = client.getCurrentUser()

    assert result.image_url == ""


def test_getCurrentUser_no_followers_returns_none():
    client = SpotifyClient(AUTH)
    data = {**USER_RESPONSE, "followers": {}}
    with patch("requests.get", return_value=mock_response(data)):
        result = client.getCurrentUser()

    assert result.followers is None
