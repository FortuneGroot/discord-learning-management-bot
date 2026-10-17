from __future__ import annotations

import discord

from ffcu.bot.embeds import help_embed, quiz_outcome_embed
from ffcu.services.quiz import QuizError, QuizSession


class OwnerView(discord.ui.View):
    def __init__(self, owner_id: int, *, timeout: float = 900):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This private control belongs to another student.", ephemeral=True)
            return False
        return True


class DashboardView(OwnerView):
    @discord.ui.button(label="CONTINUE CLASS", style=discord.ButtonStyle.primary, emoji="📚")
    async def continue_class(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.client.send_current_step(interaction, followup=True)

    @discord.ui.button(label="VIEW PROGRESS", style=discord.ButtonStyle.secondary, emoji="📊")
    async def view_progress(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.client.send_progress(interaction, followup=True)

    @discord.ui.button(label="GET HELP", style=discord.ButtonStyle.secondary, emoji="🧠")
    async def get_help(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.send_message(
            embed=help_embed(interaction.client.settings.university_chat_channel_id), ephemeral=True
        )

    @discord.ui.button(label="VIEW SCORES", style=discord.ButtonStyle.secondary)
    async def scores(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.client.send_scores(interaction, followup=True)


class LessonView(OwnerView):
    def __init__(
        self, owner_id: int, lesson_id: int, video_url: str, partner_name: str = "", partner_url: str = ""
    ):
        super().__init__(owner_id)
        self.lesson_id = lesson_id
        if video_url.startswith("https://"):
            self.add_item(discord.ui.Button(label="WATCH CLASS", style=discord.ButtonStyle.link, url=video_url, emoji="▶️"))
        if partner_name and partner_url.startswith("https://"):
            self.add_item(discord.ui.Button(
                label=f"OPEN {partner_name.upper()}"[:80], style=discord.ButtonStyle.link, url=partner_url
            ))

    @discord.ui.button(label="TAKE QUIZ", style=discord.ButtonStyle.success, emoji="✅")
    async def take_quiz(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.client.begin_quiz(interaction, "lesson", self.lesson_id)

    @discord.ui.button(label="GET HELP", style=discord.ButtonStyle.secondary, emoji="🧠")
    async def get_help(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.send_message(
            embed=help_embed(interaction.client.settings.university_chat_channel_id), ephemeral=True
        )


class ExamStartView(OwnerView):
    def __init__(self, owner_id: int, attempt_type: str, target_id: int | None):
        super().__init__(owner_id)
        self.attempt_type, self.target_id = attempt_type, target_id

    @discord.ui.button(label="BEGIN EXAM", style=discord.ButtonStyle.danger, emoji="🎓")
    async def begin(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.client.begin_quiz(interaction, self.attempt_type, self.target_id)


class QuizView(OwnerView):
    def __init__(self, owner_id: int, quiz: QuizSession):
        super().__init__(owner_id, timeout=1800)
        self.quiz = quiz
        self.position = 0
        self.answers: dict[int, int] = {}

    def embed(self) -> discord.Embed:
        question = self.quiz.questions[self.position]
        choices = "\n\n".join(f"**{letter}.** {option}" for letter, option in zip("ABCD", question.options))
        embed = discord.Embed(
            title=self.quiz.title,
            description=f"**Question {self.position + 1} of {len(self.quiz.questions)}**\n\n{question.prompt}\n\n{choices}",
            color=0x071426,
        )
        embed.set_footer(text=f"Attempt {self.quiz.attempt_number} • Select one answer • Answers cannot be changed")
        return embed

    async def choose(self, interaction: discord.Interaction, selected_index: int) -> None:
        question = self.quiz.questions[self.position]
        if question.id in self.answers:
            await interaction.response.send_message("That question was already answered.", ephemeral=True)
            return
        self.answers[question.id] = selected_index
        self.position += 1
        if self.position < len(self.quiz.questions):
            await interaction.response.edit_message(embed=self.embed(), view=self)
            return
        for item in self.children:
            item.disabled = True
        try:
            with interaction.client.database.session() as session:
                outcome = interaction.client.quiz_service.submit(session, self.quiz.attempt_id, self.answers)
        except QuizError as exc:
            await interaction.response.edit_message(content=str(exc), embed=None, view=None)
            return
        result_view: discord.ui.View
        if outcome.passed:
            result_view = PassedResultView(self.owner_id)
        else:
            result_view = FailedResultView(
                self.owner_id, self.quiz.attempt_type, self.quiz.target_id,
                interaction.client.settings.discord_guild_id,
                interaction.client.settings.university_chat_channel_id,
            )
        await interaction.response.edit_message(embed=quiz_outcome_embed(outcome), view=result_view)
        await interaction.client.handle_post_quiz(interaction, self.quiz.attempt_id, outcome)

    @discord.ui.button(label="A", style=discord.ButtonStyle.primary)
    async def answer_a(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await self.choose(interaction, 0)

    @discord.ui.button(label="B", style=discord.ButtonStyle.primary)
    async def answer_b(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await self.choose(interaction, 1)

    @discord.ui.button(label="C", style=discord.ButtonStyle.primary)
    async def answer_c(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await self.choose(interaction, 2)

    @discord.ui.button(label="D", style=discord.ButtonStyle.primary)
    async def answer_d(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await self.choose(interaction, 3)


class PassedResultView(OwnerView):
    @discord.ui.button(label="CONTINUE", style=discord.ButtonStyle.success, emoji="📚")
    async def continue_class(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.client.send_current_step(interaction, followup=True)


class FailedResultView(OwnerView):
    def __init__(
        self, owner_id: int, attempt_type: str, target_id: int | None, guild_id: int, chat_channel_id: int
    ):
        super().__init__(owner_id)
        self.attempt_type, self.target_id = attempt_type, target_id
        if guild_id and chat_channel_id:
            self.add_item(discord.ui.Button(
                label="UNIVERSITY CHAT",
                style=discord.ButtonStyle.link,
                url=f"https://discord.com/channels/{guild_id}/{chat_channel_id}",
                emoji="🧠",
            ))

    @discord.ui.button(label="REVIEW LESSON", style=discord.ButtonStyle.secondary, emoji="📚")
    async def review(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.client.send_current_step(interaction, followup=True)

    @discord.ui.button(label="RETAKE WHEN ELIGIBLE", style=discord.ButtonStyle.primary)
    async def retake(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.client.begin_quiz(interaction, self.attempt_type, self.target_id)
