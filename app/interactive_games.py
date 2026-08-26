"""
Interactive trivia game for WickedYoda bot.

Uses discord.ui buttons for multiple-choice answers, tracks scores in the
cookie/store DB, and displays a leaderboard.
"""

from __future__ import annotations

import random

import discord

from app.cookies import CookieStore

NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


class TriviaView(discord.ui.View):
    """Interactive trivia view with multiple-choice buttons."""

    def __init__(
        self,
        question: str,
        choices: list[str],
        correct_index: int,
        guild_id: int,
        cookie_store: CookieStore | None,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.question = question
        self.choices = choices
        self.correct_index = correct_index
        self.guild_id = guild_id
        self.cookie_store = cookie_store
        self.answered = False
        self.correct_user: int | None = None

        # Add a button for each choice
        for i, choice_text in enumerate(choices[:10]):
            emoji = NUMBER_EMOJIS[i] if i < len(NUMBER_EMOJIS) else str(i + 1)
            button = discord.ui.Button(
                label=choice_text[:80],
                style=discord.ButtonStyle.secondary,
                custom_id=f"trivia_choice_{i}",
                emoji=emoji,
            )
            button.callback = self._make_callback(i, button)
            self.add_item(button)

    def _make_callback(self, index: int, button: discord.ui.Button):
        async def callback(interaction: discord.Interaction) -> None:
            if self.answered:
                await interaction.response.send_message(
                    "This trivia question has already been answered!", ephemeral=True
                )
                return

            self.answered = True
            is_correct = index == self.correct_index
            self.correct_user = interaction.user.id

            # Update all buttons to show correct/incorrect
            for item in self.children:
                if isinstance(item, discord.ui.Button) and item.custom_id.startswith("trivia_choice_"):
                    btn_idx = int(item.custom_id.replace("trivia_choice_", ""))
                    if btn_idx == self.correct_index:
                        item.style = discord.ButtonStyle.success
                        item.disabled = True
                    else:
                        item.style = discord.ButtonStyle.danger
                        item.disabled = True
                        if btn_idx == index:
                            pass  # This button was the wrong answer chosen by user

            if is_correct:
                reward = 5
                if self.cookie_store:
                    new_balance = self.cookie_store.add_cookies(
                        self.guild_id, interaction.user.id, reward, "trivia_correct"
                    )
                else:
                    new_balance = reward
                content = (
                    f"✅ **Correct!** +{reward} cookies 🍪\n"
                    f"Answer: `{self.choices[self.correct_index]}`\n"
                    f"Balance: **{new_balance}** cookies"
                )
            else:
                wrong_answer = self.choices[index]
                content = (
                    f"❌ Wrong! The correct answer was **{self.choices[self.correct_index]}**\n"
                    f"You picked: `{wrong_answer}`"
                )

            embed = discord.Embed(
                title="🧠 Trivia Challenge",
                description=f"**Q:** {self.question}\n\n{content}",
                color=discord.Color.green() if is_correct else discord.Color.red(),
            )
            if not is_correct:
                correct_user = self.correct_user
                # Let the first correct answer user claim the reward
                if correct_user and correct_user != interaction.user.id:
                    embed.add_field(
                        name="💡 First Answer",
                        value=f"<@{correct_user}> got it right first!",
                        inline=False,
                    )

            await interaction.response.edit_message(view=self, embed=embed)

        return callback


class GuessTheNumberView(discord.ui.View):
    """Interactive number guessing game with buttons for hints."""

    def __init__(self, target_user: int | None = None, timeout: float = 120.0) -> None:
        super().__init__(timeout=timeout)
        self.target = random.randint(1, 100)  # nosec B311
        self.attempts = 0
        self.correct_user: int | None = None
        self.solved = False

    @discord.ui.button(label="1-25", style=discord.ButtonStyle.primary, custom_id="range_1_25")
    async def range_low(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._check_guess(interaction, 1, 25)

    @discord.ui.button(label="26-50", style=discord.ButtonStyle.primary, custom_id="range_26_50")
    async def range_mid_low(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._check_guess(interaction, 26, 50)

    @discord.ui.button(label="51-75", style=discord.ButtonStyle.primary, custom_id="range_51_75")
    async def range_mid(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._check_guess(interaction, 51, 75)

    @discord.ui.button(label="76-100", style=discord.ButtonStyle.primary, custom_id="range_76_100")
    async def range_high(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._check_guess(interaction, 76, 100)

    async def _check_guess(self, interaction: discord.Interaction, low: int, high: int) -> None:
        if self.solved:
            await interaction.response.send_message("Game already solved!", ephemeral=True)
            return
        self.attempts += 1
        if low <= self.target <= high:
            self.solved = True
            self.correct_user = interaction.user.id
            embed = discord.Embed(
                title="🎉 Correct!",
                description=f"The number was **{self.target}**.\nGuessed by {interaction.user.mention} in {self.attempts} attempt(s).",
                color=discord.Color.gold(),
            )
            await interaction.response.send_message(embed=embed, view=None)
        elif self.target < low:
            hint = f"Too high! The number is below {low}."
            await interaction.response.send_message(hint, ephemeral=True)
        elif self.target > high:
            hint = f"Too low! The number is above {high}."
            await interaction.response.send_message(hint, ephemeral=True)
        else:
            hint = "Close! Try another range."
            await interaction.response.send_message(hint, ephemeral=True)


class RockPaperScissorsView(discord.ui.View):
    """Interactive RPS game against the bot with buttons."""

    def __init__(self, challenger_id: int, timeout: float = 60.0) -> None:
        super().__init__(timeout=timeout)
        self.challenger_id = challenger_id
        self.choices = ["rock", "paper", "scissors"]
        self.emojis = {"rock": "✊", "paper": "✋", "scissors": "✌️"}

    @discord.ui.button(emoji="✊", label="Rock", style=discord.ButtonStyle.primary, custom_id="rps_rock")
    async def rock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play(interaction, "rock")

    @discord.ui.button(emoji="✋", label="Paper", style=discord.ButtonStyle.primary, custom_id="rps_paper")
    async def paper(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play(interaction, "paper")

    @discord.ui.button(emoji="✌️", label="Scissors", style=discord.ButtonStyle.primary, custom_id="rps_scissors")
    async def scissors(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play(interaction, "scissors")

    async def _play(self, interaction: discord.Interaction, player_choice: str) -> None:
        if interaction.user.id != self.challenger_id:
            await interaction.response.send_message("Only the challenger can play!", ephemeral=True)
            return

        bot_choice = random.choice(self.choices)  # nosec B311
        beats = {"rock": "scissors", "paper": "rock", "scissors": "paper"}

        if player_choice == bot_choice:
            result = "Tie!"
            color = discord.Color.gold()
        elif beats[player_choice] == bot_choice:
            result = "You win!"
            color = discord.Color.green()
        else:
            result = "Bot wins!"
            color = discord.Color.red()

        embed = discord.Embed(
            title="🪨📄✂️ Rock Paper Scissors",
            color=color,
        )
        embed.add_field(name="You", value=f"{self.emojis[player_choice]} {player_choice.title()}", inline=True)
        embed.add_field(name="Bot", value=f"{self.emojis[bot_choice]} {bot_choice.title()}", inline=True)
        embed.add_field(name="Result", value=result, inline=False)

        await interaction.response.send_message(embed=embed, view=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.challenger_id:
            await interaction.response.send_message(
                "This game was started by someone else.", ephemeral=True
            )
            return False
        return True
