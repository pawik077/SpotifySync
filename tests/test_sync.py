from unittest.mock import patch, call
from SpotifyAPI import Track, Playlist
from SpotifySync import sync
from requests.exceptions import HTTPError

# ── Fixtures ──────────────────────────────────────────────────────────────────


def track(uri: str, title: str = "") -> Track:
    return Track(title=title or uri, artist="", uri=uri)


def playlist(id: str, *tracks: Track) -> Playlist:
    p = Playlist(id=id, name=id)
    p.tracks = list(tracks)
    return p


AUTH = "Bearer test_token"


# ── Remove phase ──────────────────────────────────────────────────────────────


def test_removes_track_absent_from_all_sources():
    t1, t2 = track("uri:1"), track("uri:2")
    merged = playlist("merged", t1, t2)
    source = playlist("src", t1)  # t2 not present anywhere

    with patch("SpotifySync.removeFromPlaylist") as mock_remove:
        with patch("SpotifySync.addToPlaylist"):
            with patch("SpotifySync.reorderPlaylist"):
                sync(merged, [source], AUTH)

    mock_remove.assert_called_once_with("merged", "uri:2", AUTH)
    assert t2 not in merged.tracks


def test_keeps_track_present_in_one_source():
    t1 = track("uri:1")
    merged = playlist("merged", t1)
    source = playlist("src", t1)

    with patch("SpotifySync.removeFromPlaylist") as mock_remove:
        with patch("SpotifySync.addToPlaylist"):
            with patch("SpotifySync.reorderPlaylist"):
                sync(merged, [source], AUTH)

    mock_remove.assert_not_called()
    assert t1 in merged.tracks


def test_keeps_track_present_in_at_least_one_source():
    t1 = track("uri:1")
    merged = playlist("merged", t1)
    src_a = playlist("src_a")  # t1 absent
    src_b = playlist("src_b", t1)  # t1 present

    with patch("SpotifySync.removeFromPlaylist") as mock_remove:
        with patch("SpotifySync.addToPlaylist"):
            with patch("SpotifySync.reorderPlaylist"):
                sync(merged, [src_a, src_b], AUTH)

    mock_remove.assert_not_called()


def test_remove_failure_keeps_track_in_merged():
    t1, t2 = track("uri:1"), track("uri:2")
    merged = playlist("merged", t1, t2)
    source = playlist("src", t1)

    with patch("SpotifySync.removeFromPlaylist", side_effect=HTTPError()):
        with patch("SpotifySync.addToPlaylist"):
            with patch("SpotifySync.reorderPlaylist"):
                sync(merged, [source], AUTH)

    assert t2 in merged.tracks


# ── Add phase ─────────────────────────────────────────────────────────────────


def test_adds_track_missing_from_merged():
    t1 = track("uri:1")
    merged = playlist("merged")
    source = playlist("src", t1)

    with patch("SpotifySync.removeFromPlaylist"):
        with patch("SpotifySync.addToPlaylist") as mock_add:
            with patch("SpotifySync.reorderPlaylist"):
                sync(merged, [source], AUTH)

    mock_add.assert_called_once_with("merged", "uri:1", 0, AUTH)
    assert t1 in merged.tracks


def test_adds_at_correct_position_across_multiple_sources():
    t1, t2, t3 = track("uri:1"), track("uri:2"), track("uri:3")
    merged = playlist("merged")
    src_a = playlist("src_a", t1, t2)
    src_b = playlist("src_b", t3)

    with patch("SpotifySync.removeFromPlaylist"):
        with patch("SpotifySync.addToPlaylist") as mock_add:
            with patch("SpotifySync.reorderPlaylist"):
                sync(merged, [src_a, src_b], AUTH)

    assert mock_add.call_args_list == [
        call("merged", "uri:1", 0, AUTH),
        call("merged", "uri:2", 1, AUTH),
        call("merged", "uri:3", 2, AUTH),
    ]


def test_does_not_add_already_present_track():
    t1 = track("uri:1")
    merged = playlist("merged", t1)
    source = playlist("src", t1)

    with patch("SpotifySync.removeFromPlaylist"):
        with patch("SpotifySync.addToPlaylist") as mock_add:
            with patch("SpotifySync.reorderPlaylist"):
                sync(merged, [source], AUTH)

    mock_add.assert_not_called()


def test_add_failure_does_not_insert():
    t1, t2 = track("uri:1"), track("uri:2")
    merged = playlist("merged", t1)
    source = playlist("src", t1, t2)

    with patch("SpotifySync.removeFromPlaylist"):
        with patch("SpotifySync.addToPlaylist", side_effect=HTTPError()):
            with patch("SpotifySync.reorderPlaylist"):
                sync(merged, [source], AUTH)

    assert t2 not in merged.tracks


# ── Reorder phase ─────────────────────────────────────────────────────────────


def test_reorders_incorrectly_placed_track():
    t1, t2, t3, t4 = track("uri:1"), track("uri:2"), track("uri:3"), track("uri:4")
    merged = playlist("merged", t1, t2, t4, t3)
    src_a = playlist("src_a", t1, t2)
    src_b = playlist("src_b", t3, t4)

    with patch("SpotifySync.removeFromPlaylist"):
        with patch("SpotifySync.addToPlaylist"):
            with patch("SpotifySync.reorderPlaylist") as mock_reorder:
                sync(merged, [src_a, src_b], AUTH)

    mock_reorder.assert_called_once_with("merged", 3, 2, AUTH)
    assert merged.tracks == [t1, t2, t3, t4]


def test_does_not_reorder_correctly_placed_track():
    t1, t2, t3, t4 = track("uri:1"), track("uri:2"), track("uri:3"), track("uri:4")
    merged = playlist("merged", t1, t2, t3, t4)
    src_a = playlist("src_a", t1, t2)
    src_b = playlist("src_b", t3, t4)

    with patch("SpotifySync.removeFromPlaylist"):
        with patch("SpotifySync.addToPlaylist"):
            with patch("SpotifySync.reorderPlaylist") as mock_reorder:
                sync(merged, [src_a, src_b], AUTH)

    mock_reorder.assert_not_called()


def test_reorder_failure_does_not_reorder():
    t1, t2, t3 = track("uri:1"), track("uri:2"), track("uri:3")
    merged = playlist("merged", t1, t3, t2)
    source = playlist("src", t1, t2, t3)

    with patch("SpotifySync.removeFromPlaylist"):
        with patch("SpotifySync.addToPlaylist"):
            with patch("SpotifySync.reorderPlaylist", side_effect=HTTPError()):
                sync(merged, [source], AUTH)

    assert merged.tracks == [t1, t3, t2]


# ── Full sync integration test ────────────────────────────────────────────────


def test_full_sync_correct():
    t1, t2, t3, t4, t5, t6, t7 = (
        track("uri:1"),
        track("uri:2"),
        track("uri:3"),
        track("uri:4"),
        track("uri:5"),
        track("uri:6"),
        track("uri:7"),
    )
    merged = playlist("merged", t1, t3, t2, t4, t7, t6)
    src_a = playlist("src_a", t1, t2)
    src_b = playlist("src_b", t3)
    src_c = playlist("src_c", t4, t5)
    src_d = playlist("src_d", t6)

    with patch("SpotifySync.removeFromPlaylist") as mock_remove:
        with patch("SpotifySync.addToPlaylist") as mock_add:
            with patch("SpotifySync.reorderPlaylist") as mock_reorder:
                sync(merged, [src_a, src_b, src_c, src_d], AUTH)

    mock_remove.assert_called_once_with("merged", "uri:7", AUTH)
    mock_add.assert_called_once_with("merged", "uri:5", 4, AUTH)
    mock_reorder.assert_called_once_with("merged", 2, 1, AUTH)
    assert merged.tracks == [t1, t2, t3, t4, t5, t6]
