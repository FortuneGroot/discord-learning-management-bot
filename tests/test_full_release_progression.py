from __future__ import annotations

import random
from pathlib import Path

import yaml

from ffcu.database import Database
from ffcu.models import LessonCompletion, LevelCompletion, Question, QuizAttempt
from ffcu.services.certificate import CertificateService
from ffcu.services.content_loader import load_content
from ffcu.services.course import CourseService
from ffcu.services.quiz import QuizService


ROOT = Path(__file__).resolve().parents[1]


def correct_answers(session, attempt_id: int) -> dict[int, int]:
    attempt = session.get(QuizAttempt, attempt_id)
    answers: dict[int, int] = {}
    for question_id in attempt.questions_used["question_ids"]:
        question = session.get(Question, question_id)
        order = attempt.questions_used["option_orders"][str(question_id)]
        answers[question_id] = order.index(question.correct_index)
    return answers


def test_every_published_lesson_progresses_to_final_and_certificate(tmp_path) -> None:
    content = tmp_path / "content"
    content.mkdir()
    course = yaml.safe_load((ROOT / "content" / "university.yaml").read_text(encoding="utf-8"))
    for level in course["levels"]:
        level["published"] = True
        level["exam_size"] = 10
        for lesson in level["lessons"]:
            lesson["published"] = True
    (content / "university.yaml").write_text(
        yaml.safe_dump(course, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    (content / "questions.yaml").write_text(
        (ROOT / "content" / "questions.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )

    database = Database("sqlite:///:memory:")
    database.create_all()
    with database.session() as session:
        summary = load_content(session, content)
        assert summary.levels == 2
        assert summary.lessons == 6
        assert summary.questions == 84
        student = CourseService.enroll(session, 125001, "Full Release Graduate")
        levels = CourseService.published_levels(session)
        assert len(levels) == 2
        assert len(CourseService.published_lessons(session)) == 6

        for level in levels:
            lessons = CourseService.published_lessons(session, level.id)
            for lesson in lessons:
                assert CourseService.lesson_unlocked(session, student, lesson)
                session.add(LessonCompletion(student_id=student.id, lesson_id=lesson.id, best_score=100))
                session.flush()
            assert CourseService.level_exam_eligible(session, student, level)
            session.add(LevelCompletion(student_id=student.id, level_id=level.id, best_score=100))
            session.flush()

        progress = CourseService.progress(session, student)
        assert progress.total_levels == 2
        assert progress.total_lessons == 6
        assert CourseService.final_exam_eligible(session, student)
        quiz_service = QuizService(rng=random.Random(125))
        final_quiz = quiz_service.start(session, student, "final")
        assert len(final_quiz.questions) == 20
        outcome = quiz_service.submit(
            session,
            final_quiz.attempt_id,
            correct_answers(session, final_quiz.attempt_id),
        )
        assert outcome.score == 100
        assert outcome.graduated
        certificate = CertificateService(tmp_path / "certificates").issue(session, student)
        assert Path(certificate.file_path).is_file()
        assert Path(certificate.file_path).stat().st_size > 10_000
    database.dispose()
