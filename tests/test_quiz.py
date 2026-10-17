from __future__ import annotations

import random

from sqlalchemy import select

from ffcu.models import Lesson, Question, QuizAttempt
from ffcu.services.course import CourseService
from ffcu.services.quiz import QuizError, QuizService


def displayed_correct_answers(session, attempt_id: int) -> dict[int, int]:
    attempt = session.get(QuizAttempt, attempt_id)
    answers: dict[int, int] = {}
    for question_id in attempt.questions_used["question_ids"]:
        question = session.get(Question, question_id)
        order = attempt.questions_used["option_orders"][str(question_id)]
        answers[question_id] = order.index(question.correct_index)
    return answers


def test_80_passes_and_79_fails_boundary() -> None:
    assert QuizService.score(80, 100) == 80
    assert QuizService.score(79, 100) == 79
    assert QuizService.score(80, 100) >= 80
    assert QuizService.score(79, 100) < 80


def test_quiz_scoring_pass_records_completion(database) -> None:
    service = QuizService(rng=random.Random(4))
    with database.session() as session:
        student = CourseService.enroll(session, 101, "Student One")
        lesson = session.scalar(select(Lesson).where(Lesson.code == "0.1"))
        quiz = service.start(session, student, "lesson", lesson.id)
        answers = displayed_correct_answers(session, quiz.attempt_id)
        first = next(iter(answers))
        answers[first] = (answers[first] + 1) % 4
        outcome = service.submit(session, quiz.attempt_id, answers)
        assert outcome.score == 80
        assert outcome.passed is True
        assert CourseService.lesson_completed(session, student.id, lesson.id)


def test_failed_quiz_shows_topics_but_not_answer_key(database) -> None:
    service = QuizService(rng=random.Random(9))
    with database.session() as session:
        student = CourseService.enroll(session, 102, "Student Two")
        lesson = session.scalar(select(Lesson).where(Lesson.code == "0.1"))
        quiz = service.start(session, student, "lesson", lesson.id)
        answers = {question.id: 0 for question in quiz.questions}
        # Force each selection to a displayed option that is not correct.
        correct = displayed_correct_answers(session, quiz.attempt_id)
        answers = {question_id: (index + 1) % 4 for question_id, index in correct.items()}
        outcome = service.submit(session, quiz.attempt_id, answers)
        assert outcome.passed is False
        assert outcome.review_topics
        assert not hasattr(outcome, "correct_answers")


def test_question_and_answer_order_randomize(database) -> None:
    with database.session() as session:
        lesson = session.scalar(select(Lesson).where(Lesson.code == "0.1"))
        first_student = CourseService.enroll(session, 103, "First")
        second_student = CourseService.enroll(session, 104, "Second")
        first = QuizService(rng=random.Random(1)).start(session, first_student, "lesson", lesson.id)
        second = QuizService(rng=random.Random(2)).start(session, second_student, "lesson", lesson.id)
        first_signature = [(item.id, item.options) for item in first.questions]
        second_signature = [(item.id, item.options) for item in second.questions]
        assert first_signature != second_signature
        assert len(first.questions) == 5
        assert len({item.id for item in first.questions}) == 5


def test_duplicate_submission_is_rejected(database) -> None:
    service = QuizService(rng=random.Random(7))
    with database.session() as session:
        student = CourseService.enroll(session, 105, "Duplicate")
        lesson = session.scalar(select(Lesson).where(Lesson.code == "0.1"))
        quiz = service.start(session, student, "lesson", lesson.id)
        answers = displayed_correct_answers(session, quiz.attempt_id)
        service.submit(session, quiz.attempt_id, answers)
        try:
            service.submit(session, quiz.attempt_id, answers)
        except QuizError as exc:
            assert "already submitted" in str(exc)
        else:
            raise AssertionError("Duplicate submission should have failed")
