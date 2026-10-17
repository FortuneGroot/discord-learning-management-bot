"""Run a complete student journey through the sample course without Discord.

Usage: python scripts/demo_walkthrough.py [--output demo_output]
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from ffcu.database import Database
from ffcu.models import Question, QuizAttempt
from ffcu.services.certificate import CertificateService
from ffcu.services.content_loader import load_content
from ffcu.services.course import CourseService
from ffcu.services.quiz import QuizService


def answers_for(session, attempt_id: int, correct: bool) -> dict[int, int]:
    attempt = session.get(QuizAttempt, attempt_id)
    answers: dict[int, int] = {}
    for question_id in attempt.questions_used["question_ids"]:
        order = attempt.questions_used["option_orders"][str(question_id)]
        right = order.index(session.get(Question, question_id).correct_index)
        answers[question_id] = right if correct else (right + 1) % 4
    return answers


def take(session, quiz: QuizService, student, kind: str, target_id: int | None, label: str, correct: bool = True):
    started = quiz.start(session, student, kind, target_id)
    outcome = quiz.submit(session, started.attempt_id, answers_for(session, started.attempt_id, correct))
    status = "PASS" if outcome.passed else "FAIL"
    print(f"  {label:<48} attempt {started.attempt_number}: {outcome.score:>3}% {status}")
    if not outcome.passed and outcome.review_topics:
        print(f"    review topics: {', '.join(outcome.review_topics)}")
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="demo_output", help="Folder for the demo database and certificate.")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)

    db_path = output / "demo.db"
    db_path.unlink(missing_ok=True)
    database = Database(f"sqlite:///{db_path.as_posix()}")
    database.create_all()
    quiz = QuizService(rng=random.Random(2026))
    with database.session() as session:
        summary = load_content(session, PROJECT / "content")
        print(f"Loaded sample course: {summary.levels} levels, {summary.lessons} lessons, {summary.questions} questions\n")
        student = CourseService.enroll(session, 100000000000000001, "Demo Student")

        first = CourseService.published_lessons(session)[1]
        try:
            quiz.start(session, student, "lesson", first.id)
        except Exception as exc:
            print(f"Locked-lesson check ({first.code}): {exc}\n")

        for level in CourseService.published_levels(session):
            print(f"Level {level.number}: {level.title}")
            for index, lesson in enumerate(CourseService.published_lessons(session, level.id)):
                label = f"Lesson {lesson.code} {lesson.title}"
                if index == 0 and level.number == 0:
                    take(session, quiz, student, "lesson", lesson.id, label, correct=False)
                take(session, quiz, student, "lesson", lesson.id, label)
            take(session, quiz, student, "level", level.id, f"Level {level.number} exam")
            print()

        outcome = take(session, quiz, student, "final", None, "Comprehensive final exam")
        progress = CourseService.progress(session, student)
        print(f"\nGraduated: {outcome.graduated} | lessons completed {progress.completed_lessons}/{progress.total_lessons}")
        certificate = CertificateService(output / "certificates").issue(session, student)
        print(f"Certificate {certificate.certificate_id} -> {certificate.file_path}")
    database.dispose()


if __name__ == "__main__":
    main()
