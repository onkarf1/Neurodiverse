import pytest

from tests.db_fixtures import database_tests_required


@pytest.mark.parametrize(
    ("environ", "required"),
    [
        ({}, False),
        ({"CI": "true"}, True),
        ({"CI": "1"}, True),
        ({"CI": "false"}, False),
        ({"CI": "0"}, False),
        ({"CI": ""}, False),
        ({"REQUIRE_DB_TESTS": "yes"}, True),
        ({"REQUIRE_DB_TESTS": "TRUE"}, True),
        ({"CI": "false", "REQUIRE_DB_TESTS": "1"}, True),
    ],
)
def test_missing_database_fails_only_when_explicitly_required(
    environ: dict[str, str], required: bool
) -> None:
    assert database_tests_required(environ) is required
