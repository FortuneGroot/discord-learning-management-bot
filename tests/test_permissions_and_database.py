from __future__ import annotations

from sqlalchemy import func, select

from ffcu.models import Student
from ffcu.services.course import CourseService
from ffcu.services.permissions import StaffAccess, access_level, allowed, student_allowed


def test_permission_hierarchy() -> None:
    kwargs = {"admin_role_id": 10, "professor_role_id": 20, "mentor_role_id": 30}
    assert access_level([10], **kwargs) is StaffAccess.ADMIN
    assert access_level([20], **kwargs) is StaffAccess.PROFESSOR
    assert access_level([30], **kwargs) is StaffAccess.MENTOR
    assert access_level([999], **kwargs) is StaffAccess.STUDENT
    assert allowed(StaffAccess.ADMIN, StaffAccess.PROFESSOR)
    assert not allowed(StaffAccess.MENTOR, StaffAccess.ADMIN)
    assert access_level([], administrator_permission=True, **kwargs) is StaffAccess.ADMIN


def test_paid_student_role_gates_university_access() -> None:
    kwargs = {
        "student_role_id": 40,
        "graduate_role_id": 50,
        "admin_role_id": 10,
        "professor_role_id": 20,
        "mentor_role_id": 30,
    }
    assert student_allowed([40], **kwargs)
    assert student_allowed([50], **kwargs)
    assert student_allowed([20], **kwargs)
    assert student_allowed([], administrator_permission=True, **kwargs)
    assert not student_allowed([999], **kwargs)


def test_blank_student_role_keeps_local_development_available() -> None:
    assert student_allowed([], student_role_id=0)


def test_enrollment_uses_discord_id_and_updates_name(database) -> None:
    with database.session() as session:
        first = CourseService.enroll(session, 401, "Old Name")
        second = CourseService.enroll(session, 401, "New Name")
        assert first.id == second.id
        assert second.display_name == "New Name"
        assert session.scalar(select(func.count(Student.id))) == 1


def test_display_name_sanitization() -> None:
    assert CourseService.safe_display_name("\x00  Student\n") == "Student"
    assert len(CourseService.safe_display_name("x" * 500)) == 100
