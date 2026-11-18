from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbSession, SettingsDep
from app.core.rate_limit import LOGIN, REGISTER, by_ip
from app.domains.auth import service
from app.domains.auth.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(by_ip(REGISTER))],
)
def register(body: RegisterRequest, session: DbSession) -> UserOut:
    return UserOut.model_validate(service.register(session, body))


@router.post("/login", response_model=TokenPair, dependencies=[Depends(by_ip(LOGIN))])
def login(body: LoginRequest, session: DbSession, settings: SettingsDep) -> TokenPair:
    return service.login(session, body.email, body.password, settings)


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshRequest, session: DbSession, settings: SettingsDep) -> TokenPair:
    return service.refresh(session, body.refresh_token, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshRequest, session: DbSession) -> None:
    service.logout(session, body.refresh_token)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    """The signed-in account (email, admin flag). The profile lives at /candidates/me."""
    return UserOut.model_validate(user)
