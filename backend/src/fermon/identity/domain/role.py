from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    BREWER = "brewer"
    VIEWER = "viewer"


# Authorization rules live here as small predicates; routes and use cases ask these helpers
# instead of comparing roles inline, so changing who may do what is a one-file change.
_BREWING = frozenset({Role.ADMIN, Role.BREWER})


def can_manage_users(role: Role) -> bool:
    return role is Role.ADMIN


def can_write_batches(role: Role) -> bool:
    return role in _BREWING


def can_acknowledge_alerts(role: Role) -> bool:
    return role in _BREWING


def can_write_quality_profiles(role: Role) -> bool:
    return role in _BREWING


def can_record_lab_analyses(role: Role) -> bool:
    return role in _BREWING


def can_download_reports(role: Role) -> bool:
    return True
