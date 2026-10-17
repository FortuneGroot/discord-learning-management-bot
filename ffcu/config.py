from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]


def _int(name: str, default: int = 0) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a whole number.") from exc


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _level_roles(value: str) -> dict[int, int]:
    result: dict[int, int] = {}
    for pair in filter(None, (part.strip() for part in value.split(","))):
        try:
            level, role_id = pair.split(":", maxsplit=1)
            result[int(level.strip())] = int(role_id.strip())
        except ValueError as exc:
            raise ValueError("LEVEL_ROLE_IDS must look like 0:123,1:456") from exc
    return result


@dataclass(slots=True)
class Settings:
    discord_token: str = field(default="", repr=False)
    discord_guild_id: int = 0
    admin_role_id: int = 0
    professor_role_id: int = 0
    mentor_role_id: int = 0
    student_role_id: int = 0
    graduate_role_id: int = 0
    university_chat_channel_id: int = 0
    level_role_ids: dict[int, int] = field(default_factory=dict)
    database_url: str = f"sqlite:///{(BASE_DIR / 'fortune_finance_university.db').as_posix()}"
    default_passing_score: int = 80
    quiz_retake_cooldown_minutes: int = 0
    certificate_output_directory: Path = BASE_DIR / "certificates"
    content_directory: Path = BASE_DIR / "content"
    backup_directory: Path = BASE_DIR / "backups"
    log_level: str = "INFO"
    coinbase_referral_url: str = ""
    tradingview_referral_url: str = ""
    bingx_referral_url: str = ""
    public_graduation_announcements: bool = False
    graduation_channel_id: int = 0
    allow_staff_overrides: bool = True

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Settings":
        load_dotenv(env_file or BASE_DIR / ".env")
        settings = cls(
            discord_token=os.getenv("DISCORD_TOKEN", "").strip(),
            discord_guild_id=_int("DISCORD_GUILD_ID"),
            admin_role_id=_int("ADMIN_ROLE_ID"),
            professor_role_id=_int("PROFESSOR_ROLE_ID"),
            mentor_role_id=_int("MENTOR_ROLE_ID"),
            student_role_id=_int("STUDENT_ROLE_ID"),
            graduate_role_id=_int("GRADUATE_ROLE_ID"),
            university_chat_channel_id=_int("UNIVERSITY_CHAT_CHANNEL_ID"),
            level_role_ids=_level_roles(os.getenv("LEVEL_ROLE_IDS", "")),
            database_url=os.getenv(
                "DATABASE_URL", f"sqlite:///{(BASE_DIR / 'fortune_finance_university.db').as_posix()}"
            ).strip(),
            default_passing_score=_int("DEFAULT_PASSING_SCORE", 80),
            quiz_retake_cooldown_minutes=_int("QUIZ_RETAKE_COOLDOWN_MINUTES", 0),
            certificate_output_directory=Path(
                os.getenv("CERTIFICATE_OUTPUT_DIRECTORY", str(BASE_DIR / "certificates"))
            ),
            content_directory=Path(os.getenv("CONTENT_DIRECTORY", str(BASE_DIR / "content"))),
            backup_directory=Path(os.getenv("BACKUP_DIRECTORY", str(BASE_DIR / "backups"))),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            coinbase_referral_url=os.getenv("COINBASE_REFERRAL_URL", "").strip(),
            tradingview_referral_url=os.getenv("TRADINGVIEW_REFERRAL_URL", "").strip(),
            bingx_referral_url=os.getenv("BINGX_REFERRAL_URL", "").strip(),
            public_graduation_announcements=_bool("PUBLIC_GRADUATION_ANNOUNCEMENTS"),
            graduation_channel_id=_int("GRADUATION_CHANNEL_ID"),
            allow_staff_overrides=_bool("ALLOW_STAFF_OVERRIDES", True),
        )
        if not 1 <= settings.default_passing_score <= 100:
            raise ValueError("DEFAULT_PASSING_SCORE must be between 1 and 100.")
        if settings.quiz_retake_cooldown_minutes not in {0, 5, 15, 30, 60}:
            raise ValueError("QUIZ_RETAKE_COOLDOWN_MINUTES must be 0, 5, 15, 30, or 60.")
        return settings

    def validate_for_bot(self) -> list[str]:
        missing: list[str] = []
        if not self.discord_token:
            missing.append("DISCORD_TOKEN")
        if not self.discord_guild_id:
            missing.append("DISCORD_GUILD_ID")
        return missing
