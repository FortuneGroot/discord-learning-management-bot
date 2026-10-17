from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from ffcu.models import Assignment, CourseLevel, CourseSetting, Lesson, Question, ReferralLink


class ContentError(ValueError):
    pass


@dataclass(slots=True)
class LoadSummary:
    levels: int = 0
    lessons: int = 0
    questions: int = 0
    assignments: int = 0
    referrals: int = 0


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ContentError(f"Could not read {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContentError(f"{path.name} must contain a YAML mapping at the top level.")
    return data


def _validate_question(raw: dict[str, Any], source: str) -> tuple[list[str], int]:
    options = raw.get("options")
    if not isinstance(options, list) or len(options) != 4:
        raise ContentError(f"{source}: every question must have exactly four non-empty options.")
    normalized = ["Yes" if item is True else "No" if item is False else str(item).strip() for item in options]
    if not all(normalized):
        raise ContentError(f"{source}: every question must have exactly four non-empty options.")
    correct = raw.get("correct")
    if isinstance(correct, str) and correct.upper() in {"A", "B", "C", "D"}:
        correct_index = ord(correct.upper()) - ord("A")
    elif isinstance(correct, int) and 0 <= correct <= 3:
        correct_index = correct
    else:
        raise ContentError(f"{source}: correct must be A, B, C, or D.")
    return normalized, correct_index


def _upsert_questions(
    session: Session,
    questions: list[dict[str, Any]],
    *,
    question_type: str,
    id_prefix: str,
    lesson_id: int | None = None,
    level_id: int | None = None,
) -> int:
    loaded = 0
    seen: set[str] = set()
    for index, raw in enumerate(questions, start=1):
        if not isinstance(raw, dict):
            raise ContentError(f"{id_prefix} question {index} must be a mapping.")
        external_id = str(raw.get("id") or f"{id_prefix}-{index:03d}")
        if external_id in seen:
            raise ContentError(f"Duplicate question id {external_id} in {id_prefix}.")
        seen.add(external_id)
        options, correct_index = _validate_question(raw, external_id)
        prompt = str(raw.get("prompt", "")).strip()
        if not prompt:
            raise ContentError(f"{external_id}: prompt is required.")
        question = session.scalar(select(Question).where(Question.external_id == external_id))
        if question is None:
            question = Question(external_id=external_id, prompt=prompt, options=options, correct_index=correct_index)
            session.add(question)
        question.question_type = question_type
        question.lesson_id = lesson_id
        question.level_id = level_id
        question.prompt = prompt
        question.options = options
        question.correct_index = correct_index
        question.topic = str(raw.get("topic", "General"))[:120]
        question.explanation = str(raw.get("explanation", ""))
        question.active = bool(raw.get("active", True))
        loaded += 1
    return loaded


def load_content(session: Session, content_directory: Path, default_passing_score: int = 80) -> LoadSummary:
    course_path = content_directory / "university.yaml"
    questions_path = content_directory / "questions.yaml"
    course = _read_yaml(course_path)
    banks = _read_yaml(questions_path)
    summary = LoadSummary()

    levels_by_number: dict[int, CourseLevel] = {}
    for raw_level in course.get("levels", []):
        number = int(raw_level["number"])
        level = session.scalar(select(CourseLevel).where(CourseLevel.number == number))
        if level is None:
            level = CourseLevel(number=number, slug=str(raw_level["slug"]), title=str(raw_level["title"]), order_index=number)
            session.add(level)
        level.slug = str(raw_level["slug"])
        level.title = str(raw_level["title"])
        level.description = str(raw_level.get("description", ""))
        level.order_index = int(raw_level.get("order", number))
        level.passing_score = int(raw_level.get("passing_score", default_passing_score))
        level.exam_size = int(raw_level.get("exam_size", 10))
        level.published = bool(raw_level.get("published", True))
        session.flush()
        levels_by_number[number] = level
        summary.levels += 1

        lesson_rows = list(raw_level.get("lessons", []))
        lesson_orders = [int(item.get("order", index)) for index, item in enumerate(lesson_rows, start=1)]
        if len(lesson_orders) != len(set(lesson_orders)):
            raise ContentError(f"Level {number} contains duplicate lesson order values.")
        for lesson_index, raw_lesson in enumerate(lesson_rows, start=1):
            code = str(raw_lesson["code"])
            lesson = session.scalar(select(Lesson).where(Lesson.code == code))
            if lesson is None:
                lesson = Lesson(level_id=level.id, code=code, order_index=lesson_index, title=str(raw_lesson["title"]))
                session.add(lesson)
            lesson.level_id = level.id
            lesson.order_index = int(raw_lesson.get("order", lesson_index))
            lesson.title = str(raw_lesson["title"])
            lesson.description = str(raw_lesson.get("description", ""))
            lesson.video_url = str(raw_lesson.get("video_url", ""))
            lesson.video_provider = str(raw_lesson.get("video_provider", ""))
            lesson.video_duration_minutes = int(raw_lesson.get("video_duration_minutes", 0))
            lesson.professor = str(raw_lesson.get("professor", "Fortune & Finance Faculty"))
            lesson.objectives = list(raw_lesson.get("objectives", []))
            lesson.topics = list(raw_lesson.get("topics", []))
            lesson.supporting_notes = str(raw_lesson.get("supporting_notes", ""))
            lesson.resources = list(raw_lesson.get("resources", []))
            lesson.partner_key = raw_lesson.get("partner_key")
            lesson.prerequisite_code = raw_lesson.get("prerequisite")
            lesson.passing_score = int(raw_lesson.get("passing_score", default_passing_score))
            lesson.quiz_size = int(raw_lesson.get("quiz_size", 5))
            lesson.published = bool(raw_lesson.get("published", True))
            summary.lessons += 1

    session.flush()
    lesson_banks = banks.get("lesson_banks", {})
    for code, questions in lesson_banks.items():
        lesson = session.scalar(select(Lesson).where(Lesson.code == str(code)))
        if lesson is None:
            raise ContentError(f"Question bank refers to unknown lesson {code}.")
        summary.questions += _upsert_questions(
            session, list(questions), question_type="lesson", id_prefix=f"lesson-{code}", lesson_id=lesson.id
        )

    for number_text, exam in banks.get("level_exams", {}).items():
        number = int(number_text)
        level = levels_by_number.get(number) or session.scalar(select(CourseLevel).where(CourseLevel.number == number))
        if level is None:
            raise ContentError(f"Exam bank refers to unknown level {number}.")
        if isinstance(exam, dict):
            level.exam_size = int(exam.get("exam_size", level.exam_size))
            questions = list(exam.get("questions", []))
        else:
            questions = list(exam)
        summary.questions += _upsert_questions(
            session, questions, question_type="level", id_prefix=f"level-{number}-exam", level_id=level.id
        )

    final_exam = banks.get("final_exam", {})
    final_questions = list(final_exam.get("questions", [])) if isinstance(final_exam, dict) else list(final_exam)
    summary.questions += _upsert_questions(
        session, final_questions, question_type="final", id_prefix="final-exam"
    )
    if isinstance(final_exam, dict):
        for key, value in {
            "final_exam_size": int(final_exam.get("exam_size", 20)),
            "final_passing_score": int(final_exam.get("passing_score", default_passing_score)),
        }.items():
            setting = session.scalar(select(CourseSetting).where(CourseSetting.key == key))
            if setting is None:
                setting = CourseSetting(key=key, value=value)
                session.add(setting)
            setting.value = value

    for raw in course.get("assignments", []):
        external_id = str(raw["id"])
        assignment = session.scalar(select(Assignment).where(Assignment.external_id == external_id))
        level = levels_by_number.get(int(raw["level"]))
        if level is None:
            raise ContentError(f"Assignment {external_id} refers to an unknown level.")
        lesson_id = None
        if raw.get("lesson"):
            lesson = session.scalar(select(Lesson).where(Lesson.code == str(raw["lesson"])))
            if lesson is None:
                raise ContentError(f"Assignment {external_id} refers to unknown lesson {raw['lesson']}.")
            lesson_id = lesson.id
        if assignment is None:
            assignment = Assignment(external_id=external_id, level_id=level.id, title=str(raw["title"]), instructions=str(raw["instructions"]))
            session.add(assignment)
        assignment.level_id = level.id
        assignment.lesson_id = lesson_id
        assignment.title = str(raw["title"])
        assignment.instructions = str(raw["instructions"])
        assignment.required = bool(raw.get("required", False))
        assignment.enabled = bool(raw.get("enabled", False))
        summary.assignments += 1

    for raw in course.get("referral_partners", []):
        key = str(raw["key"])
        referral = session.scalar(select(ReferralLink).where(ReferralLink.partner_key == key))
        if referral is None:
            referral = ReferralLink(partner_key=key, display_name=str(raw["display_name"]))
            session.add(referral)
        referral.display_name = str(raw["display_name"])
        referral.enabled = bool(raw.get("enabled", False))
        referral.disclosure = str(raw.get("disclosure", referral.disclosure))
        summary.referrals += 1

    session.flush()
    for level in levels_by_number.values():
        if not level.published:
            continue
        active_lessons = [lesson for lesson in level.lessons if lesson.published]
        if not active_lessons:
            raise ContentError(f"Published level {level.number} has no published lessons.")
        for lesson in active_lessons:
            count = len([question for question in lesson.questions if question.active and question.question_type == "lesson"])
            if count < lesson.quiz_size:
                raise ContentError(
                    f"Published lesson {lesson.code} needs at least {lesson.quiz_size} active questions; found {count}."
                )
        exam_count = len(list(session.scalars(select(Question).where(
            Question.question_type == "level", Question.level_id == level.id, Question.active.is_(True)
        ))))
        if exam_count < level.exam_size:
            raise ContentError(f"Published level {level.number} exam needs {level.exam_size} questions; found {exam_count}.")
    final_size_setting = session.scalar(select(CourseSetting).where(CourseSetting.key == "final_exam_size"))
    final_size = int(final_size_setting.value) if final_size_setting else 20
    if len(final_questions) < final_size:
        raise ContentError(f"Final exam needs at least {final_size} questions; found {len(final_questions)}.")
    return summary
