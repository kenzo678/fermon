import pytest

from fermon.identity.domain import (
    Role,
    can_acknowledge_alerts,
    can_download_reports,
    can_manage_users,
    can_write_batches,
)

# role -> (manage users, write batches, acknowledge alerts, download reports)
PERMISSIONS = {
    Role.ADMIN: (True, True, True, True),
    Role.BREWER: (False, True, True, True),
    Role.VIEWER: (False, False, False, True),
}


@pytest.mark.parametrize("role", list(Role))
def test_permission_table(role: Role) -> None:
    granted = (
        can_manage_users(role),
        can_write_batches(role),
        can_acknowledge_alerts(role),
        can_download_reports(role),
    )
    assert granted == PERMISSIONS[role]


def test_role_values_are_the_stored_names() -> None:
    assert [r.value for r in Role] == ["admin", "brewer", "viewer"]
