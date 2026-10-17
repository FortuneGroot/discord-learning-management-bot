from __future__ import annotations

import discord

from ffcu.models import Lesson, Student
from ffcu.services.course import CourseService, ProgressSummary
from ffcu.services.quiz import QuizOutcome


NAVY = 0x071426
GOLD = 0xD4AF37
GREEN = 0x2E8B57
RED = 0xA83232


def branded(title: str, description: str = "", *, color: int = NAVY) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_author(name="Fortune & Finance Crypto University")
    embed.set_footer(text="Education only • Cryptocurrency and derivatives involve substantial financial risk")
    return embed


def disclaimer_embed() -> discord.Embed:
    return branded(
        "🎓 Welcome to Fortune & Finance Crypto University",
        "This program is educational. It does not provide personalized financial advice, promise profits, "
        "guarantee results, or qualify anyone as a professional trader. Cryptocurrency and derivatives can "
        "cause substantial or total loss. The bot never needs your password, seed phrase, private key, 2FA "
        "code, exchange login, or trading API key. **Never send those to anyone.**",
        color=GOLD,
    )


def lesson_embed(lesson: Lesson, *, video_ready: bool | None = None) -> discord.Embed:
    ready = bool(lesson.video_url) if video_ready is None else video_ready
    video_line = "Use **WATCH CLASS** below." if ready else "Secure class video is not available yet — ask staff before continuing."
    embed = branded(
        f"Level {lesson.level.number} • Lesson {lesson.code} — {lesson.title}",
        f"**Class Video**\n{video_line}\n\n**Estimated time:** {lesson.video_duration_minutes or 'TBD'} minutes\n\n{lesson.description}",
        color=GOLD,
    )
    if lesson.objectives:
        embed.add_field(name="Learning objectives", value="\n".join(f"• {item}" for item in lesson.objectives)[:1024], inline=False)
    if lesson.topics:
        embed.add_field(name="Topics", value="\n".join(f"• {item}" for item in lesson.topics)[:1024], inline=False)
    if lesson.supporting_notes:
        embed.add_field(name="Supporting notes", value=lesson.supporting_notes[:1024], inline=False)
    if lesson.resources:
        links = []
        for item in lesson.resources:
            name, url = str(item.get("name", "Resource")), str(item.get("url", ""))
            links.append(f"[{name}]({url})" if url.startswith("https://") else name)
        embed.add_field(name="Resources", value="\n".join(links)[:1024], inline=False)
    embed.add_field(name="After watching", value="Press **TAKE QUIZ**. A score of 80% or higher is required.", inline=False)
    return embed


def progress_embed(student: Student, progress: ProgressSummary) -> discord.Embed:
    bar = CourseService.progress_bar(progress.overall_percent)
    embed = branded("📊 Student Dashboard", f"**Student:** {student.display_name}", color=GOLD)
    embed.add_field(name="Overall progress", value=f"`{bar}` {progress.overall_percent}%", inline=False)
    embed.add_field(name="Current level", value=progress.current_level, inline=False)
    embed.add_field(name="Current lesson", value=progress.current_lesson, inline=False)
    embed.add_field(name="Levels completed", value=f"{progress.completed_levels} / {progress.total_levels}", inline=True)
    embed.add_field(name="Lesson quizzes passed", value=f"{progress.completed_lessons} / {progress.total_lessons}", inline=True)
    embed.add_field(name="Current average", value=f"{progress.average_score}%", inline=True)
    embed.add_field(name="Status", value=progress.status, inline=False)
    return embed


def quiz_outcome_embed(outcome: QuizOutcome) -> discord.Embed:
    if outcome.passed:
        description = (
            f"**Score:** {outcome.score}%\n**Correct:** {outcome.correct_count} / {outcome.total_questions}\n\n"
            "✅ **PASS**\n\nYour next required step is now available."
        )
        if outcome.graduated:
            description += "\n\n🎓 **You have graduated!** Your certificate is being prepared."
        return branded("Quiz Result", description, color=GREEN)
    topics = "\n".join(f"• {topic}" for topic in outcome.review_topics) or "• Review the complete lesson"
    return branded(
        "Quiz Result",
        f"**Score:** {outcome.score}%\n**Passing score required:** {outcome.passing_score}%\n"
        f"**Correct:** {outcome.correct_count} / {outcome.total_questions}\n\n❌ **NOT PASSED**\n\n"
        f"**Recommended review**\n{topics}\n\nReview the lesson and ask for concept help in University Chat. "
        "Answer keys are not displayed after a failed attempt.",
        color=RED,
    )


def help_embed(channel_id: int) -> discord.Embed:
    chat = f"<#${channel_id}>".replace("$", "") if channel_id else "the configured University Chat channel"
    return branded(
        "🧠 Need help?",
        f"Ask educational questions and request clarification in {chat}. Staff will help you understand concepts; "
        "they will not simply provide quiz answers.\n\n**Your membership includes each month:**\n"
        "• 4 × 15-minute one-on-one mentor sessions\n• 2 × 1-hour professor sessions\n\n"
        "Never share passwords, seed phrases, private keys, 2FA codes, exchange credentials, or trading API keys.",
        color=GOLD,
    )
