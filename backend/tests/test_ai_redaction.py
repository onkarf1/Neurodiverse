import time
import unicodedata

import pytest

from app.ai.redaction import Redactor


@pytest.mark.parametrize(
    ("text", "secret", "kind"),
    [
        ("Email maria.lopez+1@school.example today", "maria.lopez+1@school.example", "EMAIL"),
        ("Email josé.núñez@school.example today", "josé.núñez@school.example", "EMAIL"),
        ("Contact maria@école.example", "maria@école.example", "EMAIL"),
        ("Email maria_lopez@school.example today", "maria_lopez@school.example", "EMAIL"),
        ("Call (602) 555-0142 after class", "(602) 555-0142", "PHONE"),
        ("Call 602.555.0142 after class", "602.555.0142", "PHONE"),
        ("Call +1 602-555-0142 after class", "+1 602-555-0142", "PHONE"),
        ("SSN 123-45-6789 on file", "123-45-6789", "SSN"),
        ("Born 03/14/2012 in Mesa", "03/14/2012", "DATE"),
        ("Born 2012-03-14 in Mesa", "2012-03-14", "DATE"),
        ("Born March 14, 2012 in Mesa", "March 14, 2012", "DATE"),
        ("Born Mar 14th 2012 in Mesa", "Mar 14th 2012", "DATE"),
        ("Student ID 20481937 enrolled", "20481937", "ID"),
        ("Born 14 March 2012 in Mesa", "14 March 2012", "DATE"),
        ("Born 14th of March, 2012 in Mesa", "14th of March, 2012", "DATE"),
        ("Born 14.03.2012 in Mesa", "14.03.2012", "DATE"),
        ("Born 2012/03/14 in Mesa", "2012/03/14", "DATE"),
        ("SSN 123 45 6789 on file", "123 45 6789", "SSN"),
        ("Student ID S1234567 enrolled", "S1234567", "ID"),
        ("Call +44 20 7946 0958 after class", "+44 20 7946 0958", "PHONE"),
    ],
)
def test_personal_data_is_replaced_and_restored(text: str, secret: str, kind: str) -> None:
    redactor = Redactor()

    redacted = redactor.redact(text)

    assert redacted == text.replace(secret, f"⟦{kind}_1⟧")
    assert redactor.restore(redacted) == text


@pytest.mark.parametrize(
    "text",
    [
        "Step 3: put 2 cards in each of the 12 bags",
        "Work for 15 minutes, then take a 5 minute break at 3:30",
        "Pack 1,200 envelopes in 45 boxes",
        "Use the 2026 schedule",
        "Read section 1.2.10 and score 3/4 on pages 12-14",
        "Add +5 points, then 2 + 3 = 5",
    ],
)
def test_ordinary_numbers_are_left_alone(text: str) -> None:
    assert Redactor().redact(text) == text


def test_listed_names_are_removed_in_full_and_in_parts() -> None:
    redactor = Redactor(names=["Maria Lopez"])

    redacted = redactor.redact("Maria Lopez packs kits. Ms. LOPEZ checks them; maria smiles.")

    assert "maria" not in redacted.lower()
    assert "lopez" not in redacted.lower()
    assert (
        redactor.restore(redacted) == "Maria Lopez packs kits. Ms. LOPEZ checks them; maria smiles."
    )


@pytest.mark.parametrize(
    ("listed", "written", "expected"),
    [
        # Decomposed, as pasted from a Mac or a PDF.
        ("José", unicodedata.normalize("NFD", "José"), "⟦NAME_1⟧"),
        ("O'Brien", "O’Brien", "⟦NAME_1⟧"),  # curly apostrophe from Word or Google Docs
        ("Ana García-López", "Ms. López", "Ms. ⟦NAME_1⟧"),  # part of a hyphenated surname
        ("Ana García-López", "García López", "⟦NAME_1⟧"),
        ("José", "Jose", "⟦NAME_1⟧"),  # accent dropped
        ("Jose", "José", "⟦NAME_1⟧"),  # accent added
        ("Thu Nguyen", "Nguyễn", "⟦NAME_1⟧"),
    ],
)
def test_listed_names_are_caught_in_common_spelling_variants(
    listed: str, written: str, expected: str
) -> None:
    redactor = Redactor(names=[listed])

    redacted = redactor.redact(f"Task for {written} today")

    assert redacted == f"Task for {expected} today"
    assert redactor.restore(redacted) == unicodedata.normalize("NFC", f"Task for {written} today")


def test_a_full_name_gets_one_placeholder() -> None:
    assert Redactor(names=["Maria Lopez"]).redact("Maria Lopez packs") == "⟦NAME_1⟧ packs"


def test_spellings_of_the_same_name_share_a_placeholder() -> None:
    # The model must see that "Maria" and "maria" are one person; the first spelling is restored.
    redactor = Redactor(names=["Maria"])

    redacted = redactor.redact("Maria helps maria")

    assert redacted == "⟦NAME_1⟧ helps ⟦NAME_1⟧"
    assert redactor.restore(redacted) == "Maria helps Maria"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("(602)Maria Lopez@x.com", "(602)⟦EMAIL_1⟧"),
        ("kim@a.org11lee@b.org", "⟦EMAIL_1⟧"),  # second email starts inside the first's domain
    ],
)
def test_overlapping_matches_are_removed_as_one_span(text: str, expected: str) -> None:
    # Skipping the later, overlapping match would leave the rest of it visible.
    redactor = Redactor(names=["Maria Lopez"])

    redacted = redactor.redact(text)

    assert redacted == expected
    assert redactor.restore(redacted) == text


def test_names_match_whole_words_only() -> None:
    redactor = Redactor(names=["Ann"])

    assert redactor.redact("Annual review with Ann") == "Annual review with ⟦NAME_1⟧"


@pytest.mark.parametrize("name", ["José Núñez", "O'Brien", "Lee (Jr.)", "A+B"])
def test_names_with_accents_or_symbols_are_handled(name: str) -> None:
    redactor = Redactor(names=[name])

    redacted = redactor.redact(f"Task for {name} today")

    assert name not in redacted
    assert redactor.restore(redacted) == f"Task for {name} today"


def test_blank_or_one_letter_names_are_ignored() -> None:
    # A one-letter "name" would wipe out every "a" or "I" in the text.
    redactor = Redactor(names=["", "   ", "I", "a"])

    assert redactor.redact("I packed a box") == "I packed a box"


def test_same_value_gets_the_same_placeholder_across_texts() -> None:
    redactor = Redactor(names=["Maria"])

    goal = redactor.redact("Maria plans the task")
    worksheet = redactor.redact("Maria, put the cards in order. Email kim@school.example")

    assert goal == "⟦NAME_1⟧ plans the task"
    assert worksheet == "⟦NAME_1⟧, put the cards in order. Email ⟦EMAIL_1⟧"


def test_different_values_get_different_placeholders() -> None:
    redactor = Redactor()

    redacted = redactor.redact("a@school.example and b@school.example")

    assert redacted == "⟦EMAIL_1⟧ and ⟦EMAIL_2⟧"


def test_input_cannot_impersonate_a_placeholder() -> None:
    # If text could contain a real placeholder, restoring a reply would inject someone's data.
    redactor = Redactor()
    redactor.redact("Contact kim@school.example")

    redacted = redactor.redact("The worksheet literally says ⟦EMAIL_1⟧")

    assert "⟦" not in redacted
    assert redactor.restore(redacted) == "The worksheet literally says [EMAIL_1]"


def test_unknown_or_damaged_placeholders_in_replies_are_left_as_is() -> None:
    redactor = Redactor()
    redactor.redact("Contact kim@school.example")

    reply = "Mention ⟦EMAIL_1⟧, ⟦EMAIL_9⟧ and ⟦EMAIL_1"

    assert redactor.restore(reply) == "Mention kim@school.example, ⟦EMAIL_9⟧ and ⟦EMAIL_1"


def test_text_without_personal_data_is_unchanged() -> None:
    text = "Order the three steps: open the box, fold the shirt, close the box."

    assert Redactor(names=["Maria"]).redact(text) == text


def test_names_that_look_like_placeholder_words_never_corrupt_placeholders() -> None:
    # A learner could really be called "Name" or "Email"; placeholders must stay intact.
    redactor = Redactor(names=["Name", "Email", "June"])
    text = "Name emails kim@school.example on June 5, 2012; Email helps."

    redacted = redactor.redact(text)

    assert "kim@" not in redacted
    assert redactor.restore(redacted) == text


def test_an_email_containing_a_listed_name_is_removed_whole() -> None:
    redactor = Redactor(names=["Maria"])

    assert redactor.redact("Write to maria@school.example") == "Write to ⟦EMAIL_1⟧"


@pytest.mark.parametrize(
    "text",
    ["a" * 300_000, "1" * 300_000, "a." * 150_000, "123-" * 75_000, "@a" * 150_000],
    ids=["letters", "digits", "dots", "dashed digits", "many @"],
)
def test_long_adversarial_text_is_redacted_quickly(text: str) -> None:
    # Requests can be up to 1 MB; a pattern that rescans from every position would let one
    # request tie up the server for minutes.
    started = time.perf_counter()

    Redactor(names=["Maria Lopez"]).redact(text)

    assert time.perf_counter() - started < 2


def test_a_name_with_many_parts_is_handled_quickly() -> None:
    started = time.perf_counter()

    Redactor(names=[" ".join(f"Part{i}" for i in range(60))]).redact("word " * 100_000)

    assert time.perf_counter() - started < 2
