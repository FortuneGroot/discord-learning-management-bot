from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands
from sqlalchemy import select

from ffcu.bot.embeds import branded, lesson_embed, progress_embed
from ffcu.bot.views import DashboardView, ExamStartView, LessonView, QuizView
from ffcu.config import Settings
from ffcu.database import Database
from ffcu.models import Certificate, CourseLevel, Lesson, QuizAttempt, ReferralLink, Student
from ffcu.services.certificate import CertificateService
from ffcu.services.course import CourseService
from ffcu.services.permissions import student_allowed
from ffcu.services.quiz import QuizError, QuizOutcome, QuizService
from ffcu.services.video import VideoAccessError, VideoAccessService


log = logging.getLogger(__name__)


class UniversityBot(commands.Bot):
    def __init__(self, settings: Settings, database: Database):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!ffcu-", intents=intents, help_command=None)
        self.settings = settings
        self.database = database
        self.quiz_service = QuizService(settings.quiz_retake_cooldown_minutes)
        self.certificate_service = CertificateService(settings.certificate_output_directory)
        self.video_access = VideoAccessService(settings)

    async def setup_hook(self) -> None:
        from ffcu.bot.cogs.admin import AdminCog
        from ffcu.bot.cogs.staff import StaffCog
        from ffcu.bot.cogs.student import StudentCog

        await self.add_cog(StudentCog(self))
        await self.add_cog(StaffCog(self))
        await self.add_cog(AdminCog(self))
        if self.settings.discord_guild_id:
            guild = discord.Object(id=self.settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Slash commands synced to guild %s", self.settings.discord_guild_id)
        else:
            await self.tree.sync()

    async def on_ready(self) -> None:
        log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")
        await self.change_presence(activity=discord.Game(name="Fortune & Finance University"))

    def enroll_interaction(self, session, interaction: discord.Interaction) -> Student:
        return CourseService.enroll(session, interaction.user.id, interaction.user.display_name)

    def has_student_access(self, interaction: discord.Interaction) -> bool:
        member = interaction.user
        role_ids = [role.id for role in member.roles] if isinstance(member, discord.Member) else []
        administrator_permission = bool(
            isinstance(member, discord.Member) and member.guild_permissions.administrator
        )
        return student_allowed(
            role_ids,
            student_role_id=self.settings.student_role_id,
            graduate_role_id=self.settings.graduate_role_id,
            admin_role_id=self.settings.admin_role_id,
            professor_role_id=self.settings.professor_role_id,
            mentor_role_id=self.settings.mentor_role_id,
            administrator_permission=administrator_permission,
        )

    async def require_student_access(
        self,
        interaction: discord.Interaction,
        *,
        followup: bool = False,
    ) -> bool:
        if self.has_student_access(interaction):
            return True
        sender = interaction.followup.send if followup or interaction.response.is_done() else interaction.response.send_message
        await sender(
            "This University is available only to active Fortune & Finance members. "
            "If you recently joined, ask staff to confirm your Student role.",
            ephemeral=True,
        )
        return False

    async def send_progress(self, interaction: discord.Interaction, *, followup: bool = False) -> None:
        if not await self.require_student_access(interaction, followup=followup):
            return
        with self.database.session() as session:
            student = self.enroll_interaction(session, interaction)
            embed = progress_embed(student, CourseService.progress(session, student))
        sender = interaction.followup.send if followup else interaction.response.send_message
        await sender(embed=embed, view=DashboardView(interaction.user.id), ephemeral=True)

    async def send_scores(self, interaction: discord.Interaction, *, followup: bool = False) -> None:
        if not await self.require_student_access(interaction, followup=followup):
            return
        with self.database.session() as session:
            student = self.enroll_interaction(session, interaction)
            attempts = list(session.scalars(select(QuizAttempt).where(
                QuizAttempt.student_id == student.id, QuizAttempt.completed_at.is_not(None)
            ).order_by(QuizAttempt.completed_at.desc()).limit(10)))
            if attempts:
                lines = [
                    f"• {item.attempt_type.title()} attempt {item.attempt_number}: **{item.score}%** "
                    f"{'PASS' if item.passed else 'NOT PASSED'}" for item in attempts
                ]
                description = "\n".join(lines)
            else:
                description = "No completed quiz or exam attempts yet."
        sender = interaction.followup.send if followup else interaction.response.send_message
        await sender(embed=branded("My Scores", description), ephemeral=True)

    async def send_current_step(self, interaction: discord.Interaction, *, followup: bool = False) -> None:
        if not await self.require_student_access(interaction, followup=followup):
            return
        with self.database.session() as session:
            student = self.enroll_interaction(session, interaction)
            lesson = CourseService.current_lesson(session, student)
            if lesson:
                try:
                    video_url = self.video_access.playback_url(
                        lesson.video_url,
                        lesson.video_duration_minutes,
                    )
                except VideoAccessError as exc:
                    log.error("Lesson %s video configuration is invalid: %s", lesson.code, exc)
                    video_url = ""
                embed = lesson_embed(lesson, video_ready=bool(video_url))
                referral = session.scalar(select(ReferralLink).where(
                    ReferralLink.partner_key == lesson.partner_key,
                    ReferralLink.enabled.is_(True),
                )) if lesson.partner_key else None
                if referral:
                    embed.add_field(name="Partner/referral disclosure", value=referral.disclosure[:1024], inline=False)
                view = LessonView(
                    interaction.user.id,
                    lesson.id,
                    video_url,
                    referral.display_name if referral else "",
                    referral.url if referral else "",
                )
            else:
                levels = CourseService.published_levels(session)
                pending = next((level for level in levels if CourseService.level_exam_eligible(session, student, level)), None)
                if pending:
                    embed = branded(
                        f"🎓 {pending.title} Final Exam",
                        f"All required lessons are complete. This randomized exam requires {pending.passing_score}% to pass.",
                    )
                    view = ExamStartView(interaction.user.id, "level", pending.id)
                elif CourseService.final_exam_eligible(session, student) and student.status != "graduate":
                    embed = branded(
                        "🎓 Comprehensive Final Examination",
                        "All published levels are complete. Pass this randomized comprehensive exam with 80% or higher to graduate.",
                    )
                    view = ExamStartView(interaction.user.id, "final", None)
                elif student.status == "graduate":
                    embed = branded("🎓 University Complete", "Congratulations, graduate. Use `/my-certificate` to retrieve your certificate.")
                    view = None
                else:
                    embed = branded("No class available", "Your next class is not yet published or an assignment still needs approval. Ask University Chat for help.")
                    view = None
        sender = interaction.followup.send if followup else interaction.response.send_message
        await sender(embed=embed, view=view, ephemeral=True)

    async def begin_quiz(self, interaction: discord.Interaction, attempt_type: str, target_id: int | None) -> None:
        if not await self.require_student_access(interaction, followup=True):
            return
        try:
            with self.database.session() as session:
                student = self.enroll_interaction(session, interaction)
                quiz = self.quiz_service.start(session, student, attempt_type, target_id)
            view = QuizView(interaction.user.id, quiz)
            await interaction.followup.send(embed=view.embed(), view=view, ephemeral=True)
        except QuizError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)

    async def handle_post_quiz(self, interaction: discord.Interaction, attempt_id: int, outcome: QuizOutcome) -> None:
        if not outcome.passed or not isinstance(interaction.user, discord.Member):
            return
        certificate_path: Path | None = None
        with self.database.session() as session:
            attempt = session.get(QuizAttempt, attempt_id)
            if attempt and attempt.attempt_type == "level" and attempt.level_id:
                level = session.get(CourseLevel, attempt.level_id)
                role_id = self.settings.level_role_ids.get(level.number)
                if role_id:
                    role = interaction.user.guild.get_role(role_id)
                    if role and role not in interaction.user.roles:
                        try:
                            await interaction.user.add_roles(role, reason=f"Passed FFCU Level {level.number}")
                        except discord.Forbidden:
                            log.warning("Unable to assign level role %s", role_id)
            if outcome.graduated:
                if self.settings.graduate_role_id:
                    role = interaction.user.guild.get_role(self.settings.graduate_role_id)
                    if role:
                        try:
                            await interaction.user.add_roles(role, reason="FFCU graduation")
                        except discord.Forbidden:
                            log.warning("Unable to assign graduate role")
                student = session.get(Student, attempt.student_id)
                certificate = self.certificate_service.issue(session, student)
                certificate_path = Path(certificate.file_path)
        if certificate_path and certificate_path.exists():
            await interaction.followup.send(
                "Your Certificate of Completion is ready.", file=discord.File(certificate_path), ephemeral=True
            )
            if self.settings.public_graduation_announcements and self.settings.graduation_channel_id:
                channel = self.get_channel(self.settings.graduation_channel_id)
                if isinstance(channel, discord.TextChannel):
                    try:
                        await channel.send(f"🎓 Congratulations to {interaction.user.mention} on completing Fortune & Finance Crypto University!")
                    except discord.Forbidden:
                        log.warning("Unable to post the configured public graduation announcement.")

    async def on_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError) -> None:
        log.exception("Application command failed", exc_info=error)
        message = "Something went wrong while processing that request. Staff can check the bot log for details."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
