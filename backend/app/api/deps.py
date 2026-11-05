from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.security import InvalidTokenError, PasswordWorker, decode_access_token
from app.db.health import DatabaseProbe
from app.models import User
from app.repositories.users import get_user_by_id

_bearer = HTTPBearer(auto_error=False, description="Access token from POST /v1/auth/login")


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_database_probe(request: Request) -> DatabaseProbe:
    return cast(DatabaseProbe, request.app.state.database_probe)


def get_password_worker(request: Request) -> PasswordWorker:
    return cast(PasswordWorker, request.app.state.password_worker)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request. Anything not committed is rolled back when it closes."""
    factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    async with factory() as session:
        yield session


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """The signed-in user. Loaded fresh on every request, so disabling an account takes
    effect immediately instead of when its token expires."""
    if credentials is None:
        raise unauthorized("Authentication required.")
    try:
        user_id = decode_access_token(credentials.credentials, settings)
    except InvalidTokenError:
        raise unauthorized("Authentication required.") from None
    user = await get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        raise unauthorized("Authentication required.")
    return user


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
PasswordWorkerDep = Annotated[PasswordWorker, Depends(get_password_worker)]
CurrentUser = Annotated[User, Depends(get_current_user)]
