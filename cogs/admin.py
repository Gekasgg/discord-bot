import discord
from discord import app_commands
from discord.ext import commands


class AdminCommands(commands.Cog):
    """Справочный модуль бота (вся настройка вынесена в Веб-Панель /сайт)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="help",
        description="Справка по командам сервера (ранг, топ и панель управления)"
    )
    async def cmd_help(self, interaction: discord.Interaction):
        """Компактная справка по командам."""
        embed = discord.Embed(
            title="📖 Команды сервера",
            description="Основные команды для участников и администрации сервера:",
            color=discord.Color.blurple()
        )
        embed.add_field(
            name="⭐ Уровни и Активность (Для всех участников)",
            value=(
                "`/ранг` (или `/rank`, `!ранг`) — ваша карточка уровня, опыта и места в топе\n"
                "`/топ` (или `/leaderboard`, `!топ`) — таблица Топ-10 самых активных участников сервера"
            ),
            inline=False
        )
        embed.add_field(
            name="🌐 Управление ботом (Только для Администраторов)",
            value=(
                "`/сайт` (или `/dashboard`, `!сайт`) — **открыть Веб-Панель управления сервером в браузере**\n"
                "*Все настройки логов, автороли, рангов, тикетов, голосовых комнат, розыгрышей и очистки чата производятся на сайте!*"
            ),
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCommands(bot))
