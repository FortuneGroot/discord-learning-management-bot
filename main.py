from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from sqlalchemy import select

from ffcu.bot.app import UniversityBot
from ffcu.config import BASE_DIR, Settings
from ffcu.database import Database
from ffcu.models import ReferralLink
from ffcu.services.content_loader import load_content


def configure_logging(level: str) -> None:
    log_directory = BASE_DIR / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(log_directory / "ffcu.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logging.basicConfig(level=getattr(logging, level, logging.INFO), handlers=[file_handler, console_handler])
    logging.getLogger("discord.http").setLevel(logging.WARNING)


def prepare_database(settings: Settings) -> Database:
    database = Database(settings.database_url)
    database.create_all()
    with database.session() as session:
        summary = load_content(session, settings.content_directory, settings.default_passing_score)
        configured = {
            "coinbase": settings.coinbase_referral_url,
            "tradingview": settings.tradingview_referral_url,
            "bingx": settings.bingx_referral_url,
        }
        for key, url in configured.items():
            referral = session.scalar(select(ReferralLink).where(ReferralLink.partner_key == key))
            if referral:
                referral.url = url
                referral.enabled = bool(url)
    logging.getLogger(__name__).info(
        "Content loaded: %s levels, %s lessons, %s questions", summary.levels, summary.lessons, summary.questions
    )
    return database


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    missing = settings.validate_for_bot()
    if missing:
        raise SystemExit(f"Missing required .env setting(s): {', '.join(missing)}. See README.md.")
    database = prepare_database(settings)
    bot = UniversityBot(settings, database)
    try:
        bot.run(settings.discord_token, log_handler=None)
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
