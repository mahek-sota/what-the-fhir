from fhirlearn.report import update_history


def test_first_build_is_v1():
    h, cur, added = update_history([], "d1", "l1", "2026-11-10", None, "2026-11-10 12:00")
    assert added and cur["version"] == 1 and cur["note"] == "First version"
    assert cur["changes"] == ["data", "layout"]


def test_no_change_keeps_version():
    h, _, _ = update_history([], "d1", "l1", "2026-11-10", None, "t1")
    h2, cur, added = update_history(h, "d1", "l1", "2026-11-10", "ignored", "t2")
    assert not added and cur["version"] == 1 and len(h2) == 1


def test_data_change_bumps_with_note():
    h, _, _ = update_history([], "d1", "l1", "2026-11-10", None, "t1")
    h, cur, added = update_history(h, "d2", "l1", "2026-12-01", "December refresh", "t2")
    assert added and cur["version"] == 2 and cur["changes"] == ["data"]
    assert cur["note"] == "December refresh" and cur["fetched"] == "2026-12-01"


def test_layout_change_default_note():
    h, _, _ = update_history([], "d1", "l1", "x", None, "t1")
    _, cur, _ = update_history(h, "d1", "l2", "x", None, "t2")
    assert cur["changes"] == ["layout"] and cur["note"] == "Layout updated"


def test_pack_roundtrip_and_version_of():
    from fhirlearn.report import pack, unpack, version_of
    html = '<html><script>const DATA = {"version":{"version":3,"note":"x"}};</script></html>'
    assert unpack(pack(html)) == html
    assert version_of(html) == 3
    assert version_of("<html></html>") is None
