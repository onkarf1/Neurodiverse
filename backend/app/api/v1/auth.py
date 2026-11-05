from fastapi import APIRouter

from app.api.deps import CurrentUser, PasswordWorkerDep, SessionDep, SettingsDep, unauthorized
from app.core.security import create_access_token
from app.schemas.auth import CurrentUserResponse, LoginRequest, TokenResponse
from app.services.auth import AuthenticationFailed, authenticate

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", responses={401: {"description": "Invalid email or password"}})
async def login(
    body: LoginRequest, session: SessionDep, passwords: PasswordWorkerDep, settings: SettingsDep
) -> TokenResponse:
    try:
        user = await authenticate(session, passwords, body.email, body.password.get_secret_value())
    except AuthenticationFailed:
        # One message for every failure, so responses never reveal which accounts exist.
        raise unauthorized("Invalid email or password.") from None
    token = create_access_token(user.id, settings)
    return TokenResponse(access_token=token.value, expires_in=token.expires_in)


@router.get("/me", responses={401: {"description": "Missing, invalid, or expired token"}})
async def me(user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=user.id, email=user.email, role=user.role, school_id=user.school_id
    )
