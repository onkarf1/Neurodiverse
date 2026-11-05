import threading
import time

import anyio
import pytest
from argon2 import PasswordHasher

from app.core import security
from app.core.security import (
    PasswordWorker,
    PasswordWorkerBusy,
    hash_password,
    password_needs_rehash,
    verify_password,
)

PASSWORD = "correct horse battery staple"


def test_hash_is_argon2id_and_does_not_contain_the_password() -> None:
    hashed = hash_password(PASSWORD)

    assert hashed.startswith("$argon2id$")
    assert PASSWORD not in hashed


def test_each_hash_uses_a_new_salt() -> None:
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_only_the_right_password_verifies() -> None:
    hashed = hash_password(PASSWORD)

    assert verify_password(PASSWORD, hashed)
    assert not verify_password(PASSWORD + "x", hashed)


def test_equivalent_unicode_spellings_match() -> None:
    # "é" as one character vs "e" plus a combining accent: different bytes, same text.
    composed, decomposed = "caf\u00e9-terrace-2026", "cafe\u0301-terrace-2026"

    assert verify_password(decomposed, hash_password(composed))


@pytest.mark.parametrize("bad_hash", ["", "not-a-hash", "$argon2id$v=19$m=65536,t=3,p=4$broken"])
def test_corrupted_hash_counts_as_a_mismatch(bad_hash: str) -> None:
    assert not verify_password(PASSWORD, bad_hash)


def test_hashes_with_weaker_settings_are_flagged_for_upgrade() -> None:
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)

    assert password_needs_rehash(weak)
    assert not password_needs_rehash(hash_password(PASSWORD))


LONE_SURROGATE = "\ud800"  # valid in JSON strings, but can't be encoded as UTF-8


def test_unencodable_password_verifies_as_false_instead_of_crashing() -> None:
    assert not verify_password(LONE_SURROGATE, hash_password(PASSWORD))


def test_unencodable_password_cannot_be_hashed() -> None:
    with pytest.raises(ValueError, match="can't be encoded"):
        hash_password(LONE_SURROGATE)


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["verify", "hash"])
async def test_password_work_never_exceeds_the_concurrency_limit(
    monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    # Each Argon2 hash uses 64 MiB, so unbounded parallel logins could exhaust memory.
    active = peak = 0
    lock = threading.Lock()

    def slow(*_args: str) -> str:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return "done"

    monkeypatch.setattr(security, "verify_password", slow)
    monkeypatch.setattr(security, "hash_password", slow)
    worker = PasswordWorker(max_concurrent=2, max_waiting=10)

    async def run() -> None:
        if operation == "verify":
            await worker.verify("password", "hash")
        else:
            await worker.hash("password")

    async with anyio.create_task_group() as tasks:
        for _ in range(6):
            tasks.start_soon(run)

    assert peak == 2


@pytest.mark.anyio
async def test_unknown_emails_are_checked_against_the_placeholder_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked: list[str] = []

    def record(_password: str, password_hash: str) -> bool:
        checked.append(password_hash)
        return False

    monkeypatch.setattr(security, "verify_password", record)

    await PasswordWorker(max_concurrent=1, max_waiting=1).verify_against_dummy("guess")

    assert checked == [security._dummy_hash()]


@pytest.mark.anyio
async def test_excess_password_work_fails_fast_instead_of_queueing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A flood of login attempts must not make real logins wait for seconds.
    release = threading.Event()
    monkeypatch.setattr(security, "verify_password", lambda *_: release.wait(5))
    worker = PasswordWorker(max_concurrent=1, max_waiting=2)

    async with anyio.create_task_group() as tasks:
        for _ in range(3):  # one running, two waiting: the limit
            tasks.start_soon(worker.verify, "password", "hash")
        await anyio.sleep(0.05)
        with pytest.raises(PasswordWorkerBusy):
            await worker.verify("password", "hash")
        release.set()

    assert await worker.verify("password", "hash")  # capacity is freed afterwards


def test_timing_placeholder_is_ready_before_the_first_login() -> None:
    # Computing it lazily would make the first unknown-email login measurably slower.
    security._dummy_hash.cache_clear()

    PasswordWorker(max_concurrent=1, max_waiting=1)

    assert security._dummy_hash.cache_info().currsize == 1
