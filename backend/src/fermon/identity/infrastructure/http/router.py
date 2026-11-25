from uuid import UUID

from fastapi import APIRouter, Response, status

from fermon.identity.infrastructure.http.dependencies import (
    AdminUserDep,
    ChangeOwnPasswordDep,
    ClientIpDep,
    CreateUserDep,
    CurrentUserAllowingPasswordChangeDep,
    ListUsersDep,
    LoginDep,
    LogoutDep,
    ResetUserPasswordDep,
    SessionSettingsDep,
    SessionTokenDep,
    UpdateUserDep,
)
from fermon.identity.infrastructure.http.schemas import (
    ChangePasswordIn,
    CreateUserIn,
    LoginIn,
    ResetPasswordIn,
    SessionOut,
    UpdateUserIn,
    UserOut,
)
from fermon.identity.infrastructure.http.session_cookie import (
    clear_session_cookie,
    set_session_cookie,
)

router = APIRouter()


@router.post("/auth/login")
async def login(
    body: LoginIn,
    response: Response,
    use_case: LoginDep,
    settings: SessionSettingsDep,
    client_ip: ClientIpDep,
) -> SessionOut:
    user, token = await use_case.execute(body.email, body.password, client_ip)
    set_session_cookie(response, token, settings)
    return SessionOut(user=UserOut.from_domain(user))


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response, token: SessionTokenDep, use_case: LogoutDep, settings: SessionSettingsDep
) -> None:
    await use_case.execute(token)
    clear_session_cookie(response, settings)


@router.get("/auth/me")
async def me(user: CurrentUserAllowingPasswordChangeDep) -> SessionOut:
    return SessionOut(user=UserOut.from_domain(user))


@router.post("/auth/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordIn,
    user: CurrentUserAllowingPasswordChangeDep,
    token: SessionTokenDep,
    use_case: ChangeOwnPasswordDep,
) -> None:
    assert token is not None  # the user dependency already rejected a missing token
    await use_case.execute(user, token, body.current_password, body.new_password)


@router.get("/users")
async def list_users(actor: AdminUserDep, use_case: ListUsersDep) -> list[UserOut]:
    return [UserOut.from_domain(user) for user in await use_case.execute(actor)]


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(body: CreateUserIn, actor: AdminUserDep, use_case: CreateUserDep) -> UserOut:
    user = await use_case.execute(
        actor, body.email, body.display_name, body.role, body.temporary_password
    )
    return UserOut.from_domain(user)


@router.patch("/users/{user_id}")
async def update_user(
    user_id: UUID, body: UpdateUserIn, actor: AdminUserDep, use_case: UpdateUserDep
) -> UserOut:
    user = await use_case.execute(
        actor,
        user_id,
        body.version,
        role=body.role,
        active=body.active,
        display_name=body.display_name,
    )
    return UserOut.from_domain(user)


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    user_id: UUID, body: ResetPasswordIn, actor: AdminUserDep, use_case: ResetUserPasswordDep
) -> None:
    await use_case.execute(actor, user_id, body.temporary_password)
