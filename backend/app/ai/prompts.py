import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
_SAFE_NAME = re.compile(r"[a-z][a-z0-9_]*")


class PromptNotFoundError(LookupError):
    """The requested prompt version doesn't exist or is empty."""


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    text: str

    @property
    def id(self) -> str:
        """Recorded with every AI result, so it can be traced to the exact prompt."""
        return f"{self.name}.v{self.version}"


class PromptRegistry:
    """Loads versioned prompt files (`<name>.v<version>.md`) from one folder."""

    def __init__(self, directory: Path = DEFAULT_PROMPT_DIR) -> None:
        self._directory = directory
        self._cache: dict[tuple[str, int], Prompt] = {}

    def get(self, name: str, version: int) -> Prompt:
        # A strict name pattern means a prompt name can never point outside the folder.
        if not _SAFE_NAME.fullmatch(name) or version < 1:
            raise ValueError("Prompt names are lowercase words; versions start at 1.")
        key = (name, version)
        if key not in self._cache:
            path = self._directory / f"{name}.v{version}.md"
            try:
                text = path.read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                raise PromptNotFoundError(f"Prompt {name}.v{version} not found") from None
            if not text:
                raise PromptNotFoundError(f"Prompt {name}.v{version} is empty")
            self._cache[key] = Prompt(name=name, version=version, text=text)
        return self._cache[key]
