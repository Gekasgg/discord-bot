import asyncio
import logging
import sys
from pathlib import Path

# Добавляем директорию бота в путь поиска модулей
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import discord
from discord.ext import commands
import config
from cogs.tickets import TicketLauncherView, TicketControlView
from cogs.voice import VoiceControlView
from cogs.giveaways import GiveawayJoinView

# Настройка красивого вывода логов в консоль
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("discord_bot")


class DiscordBot(commands.Bot):
    def __init__(self):
        # Включаем все необходимые Intents для аудита и участников
        intents = discord.Intents.all()

        super().__init__(
            command_prefix=config.COMMAND_PREFIX,
            intents=intents,
            help_command=None,
            proxy=config.PROXY
        )

    async def setup_hook(self):
        """Асинхронная инициализация при запуске бота."""
        # Регистрация персистентных (постоянных) компонентов интерфейса
        self.add_view(TicketLauncherView())
        self.add_view(TicketControlView())
        self.add_view(VoiceControlView())
        self.add_view(GiveawayJoinView())
        logger.info("Постоянные UI Views (кнопки тикетов, войса и розыгрышей) зарегистрированы.")

        # Загрузка когов
        extensions = [
            "cogs.logging",
            "cogs.tickets",
            "cogs.voice",
            "cogs.admin",
            "cogs.levels",
            "cogs.giveaways"
        ]

        for ext in extensions:
            try:
                await self.load_extension(ext)
                logger.info(f"Успешно загружен модуль: {ext}")
            except Exception as e:
                logger.error(f"Не удалось загрузить модуль {ext}: {e}", exc_info=True)

        # Синхронизация слэш-команд
        try:
            synced = await self.tree.sync()
            logger.info(f"Синхронизировано {len(synced)} слэш-команд.")
        except Exception as e:
            logger.error(f"Ошибка синхронизации слэш-команд: {e}")

    async def on_ready(self):
        logger.info("=" * 50)
        logger.info(f"Бот успешно запущен как: {self.user} (ID: {self.user.id})")
        logger.info(f"Подключен к {len(self.guilds)} серверам.")
        logger.info("=" * 50)

        # Мгновенная регистрация и синхронизация слэш-команд на серверах
        for guild in self.guilds:
            try:
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logger.info(f"✅ Мгновенно синхронизировано {len(synced)} слэш-команд на сервере '{guild.name}' (ID: {guild.id})")
            except Exception as e:
                logger.error(f"Не удалось синхронизировать команды для {guild.name}: {e}")

        # Установка статуса активности
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="за сервером | /help"
        )
        await self.change_presence(status=discord.Status.online, activity=activity)


bot = DiscordBot()


@bot.command(name="sync")
@commands.has_permissions(administrator=True)
async def manual_sync(ctx: commands.Context):
    """Мгновенная синхронизация команд на сервере через !sync"""
    msg = await ctx.send("🔄 Мгновенно обновляю и регистрирую слэш-команды на сервере...")
    try:
        # Копируем глобальные команды на текущий сервер для моментального появления в Discord
        bot.tree.copy_global_to(guild=ctx.guild)
        synced_guild = await bot.tree.sync(guild=ctx.guild)
        # Также обновляем глобальные команды
        synced_global = await bot.tree.sync()

        await msg.edit(content=(
            f"✅ **Все слэш-команды успешно и мгновенно зарегистрированы!**\n\n"
            f"📊 На сервере доступно: **{len(synced_guild)}** команд (включая `/clear` и `/server-config`).\n\n"
            f"💡 *Если при вводе `/` они ещё не появились в списке из-за кэша Discord, нажмите `Ctrl + R` (или перезапустите Discord), чтобы обновить интерфейс.*"
        ))
    except Exception as e:
        await msg.edit(content=f"❌ Ошибка синхронизации: {e}")


async def main():
    token = config.TOKEN
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        print("\n" + "!" * 60)
        print("ОШИБКА: Токен бота не указан!")
        print("Пожалуйста, откройте файл .env и вставьте ваш токен в поле DISCORD_TOKEN.")
        print("Инструкцию по получению токена смотрите в файле README.md")
        print("!" * 60 + "\n")
        sys.exit(1)

    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nБот остановлен пользователем.")
