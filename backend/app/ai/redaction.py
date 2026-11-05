"""Removes personal data from text before it is sent to an AI model, and puts it back in the
reply.

Detected by pattern: emails; phone numbers (US, and international ones starting with "+");
US Social Security numbers (dashes or spaces); dates written as 3/14/2012, 14.03.2012,
2012-03-14, 2012/03/14, March 14, 2012 or 14 March 2012; and numbers of 6+ digits, optionally
with a 1-3 letter prefix (S1234567).

Names are only removed if they are listed: arbitrary names can't be found reliably by pattern,
so unlisted names are NOT caught. The UI must still warn teachers not to include learner names.
A listed name matches in full and by runs of up to three consecutive parts (of 2+ letters,
split on spaces and hyphens), ignoring case, accents and the apostrophe style. Parts that are
also ordinary words ("Will", "An") are removed everywhere: names stay private at the cost of
masking those words.

Redacted text is NFC-normalised, so restored text may differ from the input in Unicode form.
"""

import re
import unicodedata
from collections.abc import Sequence

_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
    r"|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_ORDINAL = r"(?:st|nd|rd|th)?"
# Earlier entries win when overlapping matches are equally long.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Only "@" and the domain; the local part is found by scanning left (see _email_start).
    # A pattern for the whole address would retry from every letter of long text without "@",
    # which is quadratic.
    ("EMAIL", re.compile(r"@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("SSN", re.compile(r"\b\d{3}([- ])\d{2}\1\d{4}\b")),
    (
        "DATE",
        re.compile(
            r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\.\d{1,2}\.\d{4}"
            r"|\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"
            rf"|{_MONTH}\.? \d{{1,2}}{_ORDINAL},? \d{{4}}"
            rf"|\d{{1,2}}{_ORDINAL}(?: of)? {_MONTH}\.?,? \d{{4}})\b",
            re.IGNORECASE,
        ),
    ),
    (
        "PHONE",
        re.compile(
            r"(?<!\w)(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]\d{4}\b"
            r"|(?<![\w+])\+\d(?:[\s.-]?\d){4,14}(?!\w)"
        ),
    ),
    ("ID", re.compile(r"\b[A-Za-z]{0,3}\d{6,}\b")),
]
_PLACEHOLDER = re.compile(r"⟦([A-Z]+_\d+)⟧")
_MIN_NAME_LENGTH = 2  # shorter "names" ("I", "a") would wipe out ordinary words
_APOSTROPHES = "'’‘ʼ`"
_EMAIL_LOCAL_SYMBOLS = frozenset("!#$%&'*+-/=?^_`{|}~.")
_NAME_SEPARATORS = re.compile(r"[\s\-‐‑–—]+")
_MAX_NAME_RUN = 3  # runs of more parts than this only match as the full name


def _email_start(text: str, at: int) -> int:
    """Start of the local part before the "@" at `at`; letters may be accented. Each scan stops
    at the previous "@", so all scans together read the text once."""
    start = at
    while start and (text[start - 1].isalnum() or text[start - 1] in _EMAIL_LOCAL_SYMBOLS):
        start -= 1
    return start


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


def _accented_letters() -> dict[str, str]:
    """Maps each ASCII letter to its accented forms in the Latin blocks ("e" -> "èéêë…")."""
    groups: dict[str, list[str]] = {}
    for code in [*range(0xC0, 0x250), *range(0x1E00, 0x1F00)]:
        letter = chr(code)
        base = _strip_accents(letter).lower()
        if base != letter.lower() and len(base) == 1 and base.isascii() and base.isalpha():
            groups.setdefault(base, []).append(letter)
    return {base: "".join(letters) for base, letters in groups.items()}


_ACCENTED = _accented_letters()


def _fold(name: str) -> str:
    """The spelling-insensitive form of a name, used to give its variants one placeholder."""
    for apostrophe in _APOSTROPHES:
        name = name.replace(apostrophe, "'")
    return _NAME_SEPARATORS.sub(" ", _strip_accents(name).casefold()).strip()


def _letter_pattern(char: str) -> str:
    if char in _APOSTROPHES:
        return f"[{re.escape(_APOSTROPHES)}]"
    base = _strip_accents(char).lower()
    if len(base) == 1 and base in _ACCENTED:
        return f"[{base}{_ACCENTED[base]}]"
    return re.escape(char)


def _name_pattern(names: Sequence[str]) -> re.Pattern[str] | None:
    terms: dict[str, list[str]] = {}
    for name in names:
        parts = [p for p in _NAME_SEPARATORS.split(unicodedata.normalize("NFC", name)) if p]
        # Runs of consecutive parts: "Ana García-López" also yields "García López".
        runs = [parts] + [
            parts[i:j]
            for i in range(len(parts))
            for j in range(i + 1, min(i + _MAX_NAME_RUN, len(parts)) + 1)
        ]
        for run in runs:
            if len(_fold(" ".join(run))) >= _MIN_NAME_LENGTH:
                terms.setdefault(_fold(" ".join(run)), run)
    if not terms:
        return None
    # Longest first, so a full name becomes one placeholder rather than one per part.
    ordered = sorted(terms.items(), key=lambda item: len(item[0]), reverse=True)
    alternatives = "|".join(
        _NAME_SEPARATORS.pattern.join("".join(map(_letter_pattern, part)) for part in term)
        for _, term in ordered
    )
    # (?<!\w)/(?!\w) rather than \b, so names that start or end with punctuation still match.
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


class Redactor:
    """One per AI request: the same value always gets the same placeholder across every text
    redacted with it, so the model can still tell that two mentions are the same. For names,
    "the same" ignores case, accents and apostrophe style; the first spelling seen is restored.
    """

    def __init__(self, names: Sequence[str] = ()) -> None:
        self._patterns = list(_PATTERNS)
        name_pattern = _name_pattern(names)
        if name_pattern is not None:
            self._patterns.append(("NAME", name_pattern))
        self._placeholders: dict[tuple[str, str], str] = {}
        self._originals: dict[str, str] = {}
        self._counts: dict[str, int] = {}

    def redact(self, text: str) -> str:
        # Input can't contain real placeholders, or restoring a reply could inject someone's
        # data. All matches are found on the original text in one pass, so a name such as
        # "Name" can never match inside a placeholder.
        text = unicodedata.normalize("NFC", text).replace("⟦", "[").replace("⟧", "]")
        matches: list[tuple[int, int, int, str]] = []
        for priority, (kind, pattern) in enumerate(self._patterns):
            for m in pattern.finditer(text):
                start = _email_start(text, m.start()) if kind == "EMAIL" else m.start()
                matches.append((start, m.end(), priority, kind))
        matches.sort()
        # Overlapping matches merge into one span, so no part of either is left visible. The
        # span takes the kind of its longest match (the earliest pattern on a tie).
        spans: list[tuple[int, int, int, int, str]] = []  # start, end, length, priority, kind
        for start, end, priority, kind in matches:
            if spans and start < spans[-1][1]:
                first, last, length, best, best_kind = spans[-1]
                if (end - start, -priority) > (length, -best):
                    length, best, best_kind = end - start, priority, kind
                spans[-1] = (first, max(last, end), length, best, best_kind)
            else:
                spans.append((start, end, end - start, priority, kind))
        parts: list[str] = []
        position = 0
        for start, end, _length, _priority, kind in spans:
            parts += [text[position:start], self._placeholder(kind, text[start:end])]
            position = end
        parts.append(text[position:])
        return "".join(parts)

    def restore(self, text: str) -> str:
        """Puts originals back. Unknown or damaged placeholders are left exactly as they are."""
        return _PLACEHOLDER.sub(lambda m: self._originals.get(m.group(0), m.group(0)), text)

    def _placeholder(self, kind: str, value: str) -> str:
        key = (kind, _fold(value) if kind == "NAME" else value)
        if key not in self._placeholders:
            self._counts[kind] = self._counts.get(kind, 0) + 1
            placeholder = f"⟦{kind}_{self._counts[kind]}⟧"
            self._placeholders[key] = placeholder
            self._originals[placeholder] = value
        return self._placeholders[key]
