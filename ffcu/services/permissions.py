from __future__ import annotations

from enum import IntEnum
from typing import Iterable


class StaffAccess(IntEnum):
    STUDENT = 0
    MENTOR = 1
    PROFESSOR = 2
    ADMIN = 3


def access_level(
    role_ids: Iterable[int],
    *,
    admin_role_id: int,
    professor_role_id: int,
    mentor_role_id: int,
    administrator_permission: bool = False,
) -> StaffAccess:
    roles = set(role_ids)
    if administrator_permission or (admin_role_id and admin_role_id in roles):
        return StaffAccess.ADMIN
    if professor_role_id and professor_role_id in roles:
        return StaffAccess.PROFESSOR
    if mentor_role_id and mentor_role_id in roles:
        return StaffAccess.MENTOR
    return StaffAccess.STUDENT


def allowed(actual: StaffAccess, required: StaffAccess) -> bool:
    return actual >= required


def student_allowed(
    role_ids: Iterable[int],
    *,
    student_role_id: int,
    graduate_role_id: int = 0,
    admin_role_id: int = 0,
    professor_role_id: int = 0,
    mentor_role_id: int = 0,
    administrator_permission: bool = False,
) -> bool:
    """Return whether a Discord member may enter the paid University experience.

    A blank student role keeps local development usable. In production, configuring
    STUDENT_ROLE_ID makes the externally managed paid-member role mandatory.
    """

    if administrator_permission:
        return True
    roles = set(role_ids)
    privileged = {role for role in (admin_role_id, professor_role_id, mentor_role_id) if role}
    if roles & privileged:
        return True
    if graduate_role_id and graduate_role_id in roles:
        return True
    if not student_role_id:
        return True
    return student_role_id in roles
