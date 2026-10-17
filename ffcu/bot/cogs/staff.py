from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select

from ffcu.bot.access import require_access
from ffcu.bot.embeds import branded, progress_embed
from ffcu.models import Assignment, AssignmentSubmission, Question, QuestionResult, QuizAttempt, Student, utcnow
from ffcu.services.audit import record_audit
from ffcu.services.course import CourseService
from ffcu.services.permissions import StaffAccess


class StaffCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="student", description="View a student's private university summary (staff)")
    async def student(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if not await require_access(interaction, StaffAccess.MENTOR):
            return
        with self.bot.database.session() as session:
            student = session.scalar(select(Student).where(Student.discord_user_id == member.id))
            if not student:
                embed = branded("Student not enrolled", f"{member.mention} has not started the university.")
            else:
                embed = progress_embed(student, CourseService.progress(session, student))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="student-progress", description="View scores and review topics for a student (staff)")
    async def student_progress(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if not await require_access(interaction, StaffAccess.MENTOR):
            return
        with self.bot.database.session() as session:
            student = session.scalar(select(Student).where(Student.discord_user_id == member.id))
            if not student:
                description = "Student has not enrolled."
            else:
                attempts = list(session.scalars(select(QuizAttempt).where(
                    QuizAttempt.student_id == student.id, QuizAttempt.completed_at.is_not(None)
                ).order_by(QuizAttempt.completed_at.desc()).limit(20)))
                lines = [
                    f"• {attempt.attempt_type.title()} #{attempt.attempt_number}: {attempt.score}% "
                    f"({'PASS' if attempt.passed else 'REVIEW NEEDED'})" for attempt in attempts
                ]
                topic_rows = session.execute(
                    select(Question.topic, func.count(QuestionResult.id))
                    .join(QuestionResult, QuestionResult.question_id == Question.id)
                    .join(QuizAttempt, QuizAttempt.id == QuestionResult.attempt_id)
                    .where(QuizAttempt.student_id == student.id, QuestionResult.correct.is_(False))
                    .group_by(Question.topic)
                    .order_by(func.count(QuestionResult.id).desc())
                    .limit(5)
                ).all()
                topic_text = ", ".join(f"{topic} ({count})" for topic, count in topic_rows) or "None recorded"
                description = ("\n".join(lines) or "No completed attempts.") + f"\n\n**Most missed topics:** {topic_text}"
        await interaction.response.send_message(embed=branded(f"Private Progress • {member.display_name}", description), ephemeral=True)

    @app_commands.command(name="assignment-review", description="Approve or reject a submitted practical assignment (professor/admin)")
    @app_commands.describe(submission_id="Database submission ID", decision="approve or reject", feedback="Educational feedback")
    async def assignment_review(
        self, interaction: discord.Interaction, submission_id: int, decision: str, feedback: str = ""
    ) -> None:
        if not await require_access(interaction, StaffAccess.PROFESSOR):
            return
        decision = decision.lower().strip()
        if decision not in {"approve", "reject"}:
            await interaction.response.send_message("Decision must be `approve` or `reject`.", ephemeral=True)
            return
        with self.bot.database.session() as session:
            submission = session.get(AssignmentSubmission, submission_id)
            if submission is None:
                message = "Submission not found."
            else:
                submission.status = "approved" if decision == "approve" else "rejected"
                submission.feedback = feedback[:4000]
                submission.reviewed_by_discord_id = interaction.user.id
                submission.reviewed_at = utcnow()
                student = session.get(Student, submission.student_id)
                record_audit(
                    session,
                    interaction.user.id,
                    f"assignment_{decision}",
                    student_discord_id=student.discord_user_id,
                    details={"submission_id": submission.id, "feedback": feedback[:500]},
                )
                message = f"Submission {submission.id} marked {submission.status}."
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="pending-assignments", description="List practical assignments awaiting review")
    async def pending_assignments(self, interaction: discord.Interaction) -> None:
        if not await require_access(interaction, StaffAccess.PROFESSOR):
            return
        with self.bot.database.session() as session:
            submissions = list(session.scalars(select(AssignmentSubmission).where(
                AssignmentSubmission.status == "submitted"
            ).order_by(AssignmentSubmission.created_at).limit(25)))
            lines = []
            for item in submissions:
                assignment = session.get(Assignment, item.assignment_id)
                student = session.get(Student, item.student_id)
                lines.append(f"• ID `{item.id}` • {student.display_name} • {assignment.title}")
        await interaction.response.send_message("\n".join(lines) if lines else "No pending assignments.", ephemeral=True)


async def setup(bot) -> None:
    await bot.add_cog(StaffCog(bot))
