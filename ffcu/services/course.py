from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, delete, func, select
from sqlalchemy.orm import Session

from ffcu.models import (
    Assignment,
    AssignmentSubmission,
    CourseLevel,
    Lesson,
    LessonCompletion,
    LevelCompletion,
    QuizAttempt,
    Student,
    utcnow,
)


@dataclass(slots=True)
class ProgressSummary:
    completed_lessons: int
    total_lessons: int
    completed_levels: int
    total_levels: int
    average_score: int
    overall_percent: int
    status: str
    current_level: str
    current_lesson: str


class CourseService:
    @staticmethod
    def safe_display_name(value: str) -> str:
        cleaned = re.sub(r"[\x00-\x1f\x7f]", "", value).strip()
        return (cleaned or "Student")[:100]

    @classmethod
    def enroll(cls, session: Session, discord_user_id: int, display_name: str) -> Student:
        student = session.scalar(select(Student).where(Student.discord_user_id == discord_user_id))
        if student is None:
            student = Student(discord_user_id=discord_user_id, display_name=cls.safe_display_name(display_name))
            session.add(student)
            session.flush()
        else:
            student.display_name = cls.safe_display_name(display_name)
            student.last_activity_at = utcnow()
        return student

    @staticmethod
    def published_levels(session: Session) -> list[CourseLevel]:
        return list(session.scalars(select(CourseLevel).where(CourseLevel.published.is_(True)).order_by(CourseLevel.order_index)))

    @staticmethod
    def published_lessons(session: Session, level_id: int | None = None) -> list[Lesson]:
        query = select(Lesson).join(CourseLevel).where(Lesson.published.is_(True), CourseLevel.published.is_(True))
        if level_id is not None:
            query = query.where(Lesson.level_id == level_id)
        return list(session.scalars(query.order_by(CourseLevel.order_index, Lesson.order_index)))

    @staticmethod
    def lesson_completed(session: Session, student_id: int, lesson_id: int) -> bool:
        return session.scalar(
            select(LessonCompletion.id).where(
                LessonCompletion.student_id == student_id, LessonCompletion.lesson_id == lesson_id
            )
        ) is not None

    @staticmethod
    def level_completed(session: Session, student_id: int, level_id: int) -> bool:
        return session.scalar(
            select(LevelCompletion.id).where(LevelCompletion.student_id == student_id, LevelCompletion.level_id == level_id)
        ) is not None

    @classmethod
    def lesson_unlocked(cls, session: Session, student: Student, lesson: Lesson) -> bool:
        if student.status in {"locked", "suspended"} or not lesson.published or not lesson.level.published:
            return False
        previous_levels = list(session.scalars(
            select(CourseLevel).where(
                CourseLevel.published.is_(True), CourseLevel.order_index < lesson.level.order_index
            ).order_by(CourseLevel.order_index)
        ))
        if any(not cls.level_completed(session, student.id, level.id) for level in previous_levels):
            return False
        if lesson.prerequisite_code:
            prerequisite = session.scalar(select(Lesson).where(Lesson.code == lesson.prerequisite_code))
            return prerequisite is not None and cls.lesson_completed(session, student.id, prerequisite.id)
        prior_lessons = list(session.scalars(
            select(Lesson).where(
                Lesson.level_id == lesson.level_id,
                Lesson.published.is_(True),
                Lesson.order_index < lesson.order_index,
            )
        ))
        return all(cls.lesson_completed(session, student.id, item.id) for item in prior_lessons)

    @classmethod
    def current_lesson(cls, session: Session, student: Student) -> Lesson | None:
        for lesson in cls.published_lessons(session):
            if not cls.lesson_completed(session, student.id, lesson.id) and cls.lesson_unlocked(session, student, lesson):
                return lesson
        return None

    @classmethod
    def level_exam_eligible(cls, session: Session, student: Student, level: CourseLevel) -> bool:
        if student.status in {"locked", "suspended"} or cls.level_completed(session, student.id, level.id):
            return False
        lessons = cls.published_lessons(session, level.id)
        if not lessons or any(not cls.lesson_completed(session, student.id, lesson.id) for lesson in lessons):
            return False
        required = list(session.scalars(select(Assignment).where(
            Assignment.level_id == level.id, Assignment.enabled.is_(True), Assignment.required.is_(True)
        )))
        for assignment in required:
            approved = session.scalar(select(AssignmentSubmission.id).where(
                AssignmentSubmission.assignment_id == assignment.id,
                AssignmentSubmission.student_id == student.id,
                AssignmentSubmission.status == "approved",
            ))
            if approved is None:
                return False
        return True

    @classmethod
    def final_exam_eligible(cls, session: Session, student: Student) -> bool:
        levels = cls.published_levels(session)
        return bool(levels) and all(cls.level_completed(session, student.id, level.id) for level in levels)

    @classmethod
    def can_graduate(cls, session: Session, student: Student) -> bool:
        if not cls.final_exam_eligible(session, student):
            return False
        return session.scalar(select(QuizAttempt.id).where(
            QuizAttempt.student_id == student.id,
            QuizAttempt.attempt_type == "final",
            QuizAttempt.passed.is_(True),
        ).limit(1)) is not None

    @classmethod
    def progress(cls, session: Session, student: Student) -> ProgressSummary:
        lessons = cls.published_lessons(session)
        levels = cls.published_levels(session)
        completed_lesson_ids = set(session.scalars(select(LessonCompletion.lesson_id).where(LessonCompletion.student_id == student.id)))
        completed_level_ids = set(session.scalars(select(LevelCompletion.level_id).where(LevelCompletion.student_id == student.id)))
        scores = list(session.scalars(select(QuizAttempt.score).where(
            QuizAttempt.student_id == student.id, QuizAttempt.completed_at.is_not(None)
        )))
        current = cls.current_lesson(session, student)
        if current:
            current_level = current.level.title
            current_lesson = f"{current.code} {current.title}"
        else:
            pending_exam = next((level for level in levels if cls.level_exam_eligible(session, student, level)), None)
            if pending_exam:
                current_level, current_lesson = pending_exam.title, "Level final examination"
            elif cls.final_exam_eligible(session, student) and student.status != "graduate":
                current_level, current_lesson = "Final Examination", "Comprehensive final examination"
            else:
                current_level, current_lesson = "Complete", "No lesson currently available"
        completed_lessons = len(completed_lesson_ids.intersection({item.id for item in lessons}))
        completed_levels = len(completed_level_ids.intersection({item.id for item in levels}))
        total_items = len(lessons) + len(levels) + 1
        completed_items = completed_lessons + completed_levels + (1 if student.status == "graduate" else 0)
        return ProgressSummary(
            completed_lessons=completed_lessons,
            total_lessons=len(lessons),
            completed_levels=completed_levels,
            total_levels=len(levels),
            average_score=round(sum(score for score in scores if score is not None) / len(scores)) if scores else 0,
            overall_percent=round(100 * completed_items / total_items) if total_items else 0,
            status=student.status.upper(),
            current_level=current_level,
            current_lesson=current_lesson,
        )

    @staticmethod
    def stalled_count(session: Session, days: int = 7) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return int(session.scalar(select(func.count(Student.id)).where(
            Student.status == "active", Student.last_activity_at < cutoff
        )) or 0)

    @staticmethod
    def reset_progress(session: Session, student: Student) -> None:
        if student.certificate is not None:
            raise ValueError("A certificate has already been issued; preserve the audit record and do not reset this graduate.")
        session.execute(delete(QuizAttempt).where(QuizAttempt.student_id == student.id))
        session.execute(delete(LessonCompletion).where(LessonCompletion.student_id == student.id))
        session.execute(delete(LevelCompletion).where(LevelCompletion.student_id == student.id))
        session.execute(delete(AssignmentSubmission).where(AssignmentSubmission.student_id == student.id))
        student.status = "active"
        student.last_activity_at = utcnow()

    @staticmethod
    def progress_bar(percent: int, width: int = 10) -> str:
        filled = max(0, min(width, round(width * percent / 100)))
        return "█" * filled + "░" * (width - filled)
