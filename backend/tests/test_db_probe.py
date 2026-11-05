import logging

import pytest

from app.db.health import DatabaseProbe

pytestmark = pytest.mark.anyio


class ScriptedProbe(DatabaseProbe):
    """Replaces the network call with a scripted sequence of outcomes."""

    def __init__(self, outcomes: list[Exception | None]) -> None:
        super().__init__("postgresql+asyncpg://u:p@127.0.0.1:1/unused", timeout_seconds=1)
        self._outcomes = outcomes

    async def _ping(self) -> None:
        outcome = self._outcomes.pop(0)
        if outcome is not None:
            raise outcome


def _probe_logs(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "app.db.health"]


async def test_only_the_first_failure_logs_a_traceback(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.db.health")
    probe = ScriptedProbe([OSError("refused"), OSError("refused"), OSError("refused")])

    results = [await probe.check() for _ in range(3)]

    logs = _probe_logs(caplog)
    assert results == [False, False, False]
    assert [r.exc_info is not None for r in logs] == [True, False, False]
    assert logs[1].__dict__["error_type"] == "OSError"


async def test_recovery_is_logged_once(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.db.health")
    probe = ScriptedProbe([OSError("refused"), None, None])

    results = [await probe.check() for _ in range(3)]

    messages = [r.getMessage() for r in _probe_logs(caplog)]
    assert results == [False, True, True]
    assert messages == ["Database became unavailable", "Database is available again"]
