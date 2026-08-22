from v3_identity import parse_id_text, render_id_text


def test_standalone_hotload_assignment_and_canonical_render():
    enabled = parse_id_text("HOTLOAD = YES\n", source_name="ID.txt")
    disabled = parse_id_text("hotload=no\n", source_name="ID.txt")
    assert enabled["hotload_capable"] is True
    assert disabled["hotload_capable"] is False
    assert "HOTLOAD = YES" in render_id_text(enabled)
    assert "HotloadCapable" not in render_id_text(enabled)
