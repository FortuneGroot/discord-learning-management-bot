from __future__ import annotations

import random

from sqlalchemy import select

from ffcu.models import CourseLevel, CourseSetting, Lesson, LessonCompletion, LevelCompletion, Question, QuizAttempt
from ffcu.services.course import CourseService
from ffcu.services.quiz import QuizService


def _correct_answers(session, attempt_id: int) -> dict[int, int]:
    attempt = session.get(QuizAttempt, attempt_id)
    result = {}
    for question_id in attempt.questions_used["question_ids"]:
        question = session.get(Question, question_id)
        result[question_id] = attempt.questions_used["option_orders"][str(question_id)].index(question.correct_index)
    return result


def test_lesson_locking_and_unlocking(database) -> None:
    with database.session() as session:
        student = CourseService.enroll(session, 201, "Progress")
        first = session.scalar(select(Lesson).where(Lesson.code == "0.1"))
        second = session.scalar(select(Lesson).where(Lesson.code == "0.2"))
        assert CourseService.lesson_unlocked(session, student, first)
        assert not CourseService.lesson_unlocked(session, student, second)
        session.add(LessonCompletion(student_id=student.id, lesson_id=first.id, best_score=80))
        session.flush()
        assert CourseService.lesson_unlocked(session, student, second)


def test_level_unlock_requires_previous_level_exam(database) -> None:
    with database.session() as session:
        student = CourseService.enroll(session, 202, "Levels")
        level_zero = session.scalar(select(CourseLevel).where(CourseLevel.number == 0))
        level_one_first = session.scalar(select(Lesson).where(Lesson.code == "1.1"))
        for lesson in CourseService.published_lessons(session, level_zero.id):
            session.add(LessonCompletion(student_id=student.id, lesson_id=lesson.id, best_score=100))
        session.flush()
        assert CourseService.level_exam_eligible(session, student, level_zero)
        assert not CourseService.lesson_unlocked(session, student, level_one_first)
        session.add(LevelCompletion(student_id=student.id, level_id=level_zero.id, best_score=100))
        session.flush()
        assert CourseService.lesson_unlocked(session, student, level_one_first)


def test_final_graduation_validation(database) -> None:
    service = QuizService(rng=random.Random(12))
    with database.session() as session:
        student = CourseService.enroll(session, 203, "Graduate")
        for lesson in CourseService.published_lessons(session):
            session.add(LessonCompletion(student_id=student.id, lesson_id=lesson.id, best_score=100))
        for level in CourseService.published_levels(session):
            session.add(LevelCompletion(student_id=student.id, level_id=level.id, best_score=100))
        session.flush()
        assert CourseService.final_exam_eligible(session, student)
        quiz = service.start(session, student, "final")
        configured_size = session.scalar(select(CourseSetting.value).where(CourseSetting.key == "final_exam_size"))
        assert len(quiz.questions) == int(configured_size)
        outcome = service.submit(session, quiz.attempt_id, _correct_answers(session, quiz.attempt_id))
        assert outcome.score == 100
        assert outcome.graduated is True
        assert student.status == "graduate"
        assert CourseService.can_graduate(session, student)


def test_progress_counts_only_published_curriculum(database) -> None:
    with database.session() as session:
        student = CourseService.enroll(session, 204, "Dashboard")
        progress = CourseService.progress(session, student)
        assert progress.total_levels == 2
        assert progress.total_lessons == 6
        assert progress.current_lesson.startswith("0.1")
