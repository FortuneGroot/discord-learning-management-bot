from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import func, select

from ffcu.models import CourseLevel, Lesson, Question


def test_sample_course_hierarchy_is_seeded(database) -> None:
    banks = yaml.safe_load((Path(__file__).resolve().parents[1] / "content" / "questions.yaml").read_text(encoding="utf-8"))
    expected_questions = sum(len(items) for items in banks["lesson_banks"].values())
    expected_questions += sum(len(exam["questions"]) for exam in banks["level_exams"].values())
    expected_questions += len(banks["final_exam"]["questions"])
    with database.session() as session:
        assert session.scalar(select(func.count(CourseLevel.id))) == 2
        assert session.scalar(select(func.count(Lesson.id))) == 6
        assert session.scalar(select(func.count(Question.id))) == expected_questions
        security = session.scalar(select(CourseLevel).where(CourseLevel.number == 1))
        assert security.title == "Online Account Security (Demo)"
        assert security.published is True


def test_every_question_has_exactly_four_options_and_one_valid_answer(database) -> None:
    with database.session() as session:
        for question in session.scalars(select(Question)):
            assert len(question.options) == 4
            assert 0 <= question.correct_index <= 3
            assert all(question.options)
