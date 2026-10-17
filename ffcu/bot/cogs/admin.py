from __future__ import annotations

from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import delete, func, select

from ffcu.bot.access import require_access
from ffcu.bot.embeds import branded
from ffcu.models import (
    Certificate,
    CourseLevel,
    Lesson,
    LessonCompletion,
    LevelCompletion,
    Question,
    QuizAttempt,
    Student,
    utcnow,
)
from ffcu.services.audit import record_audit
from ffcu.services.course import CourseService
from ffcu.services.permissions import StaffAccess


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _admin(self, interaction: discord.Interaction) -> bool:
        return await require_access(interaction, StaffAccess.ADMIN)

    @app_commands.command(name="university-admin", description="Open the private university administration guide")
    async def university_admin(self, interaction: discord.Interaction) -> None:
        if not await self._admin(interaction):
            return
        await interaction.response.send_message(embed=branded(
            "University Administration",
            "Use `/university-stats`, `/student-progress`, `/student-lock`, `/student-unlock`, `/student-pass`, "
            "`/student-fail`, `/student-reset`, `/student-certificate`, `/course`, `/lesson`, `/quiz`, and `/exam`. "
            "Every material override is written to the audit log.",
        ), ephemeral=True)

    @app_commands.command(name="student-lock", description="Lock a student's university access")
    async def student_lock(self, interaction: discord.Interaction, member: discord.Member, reason: str) -> None:
        if not await self._admin(interaction):
            return
        with self.bot.database.session() as session:
            student = CourseService.enroll(session, member.id, member.display_name)
            student.status = "locked"
            record_audit(session, interaction.user.id, "student_lock", student_discord_id=member.id, details={"reason": reason[:500]})
        await interaction.response.send_message(f"Locked university access for {member.mention}.", ephemeral=True)

    @app_commands.command(name="student-unlock", description="Restore a student's university access")
    async def student_unlock(self, interaction: discord.Interaction, member: discord.Member, reason: str) -> None:
        if not await self._admin(interaction):
            return
        with self.bot.database.session() as session:
            student = CourseService.enroll(session, member.id, member.display_name)
            student.status = "active" if student.certificate is None else "graduate"
            record_audit(session, interaction.user.id, "student_unlock", student_discord_id=member.id, details={"reason": reason[:500]})
        await interaction.response.send_message(f"Restored university access for {member.mention}.", ephemeral=True)

    @app_commands.command(name="student-reset", description="Reset progress for a non-certified student")
    async def student_reset(self, interaction: discord.Interaction, member: discord.Member, reason: str) -> None:
        if not await self._admin(interaction):
            return
        try:
            with self.bot.database.session() as session:
                student = session.scalar(select(Student).where(Student.discord_user_id == member.id))
                if not student:
                    raise ValueError("Student has not enrolled.")
                CourseService.reset_progress(session, student)
                record_audit(session, interaction.user.id, "student_reset", student_discord_id=member.id, details={"reason": reason[:500]})
            message = f"Reset university progress for {member.mention}."
        except ValueError as exc:
            message = str(exc)
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="student-pass", description="Apply an audited manual lesson, level, or final pass")
    @app_commands.describe(target_type="lesson, level, or final", target="Lesson code (2.3), level number, or final")
    async def student_pass(
        self, interaction: discord.Interaction, member: discord.Member, target_type: str, target: str, reason: str
    ) -> None:
        if not await self._admin(interaction):
            return
        target_type = target_type.lower().strip()
        try:
            with self.bot.database.session() as session:
                student = CourseService.enroll(session, member.id, member.display_name)
                details = {"target_type": target_type, "target": target, "reason": reason[:500]}
                if target_type == "lesson":
                    lesson = session.scalar(select(Lesson).where(Lesson.code == target))
                    if not lesson:
                        raise ValueError("Lesson not found.")
                    completion = session.scalar(select(LessonCompletion).where(
                        LessonCompletion.student_id == student.id, LessonCompletion.lesson_id == lesson.id
                    ))
                    if not completion:
                        session.add(LessonCompletion(student_id=student.id, lesson_id=lesson.id, best_score=100, override=True))
                elif target_type == "level":
                    level = session.scalar(select(CourseLevel).where(CourseLevel.number == int(target)))
                    if not level:
                        raise ValueError("Level not found.")
                    completion = session.scalar(select(LevelCompletion).where(
                        LevelCompletion.student_id == student.id, LevelCompletion.level_id == level.id
                    ))
                    if not completion:
                        session.add(LevelCompletion(student_id=student.id, level_id=level.id, best_score=100, override=True))
                elif target_type == "final":
                    if not CourseService.final_exam_eligible(session, student):
                        raise ValueError("Complete or override every published level before overriding the final exam.")
                    session.add(QuizAttempt(
                        student_id=student.id, attempt_type="final", attempt_number=1, questions_used={},
                        score=100, correct_count=0, total_questions=0, passed=True, completed_at=utcnow()
                    ))
                    student.status = "graduate"
                else:
                    raise ValueError("Target type must be lesson, level, or final.")
                record_audit(session, interaction.user.id, "manual_pass", student_discord_id=member.id, details=details)
            message = f"Recorded audited manual pass for {member.mention}: {target_type} {target}."
        except (ValueError, TypeError) as exc:
            message = str(exc)
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="student-fail", description="Remove a manual or earned completion after review")
    @app_commands.describe(target_type="lesson or level", target="Lesson code or level number")
    async def student_fail(
        self, interaction: discord.Interaction, member: discord.Member, target_type: str, target: str, reason: str
    ) -> None:
        if not await self._admin(interaction):
            return
        target_type = target_type.lower().strip()
        with self.bot.database.session() as session:
            student = session.scalar(select(Student).where(Student.discord_user_id == member.id))
            if not student:
                message = "Student has not enrolled."
            elif student.certificate:
                message = "A certificate has already been issued. Preserve the completion record and resolve this administratively."
            elif target_type == "lesson":
                lesson = session.scalar(select(Lesson).where(Lesson.code == target))
                if not lesson:
                    message = "Lesson not found."
                else:
                    session.execute(delete(LessonCompletion).where(
                        LessonCompletion.student_id == student.id, LessonCompletion.lesson_id == lesson.id
                    ))
                    record_audit(session, interaction.user.id, "manual_fail", student_discord_id=member.id, details={"target_type": target_type, "target": target, "reason": reason[:500]})
                    message = "Lesson completion removed; the lesson is required again."
            elif target_type == "level":
                level = session.scalar(select(CourseLevel).where(CourseLevel.number == int(target)))
                if not level:
                    message = "Level not found."
                else:
                    session.execute(delete(LevelCompletion).where(
                        LevelCompletion.student_id == student.id, LevelCompletion.level_id == level.id
                    ))
                    record_audit(session, interaction.user.id, "manual_fail", student_discord_id=member.id, details={"target_type": target_type, "target": target, "reason": reason[:500]})
                    message = "Level completion removed; the level exam is required again."
            else:
                message = "Target type must be lesson or level."
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="student-certificate", description="Issue or retrieve a verified graduate certificate")
    async def student_certificate(
        self, interaction: discord.Interaction, member: discord.Member, certificate_name: str = ""
    ) -> None:
        if not await self._admin(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            with self.bot.database.session() as session:
                student = session.scalar(select(Student).where(Student.discord_user_id == member.id))
                if not student:
                    raise ValueError("Student has not enrolled.")
                certificate = self.bot.certificate_service.issue(session, student, certificate_name or None)
                path = Path(certificate.file_path)
                record_audit(session, interaction.user.id, "certificate_issue", student_discord_id=member.id, details={"certificate_id": certificate.certificate_id})
            await interaction.followup.send(f"Certificate `{certificate.certificate_id}`", file=discord.File(path), ephemeral=True)
        except (ValueError, RuntimeError) as exc:
            await interaction.followup.send(str(exc), ephemeral=True)

    @app_commands.command(name="course", description="Inspect the published course structure")
    async def course(self, interaction: discord.Interaction) -> None:
        if not await self._admin(interaction):
            return
        with self.bot.database.session() as session:
            levels = CourseService.published_levels(session)
            lines = [f"• Level {level.number}: **{level.title}** — {len(CourseService.published_lessons(session, level.id))} lessons" for level in levels]
        await interaction.response.send_message(embed=branded("Published Course", "\n".join(lines)), ephemeral=True)

    @app_commands.command(name="lesson", description="Inspect one lesson's content configuration")
    async def lesson(self, interaction: discord.Interaction, code: str) -> None:
        if not await self._admin(interaction):
            return
        with self.bot.database.session() as session:
            item = session.scalar(select(Lesson).where(Lesson.code == code))
            if item:
                count = int(session.scalar(select(func.count(Question.id)).where(Question.lesson_id == item.id, Question.active.is_(True))) or 0)
                text = f"**{item.code} {item.title}**\nPublished: {item.published}\nVideo: {'configured' if item.video_url else 'missing'}\nQuestion bank: {count}\nQuiz size: {item.quiz_size}"
            else:
                text = "Lesson not found."
        await interaction.response.send_message(text, ephemeral=True)

    @app_commands.command(name="quiz", description="Inspect a lesson question bank")
    async def quiz(self, interaction: discord.Interaction, lesson_code: str) -> None:
        if not await self._admin(interaction):
            return
        with self.bot.database.session() as session:
            lesson = session.scalar(select(Lesson).where(Lesson.code == lesson_code))
            count = int(session.scalar(select(func.count(Question.id)).where(Question.lesson_id == lesson.id, Question.active.is_(True))) or 0) if lesson else 0
        await interaction.response.send_message(f"Lesson `{lesson_code}` has {count} active approved questions.", ephemeral=True)

    @app_commands.command(name="exam", description="Inspect a level or final exam question bank")
    async def exam(self, interaction: discord.Interaction, level_number: int = -1) -> None:
        if not await self._admin(interaction):
            return
        with self.bot.database.session() as session:
            if level_number == -1:
                count = int(session.scalar(select(func.count(Question.id)).where(Question.question_type == "final", Question.active.is_(True))) or 0)
                label = "Final examination"
            else:
                level = session.scalar(select(CourseLevel).where(CourseLevel.number == level_number))
                count = int(session.scalar(select(func.count(Question.id)).where(Question.question_type == "level", Question.level_id == level.id, Question.active.is_(True))) or 0) if level else 0
                label = f"Level {level_number} examination"
        await interaction.response.send_message(f"{label} has {count} active approved questions.", ephemeral=True)

    @app_commands.command(name="university-stats", description="View private university statistics")
    async def university_stats(self, interaction: discord.Interaction) -> None:
        if not await self._admin(interaction):
            return
        with self.bot.database.session() as session:
            total = int(session.scalar(select(func.count(Student.id))) or 0)
            active = int(session.scalar(select(func.count(Student.id)).where(Student.status == "active")) or 0)
            graduates = int(session.scalar(select(func.count(Student.id)).where(Student.status == "graduate")) or 0)
            certificates = int(session.scalar(select(func.count(Certificate.id))) or 0)
            average = session.scalar(select(func.avg(QuizAttempt.score)).where(QuizAttempt.completed_at.is_not(None)))
            stalled = CourseService.stalled_count(session)
            students = list(session.scalars(select(Student)))
            average_completion = round(sum(CourseService.progress(session, item).overall_percent for item in students) / len(students)) if students else 0
            failed_lesson_row = session.execute(
                select(Lesson.title, func.count(QuizAttempt.id))
                .join(QuizAttempt, QuizAttempt.lesson_id == Lesson.id)
                .where(QuizAttempt.attempt_type == "lesson", QuizAttempt.passed.is_(False))
                .group_by(Lesson.id)
                .order_by(func.count(QuizAttempt.id).desc())
                .limit(1)
            ).first()
            failed_exam_row = session.execute(
                select(CourseLevel.title, func.count(QuizAttempt.id))
                .join(QuizAttempt, QuizAttempt.level_id == CourseLevel.id)
                .where(QuizAttempt.attempt_type == "level", QuizAttempt.passed.is_(False))
                .group_by(CourseLevel.id)
                .order_by(func.count(QuizAttempt.id).desc())
                .limit(1)
            ).first()
        text = (
            f"**Total enrolled:** {total}\n**Active students:** {active}\n**Graduates:** {graduates}\n"
            f"**Average completion:** {average_completion}%\n**Average quiz/exam score:** {round(float(average or 0))}%\n"
            f"**Most failed lesson:** {failed_lesson_row[0] if failed_lesson_row else 'No failures'}\n"
            f"**Most failed exam:** {failed_exam_row[0] if failed_exam_row else 'No failures'}\n"
            f"**Students stalled 7+ days:** {stalled}\n**Certificates issued:** {certificates}"
        )
        await interaction.response.send_message(embed=branded("University Statistics", text), ephemeral=True)


async def setup(bot) -> None:
    await bot.add_cog(AdminCog(bot))
