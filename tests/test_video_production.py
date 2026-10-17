from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_lesson_1_1_video_covers_every_quiz_question() -> None:
    lesson = yaml.safe_load(
        (ROOT / "video_production" / "lessons" / "1.1.yaml").read_text(encoding="utf-8")
    )
    questions = yaml.safe_load(
        (ROOT / "content" / "questions.yaml").read_text(encoding="utf-8")
    )["lesson_banks"]["1.1"]

    expected_ids = {question["id"] for question in questions}
    coverage = lesson["quiz_coverage"]
    scene_ids = {scene["id"] for scene in lesson["scenes"]}

    assert set(coverage) == expected_ids
    assert all(item["scenes"] for item in coverage.values())
    assert all(set(item["scenes"]) <= scene_ids for item in coverage.values())


def test_lesson_1_1_video_has_complete_production_fields() -> None:
    lesson = yaml.safe_load(
        (ROOT / "video_production" / "lessons" / "1.1.yaml").read_text(encoding="utf-8")
    )

    assert lesson["voice"]["name"].endswith("Neural")
    assert 6 <= len(lesson["scenes"]) <= 14
    assert all(scene["headline"] for scene in lesson["scenes"])
    assert all(scene["narration"] for scene in lesson["scenes"])
    assert sum(len(scene["narration"].split()) for scene in lesson["scenes"]) >= 250
