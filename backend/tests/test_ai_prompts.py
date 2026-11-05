from pathlib import Path

import pytest

from app.ai.prompts import DEFAULT_PROMPT_DIR, PromptNotFoundError, PromptRegistry


def test_loads_a_versioned_prompt(tmp_path: Path) -> None:
    (tmp_path / "check.v2.md").write_text("  You check worksheets.\n")

    prompt = PromptRegistry(tmp_path).get("check", 2)

    assert (prompt.name, prompt.version, prompt.text) == ("check", 2, "You check worksheets.")
    assert prompt.id == "check.v2"


def test_missing_prompt_names_the_file(tmp_path: Path) -> None:
    with pytest.raises(PromptNotFoundError, match="check.v9"):
        PromptRegistry(tmp_path).get("check", 9)


def test_empty_prompt_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "check.v1.md").write_text("   \n")

    with pytest.raises(PromptNotFoundError):
        PromptRegistry(tmp_path).get("check", 1)


@pytest.mark.parametrize(
    ("name", "version"),
    [("../secrets", 1), ("check/../x", 1), ("Check", 1), ("", 1), ("check", 0), ("check", -1)],
    ids=["parent folder", "nested path", "uppercase", "empty", "version 0", "negative version"],
)
def test_only_simple_names_and_positive_versions_are_allowed(
    tmp_path: Path, name: str, version: int
) -> None:
    # Prompt names must never reach outside the prompts folder.
    with pytest.raises(ValueError):
        PromptRegistry(tmp_path).get(name, version)


def test_default_prompt_folder_ships_inside_the_app_package() -> None:
    # Only app/ is copied into the Docker image, so prompts must live under it.
    assert DEFAULT_PROMPT_DIR.parts[-3:] == ("app", "ai", "prompts")
