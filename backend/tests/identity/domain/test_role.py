import pytest

from fermon.identity.domain import (
    Role,
    can_acknowledge_alerts,
    can_download_reports,
    can_manage_users,
    can_record_lab_analyses,
    can_write_batches,
    can_write_quality_profiles,
)

# role -> (manage users, write batches, acknowledge alerts, download reports,
#          write quality profiles, record lab analyses)
PERMISSIONS = {
    Role.ADMIN: (True, True, True, True, True, True),
    Role.BREWER: (False, True, True, True, True, True),
    Role.VIEWER: (False, False, False, True, False, False),
}


@pytest.mark.parametrize("role", list(Role))
def test_permission_table(role: Role) -> None:
    granted = (
        can_manage_users(role),
        can_write_batches(role),
        can_acknowledge_alerts(role),
        can_download_reports(role),
        can_write_quality_profiles(role),
        can_record_lab_analyses(role),
    )
    assert granted == PERMISSIONS[role]


def test_role_values_are_the_stored_names() -> None:
    assert [r.value for r in Role] == ["admin", "brewer", "viewer"]
