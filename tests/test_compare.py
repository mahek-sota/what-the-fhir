from fhirlearn.compare import render


def test_render_marks_capped_and_unavailable():
    md = render({
        "smart": "skipped (server unreachable).",
        "hapi": {"patients": (50, False), "diabetes": (154, False), "hba1c": (888, True), "hba1c_high": (309, True)},
    }, "2026-11-10")
    assert "| | SMART | HAPI |" in md
    assert "| n/a | 154 |" in md
    assert "| n/a | 888* |" in md
    assert "**SMART n/a:** skipped (server unreachable)." in md
