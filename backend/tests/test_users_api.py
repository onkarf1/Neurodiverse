import pytest
from fastapi.testclient import TestClient

from app.core.constants import PROBLEM_JSON
from app.models import UserRole
from tests.auth_fixtures import TEST_PASSWORD, SeedUser, update_user

USERS = "/v1/users"


def _auth(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/v1/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_listing_users_requires_sign_in(auth_client: TestClient) -> None:
    assert auth_client.get(USERS).status_code == 401


def test_teachers_cannot_list_users(auth_client: TestClient, seed_user: SeedUser) -> None:
    seed_user("teacher@example.com")

    response = auth_client.get(USERS, headers=_auth(auth_client, "teacher@example.com"))

    assert response.status_code == 403
    assert response.headers["content-type"] == PROBLEM_JSON


def test_admins_see_only_their_own_school(auth_client: TestClient, seed_user: SeedUser) -> None:
    admin = seed_user("admin@north.example", role=UserRole.ADMIN, school="North")
    seed_user("Bob@north.example", school="North")
    seed_user("alice@north.example", school="North", is_active=False)
    seed_user("teacher@south.example", school="South")

    response = auth_client.get(USERS, headers=_auth(auth_client, admin.email))

    assert response.status_code == 200
    items = response.json()["items"]
    # Sorted by email regardless of case; the other school's user never appears.
    assert [u["email"] for u in items] == [
        "admin@north.example",
        "alice@north.example",
        "Bob@north.example",
    ]
    assert items[1]["is_active"] is False
    assert set(items[0]) == {"id", "email", "role", "is_active"}  # never the password hash


def test_users_are_returned_in_pages(auth_client: TestClient, seed_user: SeedUser) -> None:
    admin = seed_user("a-admin@example.com", role=UserRole.ADMIN)
    for name in ("b", "c", "d"):
        seed_user(f"{name}@example.com")
    headers = _auth(auth_client, admin.email)

    first = auth_client.get(USERS, params={"limit": 2}, headers=headers).json()
    second = auth_client.get(USERS, params={"limit": 2, "offset": 2}, headers=headers).json()

    assert [u["email"] for u in first["items"]] == ["a-admin@example.com", "b@example.com"]
    assert [u["email"] for u in second["items"]] == ["c@example.com", "d@example.com"]
    assert (second["limit"], second["offset"]) == (2, 2)


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 10_001}, {"limit": "many"}],
    ids=["limit zero", "limit too large", "negative offset", "offset too deep", "not a number"],
)
def test_invalid_paging_is_rejected(
    auth_client: TestClient, seed_user: SeedUser, params: dict[str, int | str]
) -> None:
    admin = seed_user("admin@example.com", role=UserRole.ADMIN)

    response = auth_client.get(USERS, params=params, headers=_auth(auth_client, admin.email))

    assert response.status_code == 422


def test_demoted_admin_loses_access_on_the_next_request(
    auth_client: TestClient, seed_user: SeedUser, clean_database: str
) -> None:
    admin = seed_user("admin@example.com", role=UserRole.ADMIN)
    headers = _auth(auth_client, admin.email)
    assert auth_client.get(USERS, headers=headers).status_code == 200

    update_user(clean_database, admin.id, role=UserRole.TEACHER)

    assert auth_client.get(USERS, headers=headers).status_code == 403


def test_disabled_admin_is_rejected(
    auth_client: TestClient, seed_user: SeedUser, clean_database: str
) -> None:
    admin = seed_user("admin@example.com", role=UserRole.ADMIN)
    headers = _auth(auth_client, admin.email)

    update_user(clean_database, admin.id, is_active=False)

    assert auth_client.get(USERS, headers=headers).status_code == 401
