from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Student(Base, TimestampMixin):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    certificate_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    lesson_completions: Mapped[list[LessonCompletion]] = relationship(back_populates="student", cascade="all, delete-orphan")
    level_completions: Mapped[list[LevelCompletion]] = relationship(back_populates="student", cascade="all, delete-orphan")
    attempts: Mapped[list[QuizAttempt]] = relationship(back_populates="student", cascade="all, delete-orphan")
    certificate: Mapped[Certificate | None] = relationship(back_populates="student", uselist=False)


class CourseLevel(Base, TimestampMixin):
    __tablename__ = "course_levels"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    order_index: Mapped[int] = mapped_column(Integer, index=True)
    passing_score: Mapped[int] = mapped_column(Integer, default=80)
    exam_size: Mapped[int] = mapped_column(Integer, default=10)
    published: Mapped[bool] = mapped_column(Boolean, default=True)

    lessons: Mapped[list[Lesson]] = relationship(back_populates="level", cascade="all, delete-orphan", order_by="Lesson.order_index")


class Lesson(Base, TimestampMixin):
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(primary_key=True)
    level_id: Mapped[int] = mapped_column(ForeignKey("course_levels.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    video_url: Mapped[str] = mapped_column(String(500), default="")
    video_provider: Mapped[str] = mapped_column(String(50), default="")
    video_duration_minutes: Mapped[int] = mapped_column(Integer, default=0)
    professor: Mapped[str] = mapped_column(String(100), default="Fortune & Finance Faculty")
    objectives: Mapped[list[str]] = mapped_column(JSON, default=list)
    topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    supporting_notes: Mapped[str] = mapped_column(Text, default="")
    resources: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    partner_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    prerequisite_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    passing_score: Mapped[int] = mapped_column(Integer, default=80)
    quiz_size: Mapped[int] = mapped_column(Integer, default=5)
    published: Mapped[bool] = mapped_column(Boolean, default=True)

    level: Mapped[CourseLevel] = relationship(back_populates="lessons")
    questions: Mapped[list[Question]] = relationship(back_populates="lesson", cascade="all, delete-orphan")

class Question(Base, TimestampMixin):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    lesson_id: Mapped[int | None] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), nullable=True, index=True)
    level_id: Mapped[int | None] = mapped_column(ForeignKey("course_levels.id", ondelete="CASCADE"), nullable=True, index=True)
    question_type: Mapped[str] = mapped_column(String(20), default="lesson", index=True)
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(JSON)
    correct_index: Mapped[int] = mapped_column(Integer)
    topic: Mapped[str] = mapped_column(String(120), default="General")
    explanation: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    lesson: Mapped[Lesson | None] = relationship(back_populates="questions")

    __table_args__ = (
        Index("ix_questions_scope", "question_type", "lesson_id", "level_id", "active"),
    )


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    attempt_type: Mapped[str] = mapped_column(String(20), index=True)
    lesson_id: Mapped[int | None] = mapped_column(ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True, index=True)
    level_id: Mapped[int | None] = mapped_column(ForeignKey("course_levels.id", ondelete="SET NULL"), nullable=True, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    questions_used: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correct_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_questions: Mapped[int] = mapped_column(Integer)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    student: Mapped[Student] = relationship(back_populates="attempts")
    results: Mapped[list[QuestionResult]] = relationship(back_populates="attempt", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_attempt_scope", "student_id", "attempt_type", "lesson_id", "level_id"),)


class QuestionResult(Base):
    __tablename__ = "question_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("quiz_attempts.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="RESTRICT"), index=True)
    displayed_options: Mapped[list[str]] = mapped_column(JSON)
    selected_index: Mapped[int] = mapped_column(Integer)
    correct: Mapped[bool] = mapped_column(Boolean)

    attempt: Mapped[QuizAttempt] = relationship(back_populates="results")

    __table_args__ = (UniqueConstraint("attempt_id", "question_id", name="uq_attempt_question"),)


class LessonCompletion(Base):
    __tablename__ = "lesson_completions"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    attempt_id: Mapped[int | None] = mapped_column(ForeignKey("quiz_attempts.id", ondelete="SET NULL"), nullable=True)
    best_score: Mapped[int] = mapped_column(Integer)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    override: Mapped[bool] = mapped_column(Boolean, default=False)

    student: Mapped[Student] = relationship(back_populates="lesson_completions")
    lesson: Mapped[Lesson] = relationship()

    __table_args__ = (UniqueConstraint("student_id", "lesson_id", name="uq_student_lesson_completion"),)


class LevelCompletion(Base):
    __tablename__ = "level_completions"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    level_id: Mapped[int] = mapped_column(ForeignKey("course_levels.id", ondelete="CASCADE"), index=True)
    attempt_id: Mapped[int | None] = mapped_column(ForeignKey("quiz_attempts.id", ondelete="SET NULL"), nullable=True)
    best_score: Mapped[int] = mapped_column(Integer)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    override: Mapped[bool] = mapped_column(Boolean, default=False)

    student: Mapped[Student] = relationship(back_populates="level_completions")
    level: Mapped[CourseLevel] = relationship()

    __table_args__ = (UniqueConstraint("student_id", "level_id", name="uq_student_level_completion"),)


class Assignment(Base, TimestampMixin):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(80), unique=True)
    level_id: Mapped[int] = mapped_column(ForeignKey("course_levels.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int | None] = mapped_column(ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(180))
    instructions: Mapped[str] = mapped_column(Text)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class AssignmentSubmission(Base, TimestampMixin):
    __tablename__ = "assignment_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    submission_text: Mapped[str] = mapped_column(Text, default="")
    attachment_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(30), default="submitted", index=True)
    feedback: Mapped[str] = mapped_column(Text, default="")
    reviewed_by_discord_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("assignment_id", "student_id", name="uq_assignment_student"),)


class Certificate(Base):
    __tablename__ = "certificates"

    id: Mapped[int] = mapped_column(primary_key=True)
    certificate_id: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    verification_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"), unique=True)
    certificate_name: Mapped[str] = mapped_column(String(120))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    file_path: Mapped[str] = mapped_column(String(500))

    student: Mapped[Student] = relationship(back_populates="certificate")


class ReferralLink(Base, TimestampMixin):
    __tablename__ = "referral_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    partner_key: Mapped[str] = mapped_column(String(40), unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    url: Mapped[str] = mapped_column(String(500), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    disclosure: Mapped[str] = mapped_column(Text, default="Fortune & Finance may receive compensation or benefits if you register through this partner/referral link.")


class CourseSetting(Base, TimestampMixin):
    __tablename__ = "course_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    value: Mapped[Any] = mapped_column(JSON)


class AdminOverride(Base):
    __tablename__ = "admin_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_discord_id: Mapped[int] = mapped_column(BigInteger, index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    target_type: Mapped[str] = mapped_column(String(30))
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_discord_id: Mapped[int] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    student_discord_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
