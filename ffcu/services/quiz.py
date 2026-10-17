from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ffcu.models import (
    CourseLevel,
    CourseSetting,
    Lesson,
    LessonCompletion,
    LevelCompletion,
    Question,
    QuestionResult,
    QuizAttempt,
    Student,
    utcnow,
)
from ffcu.services.course import CourseService


class QuizError(ValueError):
    pass


@dataclass(slots=True)
class PresentedQuestion:
    id: int
    prompt: str
    options: list[str]
    topic: str


@dataclass(slots=True)
class QuizSession:
    attempt_id: int
    attempt_number: int
    attempt_type: str
    title: str
    passing_score: int
    questions: list[PresentedQuestion]
    target_id: int | None


@dataclass(slots=True)
class QuizOutcome:
    attempt_id: int
    score: int
    correct_count: int
    total_questions: int
    passed: bool
    passing_score: int
    review_topics: list[str]
    graduated: bool = False


class QuizService:
    def __init__(self, cooldown_minutes: int = 0, rng: random.Random | None = None):
        if cooldown_minutes not in {0, 5, 15, 30, 60}:
            raise ValueError("Cooldown must be 0, 5, 15, 30, or 60 minutes.")
        self.cooldown_minutes = cooldown_minutes
        self.rng = rng or random.SystemRandom()

    @staticmethod
    def score(correct: int, total: int) -> int:
        if total <= 0:
            raise QuizError("A quiz must contain at least one question.")
        return round(correct * 100 / total)

    def _scope(self, session: Session, attempt_type: str, target_id: int | None):
        if attempt_type == "lesson":
            lesson = session.get(Lesson, target_id)
            if lesson is None:
                raise QuizError("Lesson not found.")
            return lesson, lesson.title, lesson.passing_score, lesson.quiz_size, Lesson.id == lesson.id
        if attempt_type == "level":
            level = session.get(CourseLevel, target_id)
            if level is None:
                raise QuizError("Level not found.")
            return level, f"{level.title} Final Exam", level.passing_score, level.exam_size, CourseLevel.id == level.id
        if attempt_type == "final":
            size = session.scalar(select(CourseSetting.value).where(CourseSetting.key == "final_exam_size"))
            passing = session.scalar(select(CourseSetting.value).where(CourseSetting.key == "final_passing_score"))
            return None, "Comprehensive Final Examination", int(passing or 80), int(size or 20), None
        raise QuizError("Unknown quiz type.")

    def _last_attempt_query(self, student_id: int, attempt_type: str, target_id: int | None):
        query = select(QuizAttempt).where(
            QuizAttempt.student_id == student_id,
            QuizAttempt.attempt_type == attempt_type,
            QuizAttempt.completed_at.is_not(None),
        )
        if attempt_type == "lesson":
            query = query.where(QuizAttempt.lesson_id == target_id)
        elif attempt_type == "level":
            query = query.where(QuizAttempt.level_id == target_id)
        return query.order_by(QuizAttempt.completed_at.desc()).limit(1)

    def start(
        self,
        session: Session,
        student: Student,
        attempt_type: str,
        target_id: int | None = None,
        *,
        enforce_eligibility: bool = True,
    ) -> QuizSession:
        target, title, passing_score, requested_size, _ = self._scope(session, attempt_type, target_id)
        if student.status in {"locked", "suspended"}:
            raise QuizError("Your university access is locked. Please contact an administrator.")
        if enforce_eligibility:
            if attempt_type == "lesson" and not CourseService.lesson_unlocked(session, student, target):
                raise QuizError("This lesson is still locked.")
            if attempt_type == "level" and not CourseService.level_exam_eligible(session, student, target):
                raise QuizError("Complete every required lesson and assignment in this level first.")
            if attempt_type == "final" and not CourseService.final_exam_eligible(session, student):
                raise QuizError("Complete all published levels before taking the final examination.")

        last = session.scalar(self._last_attempt_query(student.id, attempt_type, target_id))
        if last and self.cooldown_minutes:
            completed_at = last.completed_at
            if completed_at and completed_at.tzinfo is None:
                completed_at = completed_at.replace(tzinfo=timezone.utc)
            eligible_at = completed_at + timedelta(minutes=self.cooldown_minutes) if completed_at else utcnow()
            if datetime.now(timezone.utc) < eligible_at:
                wait_seconds = int((eligible_at - datetime.now(timezone.utc)).total_seconds())
                raise QuizError(f"Retake cooldown active. Try again in about {max(1, (wait_seconds + 59) // 60)} minute(s).")

        query = select(Question).where(Question.question_type == attempt_type, Question.active.is_(True))
        if attempt_type == "lesson":
            query = query.where(Question.lesson_id == target_id)
        elif attempt_type == "level":
            query = query.where(Question.level_id == target_id)
        pool = list(session.scalars(query))
        if not pool:
            raise QuizError("This quiz has no approved questions yet. Please notify a professor.")
        count = min(requested_size, len(pool))
        selected = self.rng.sample(pool, count)
        presented: list[PresentedQuestion] = []
        option_orders: dict[str, list[int]] = {}
        for question in selected:
            order = list(range(4))
            self.rng.shuffle(order)
            option_orders[str(question.id)] = order
            presented.append(PresentedQuestion(
                id=question.id,
                prompt=question.prompt,
                options=[question.options[index] for index in order],
                topic=question.topic,
            ))
        prior_count = int(session.scalar(select(func.count(QuizAttempt.id)).where(
            QuizAttempt.student_id == student.id,
            QuizAttempt.attempt_type == attempt_type,
            QuizAttempt.lesson_id == (target_id if attempt_type == "lesson" else None),
            QuizAttempt.level_id == (target_id if attempt_type == "level" else None),
        )) or 0)
        attempt = QuizAttempt(
            student_id=student.id,
            attempt_type=attempt_type,
            lesson_id=target_id if attempt_type == "lesson" else None,
            level_id=target_id if attempt_type == "level" else None,
            attempt_number=prior_count + 1,
            total_questions=count,
            questions_used={"question_ids": [item.id for item in selected], "option_orders": option_orders},
        )
        session.add(attempt)
        session.flush()
        return QuizSession(attempt.id, attempt.attempt_number, attempt_type, title, passing_score, presented, target_id)

    def submit(self, session: Session, attempt_id: int, answers: dict[int, int]) -> QuizOutcome:
        attempt = session.get(QuizAttempt, attempt_id)
        if attempt is None:
            raise QuizError("Quiz attempt not found.")
        if attempt.completed_at is not None:
            raise QuizError("This quiz was already submitted.")
        question_ids = [int(value) for value in attempt.questions_used.get("question_ids", [])]
        if set(answers) != set(question_ids):
            raise QuizError("Every question must be answered exactly once.")
        option_orders = attempt.questions_used.get("option_orders", {})
        questions = {q.id: q for q in session.scalars(select(Question).where(Question.id.in_(question_ids)))}
        if len(questions) != len(question_ids):
            raise QuizError("One or more quiz questions are unavailable.")
        correct_count = 0
        missed_topics: list[str] = []
        for question_id in question_ids:
            selected_index = answers[question_id]
            if selected_index not in {0, 1, 2, 3}:
                raise QuizError("Answer selection must be A, B, C, or D.")
            question = questions[question_id]
            order = [int(value) for value in option_orders[str(question_id)]]
            original_index = order[selected_index]
            correct = original_index == question.correct_index
            correct_count += int(correct)
            if not correct:
                missed_topics.append(question.topic)
            session.add(QuestionResult(
                attempt_id=attempt.id,
                question_id=question_id,
                displayed_options=[question.options[index] for index in order],
                selected_index=selected_index,
                correct=correct,
            ))
        passing_score = 80
        if attempt.attempt_type == "lesson":
            passing_score = session.get(Lesson, attempt.lesson_id).passing_score
        elif attempt.attempt_type == "level":
            passing_score = session.get(CourseLevel, attempt.level_id).passing_score
        elif attempt.attempt_type == "final":
            configured = session.scalar(select(CourseSetting.value).where(CourseSetting.key == "final_passing_score"))
            passing_score = int(configured or 80)
        score = self.score(correct_count, len(question_ids))
        passed = score >= passing_score
        attempt.score = score
        attempt.correct_count = correct_count
        attempt.passed = passed
        attempt.completed_at = utcnow()
        student = session.get(Student, attempt.student_id)
        student.last_activity_at = utcnow()
        graduated = False
        if passed and attempt.attempt_type == "lesson":
            completion = session.scalar(select(LessonCompletion).where(
                LessonCompletion.student_id == student.id, LessonCompletion.lesson_id == attempt.lesson_id
            ))
            if completion is None:
                session.add(LessonCompletion(
                    student_id=student.id, lesson_id=attempt.lesson_id, attempt_id=attempt.id, best_score=score
                ))
            elif score > completion.best_score:
                completion.best_score, completion.attempt_id = score, attempt.id
        elif passed and attempt.attempt_type == "level":
            completion = session.scalar(select(LevelCompletion).where(
                LevelCompletion.student_id == student.id, LevelCompletion.level_id == attempt.level_id
            ))
            if completion is None:
                session.add(LevelCompletion(
                    student_id=student.id, level_id=attempt.level_id, attempt_id=attempt.id, best_score=score
                ))
            elif score > completion.best_score:
                completion.best_score, completion.attempt_id = score, attempt.id
        elif passed and attempt.attempt_type == "final":
            session.flush()
            if CourseService.can_graduate(session, student):
                student.status = "graduate"
                graduated = True
        review_topics = [topic for topic, _count in Counter(missed_topics).most_common(5)]
        return QuizOutcome(attempt.id, score, correct_count, len(question_ids), passed, passing_score, review_topics, graduated)
