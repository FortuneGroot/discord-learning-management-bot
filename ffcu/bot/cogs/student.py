from __future__ import annotations

from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from ffcu.bot.embeds import disclaimer_embed, help_embed
from ffcu.bot.views import DashboardView
from ffcu.models import Assignment, AssignmentSubmission, Certificate, CourseLevel, Student
from ffcu.services.course import CourseService


class StudentCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="university", description="Open your Fortune & Finance University dashboard")
    async def university(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.bot.send_progress(interaction, followup=True)

    @app_commands.command(name="start-university", description="Enroll and begin Orientation")
    async def start_university(self, interaction: discord.Interaction) -> None:
        if not await self.bot.require_student_access(interaction):
            return
        with self.bot.database.session() as session:
            CourseService.enroll(session, interaction.user.id, interaction.user.display_name)
        await interaction.response.send_message(
            embed=disclaimer_embed(), view=DashboardView(interaction.user.id), ephemeral=True
        )

    @app_commands.command(name="progress", description="View your university progress")
    async def progress(self, interaction: discord.Interaction) -> None:
        await self.bot.send_progress(interaction)

    @app_commands.command(name="current-lesson", description="Open your current required lesson")
    async def current_lesson(self, interaction: discord.Interaction) -> None:
        await self.bot.send_current_step(interaction)

    @app_commands.command(name="continue", description="Continue to your next required university step")
    async def continue_university(self, interaction: discord.Interaction) -> None:
        await self.bot.send_current_step(interaction)

    @app_commands.command(name="help-university", description="See University Chat and member support benefits")
    async def help_university(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=help_embed(self.bot.settings.university_chat_channel_id), ephemeral=True
        )

    @app_commands.command(name="my-scores", description="View your latest quiz and exam scores")
    async def my_scores(self, interaction: discord.Interaction) -> None:
        await self.bot.send_scores(interaction)

    @app_commands.command(name="my-certificate", description="Retrieve your issued graduation certificate")
    async def my_certificate(self, interaction: discord.Interaction) -> None:
        with self.bot.database.session() as session:
            student = session.scalar(select(Student).where(Student.discord_user_id == interaction.user.id))
            certificate = session.scalar(select(Certificate).where(Certificate.student_id == student.id)) if student else None
            path = Path(certificate.file_path) if certificate else None
        if not path or not path.exists():
            await interaction.response.send_message("No certificate has been issued to you yet.", ephemeral=True)
            return
        await interaction.response.send_message(file=discord.File(path), ephemeral=True)

    @app_commands.command(name="assignments", description="View enabled practical assignments")
    async def assignments(self, interaction: discord.Interaction) -> None:
        if not await self.bot.require_student_access(interaction):
            return
        with self.bot.database.session() as session:
            student = CourseService.enroll(session, interaction.user.id, interaction.user.display_name)
            items = list(session.scalars(select(Assignment).where(Assignment.enabled.is_(True)).order_by(Assignment.level_id)))
            lines = []
            for item in items:
                submission = session.scalar(select(AssignmentSubmission).where(
                    AssignmentSubmission.assignment_id == item.id, AssignmentSubmission.student_id == student.id
                ))
                status = submission.status.upper() if submission else "NOT SUBMITTED"
                lines.append(f"• `{item.external_id}` **{item.title}** — {status}{' (required)' if item.required else ''}")
        await interaction.response.send_message("\n".join(lines) if lines else "No practical assignments are enabled.", ephemeral=True)

    @app_commands.command(name="submit-assignment", description="Submit text and an optional HTTPS attachment link")
    @app_commands.describe(assignment_id="ID shown by /assignments", submission="Your work", attachment_url="Optional HTTPS image/file link")
    async def submit_assignment(
        self, interaction: discord.Interaction, assignment_id: str, submission: str, attachment_url: str = ""
    ) -> None:
        if not await self.bot.require_student_access(interaction):
            return
        if attachment_url and not attachment_url.startswith("https://"):
            await interaction.response.send_message("Attachment links must use HTTPS.", ephemeral=True)
            return
        with self.bot.database.session() as session:
            student = CourseService.enroll(session, interaction.user.id, interaction.user.display_name)
            assignment = session.scalar(select(Assignment).where(
                Assignment.external_id == assignment_id, Assignment.enabled.is_(True)
            ))
            if not assignment:
                message = "Enabled assignment not found."
            else:
                item = session.scalar(select(AssignmentSubmission).where(
                    AssignmentSubmission.assignment_id == assignment.id, AssignmentSubmission.student_id == student.id
                ))
                if item is None:
                    item = AssignmentSubmission(assignment_id=assignment.id, student_id=student.id)
                    session.add(item)
                item.submission_text = submission[:4000]
                item.attachment_url = attachment_url[:500]
                item.status = "submitted"
                item.feedback = ""
                message = "Assignment submitted for professor review. Do not include real account credentials or secrets."
        await interaction.response.send_message(message, ephemeral=True)


async def setup(bot) -> None:
    await bot.add_cog(StudentCog(bot))
