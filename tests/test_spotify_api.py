import pytest
from unittest.mock import patch, MagicMock
from requests.exceptions import HTTPError
from SpotifyAPI import (
    Track,
    Album,
    Playlist,
    refresh,
    getPlaylistContents,
    getPlaylistMetadata,
    getCurrentUserPlaylists,
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

# ── refresh ───────────────────────────────────────────────────────────────────


def test_refresh_returns_token_tuple():
    data = {
        "access_token": "new_access",
        "refresh_token": "new_refresh",
        "expires_in": 3600,
    }
    with patch("requests.post", return_value=mock_response(data)):
        result = refresh("old_refresh", "client_id")
    assert result == ("new_access", "new_refresh", 3600)


def test_refresh_propagates_http_error():
    with patch("requests.post", return_value=mock_http_error(401)):
        with pytest.raises(HTTPError):
            refresh("token", "client_id")


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
    with patch("requests.get", return_value=mock_response(METADATA_RESPONSE)):
        pl = getPlaylistMetadata(PLAYLIST_ID, AUTH)

    assert pl.id == PLAYLIST_ID
    assert pl.name == "My Playlist"
    assert pl.description == "A description"
    assert pl.cover_url == "http://cover.jpg"
    assert pl.public is True
    assert pl.collaborative is False
    assert pl.followers == 42
    assert pl.owner == {"id": "user1", "display_name": "User One"}


def test_getPlaylistMetadata_empty_images_gives_empty_cover_url():
    data = {**METADATA_RESPONSE, "images": []}
    with patch("requests.get", return_value=mock_response(data)):
        pl = getPlaylistMetadata(PLAYLIST_ID, AUTH)
    assert pl.cover_url == ""


def test_getPlaylistMetadata_propagates_http_error():
    with patch("requests.get", return_value=mock_http_error(404)):
        with pytest.raises(HTTPError):
            getPlaylistMetadata(PLAYLIST_ID, AUTH)


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
    page = {"total": 1, "next": None, "items": [PLAYLIST_LIST_ITEM]}
    with patch("requests.get", return_value=mock_response(page)):
        result = getCurrentUserPlaylists(AUTH)

    assert len(result) == 1
    assert isinstance(result[0], Playlist)
    assert result[0].id == "pl1"
    assert result[0].name == "Playlist One"
    assert result[0].cover_url == "http://img.jpg"
    assert result[0].tracks == []


def test_getCurrentUserPlaylists_follows_pagination():
    page1 = {"total": 2, "next": "http://next-page", "items": [PLAYLIST_LIST_ITEM]}
    page2 = {"total": 2, "next": None, "items": [{**PLAYLIST_LIST_ITEM, "id": "pl2"}]}
    with patch("requests.get", side_effect=mock_pages(page1, page2)):
        result = getCurrentUserPlaylists(AUTH)

    assert len(result) == 2
    assert result[1].id == "pl2"


def test_getCurrentUserPlaylists_count_mismatch_raises():
    page = {"total": 5, "next": None, "items": [PLAYLIST_LIST_ITEM]}
    with patch("requests.get", return_value=mock_response(page)):
        with pytest.raises(RuntimeError, match="expected 5"):
            getCurrentUserPlaylists(AUTH)


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
    page = {"total": 1, "next": None, "items": [PLAYLIST_ITEM]}
    with patch("requests.get", return_value=mock_response(page)):
        result = getPlaylistContents(PLAYLIST_ID, AUTH)

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
    page = {"total": 1, "next": None, "items": [PLAYLIST_ITEM]}
    with patch("requests.get", return_value=mock_response(page)):
        result = getPlaylistContents(PLAYLIST_ID, AUTH)

    assert result[0].artist == "Artist A, Artist B"


def test_getPlaylistContents_follows_pagination():
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
        result = getPlaylistContents(PLAYLIST_ID, AUTH)

    assert len(result) == 2
    assert result[1].uri == "spotify:track:def"


def test_getPlaylistContents_null_track_matches_total():
    page = {"total": 2, "next": None, "items": [PLAYLIST_ITEM, {"track": None}]}
    with patch("requests.get", return_value=mock_response(page)):
        result = getPlaylistContents(PLAYLIST_ID, AUTH)

    assert len(result) == 1


def test_getPlaylistContents_count_mismatch_raises():
    page = {"total": 5, "next": None, "items": [PLAYLIST_ITEM]}
    with patch("requests.get", return_value=mock_response(page)):
        with pytest.raises(RuntimeError, match="expected 5"):
            getPlaylistContents(PLAYLIST_ID, AUTH)
