"""Spec section 13 -- README_PROFILE_MOD_PATHING.md must describe the final
architecture accurately and must never be rewritten to "save paths are
derived only". It also locks the staging-first hosted-runtime contract.
"""

from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README_PROFILE_MOD_PATHING.md"


def _read() -> str:
    return " ".join(README.read_text(encoding="utf-8").split())


def test_readme_exists_and_is_nontrivial() -> None:
    assert README.is_file()
    assert len(_read()) > 3500


def test_readme_documents_profile_ownership_concepts() -> None:
    source = _read()
    for concept in (
        "**Machine**",
        "**Profile**",
        "**World**",
        "**DragonConnect**",
    ):
        assert concept in source, f"README must document {concept}"


def test_readme_never_claims_save_paths_are_derived_only() -> None:
    source = _read().casefold()
    # The spec is explicit: "Do NOT rewrite it to 'save paths are derived
    # only.'" Explicit machine-authored executable + Saved directory
    # selection must remain documented.
    assert "save paths are derived only" not in source
    assert "dragonwilds save directory" in source or "saved directory" in source
    assert "never an individual" in source  # "a directory, never an individual .sav file"


def test_readme_documents_mapped_destinations_as_overrideable() -> None:
    source = _read()
    assert "overrideable" in source or "override" in source
    assert "mod_overrides" in source


def test_readme_documents_runtime_architecture_declaration_model() -> None:
    source = _read()
    assert "runtime_architecture" in source
    assert "required" in source and "forbidden" in source and "standalone" in source


def test_readme_retires_hosted_runtime_management() -> None:
    source = _read()
    assert "no per-file runtime selector" in source
    assert "<AppData>/Loaders" in source
    assert "Profile/Mods" in source
    assert "staged/loaders/ue4ss" in source
    assert "never reintroduce" in source.casefold()


def test_readme_documents_chat_bridge_removal() -> None:
    source = _read()
    assert "removed entirely" in source
    assert "chat" in source.casefold()


def test_readme_branch_rule_matches_the_actual_working_branch() -> None:
    source = _read()
    assert "push target for this work is `experimental`" in source


def main() -> None:
    tests = [value for name, value in list(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"README_PROFILE_MOD_PATHING.md contract (spec section 13): PASS ({len(tests)} checks)")


if __name__ == "__main__":
    main()
