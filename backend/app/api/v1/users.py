from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, SessionDep
from app.repositories.users import list_users_in_school
from app.schemas.users import UserPage, UserSummary

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "",
    responses={
        401: {"description": "Missing, invalid, or expired token"},
        403: {"description": "Signed-in user is not an admin"},
    },
)
async def list_users(
    admin: AdminUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    # Capped so a request can't force the database to skip arbitrarily many rows.
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> UserPage:
    """Users in the admin's own school. Other schools' users are never visible."""
    users = await list_users_in_school(session, admin.school_id, limit=limit, offset=offset)
    items = [UserSummary(id=u.id, email=u.email, role=u.role, is_active=u.is_active) for u in users]
    return UserPage(items=items, limit=limit, offset=offset)
