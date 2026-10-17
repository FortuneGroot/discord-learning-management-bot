from __future__ import annotations

from sqlalchemy import func, select

from ffcu.models import Certificate
from ffcu.services.certificate import CertificateService
from ffcu.services.course import CourseService


def test_certificate_id_is_unique_and_duplicate_issuance_is_prevented(database, tmp_path) -> None:
    service = CertificateService(tmp_path / "certificates")
    with database.session() as session:
        student = CourseService.enroll(session, 301, "Alex Graduate")
        student.status = "graduate"
        first = service.issue(session, student)
        second = service.issue(session, student)
        assert first.certificate_id == second.certificate_id
        assert first.certificate_id.startswith("FFCU-")
        assert first.certificate_id.endswith("000001")
        assert (tmp_path / "certificates" / f"{first.certificate_id}.pdf").exists()
        assert session.scalar(select(func.count(Certificate.id))) == 1


def test_two_graduates_receive_sequential_ids(database, tmp_path) -> None:
    service = CertificateService(tmp_path)
    with database.session() as session:
        first_student = CourseService.enroll(session, 302, "First Graduate")
        second_student = CourseService.enroll(session, 303, "Second Graduate")
        first_student.status = second_student.status = "graduate"
        first = service.issue(session, first_student)
        second = service.issue(session, second_student)
        assert first.certificate_id[-6:] == "000001"
        assert second.certificate_id[-6:] == "000002"
        assert first.verification_code != second.verification_code
