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
        logger.info("Постоянные UI Views (кнопки тикетов и войса) зарегистрированы.")

        # Загрузка когов
        extensions = [
            "cogs.logging",
            "cogs.tickets",
            "cogs.voice",
            "cogs.admin",
            "cogs.levels"
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

        # Очистка локальных дубликатов команд на серверах
        for guild in self.guilds:
            try:
                self.tree.clear_commands(guild=guild)
                await self.tree.sync(guild=guild)
                logger.info(f"🧹 Очищены локальные дубликаты команд на сервере '{guild.name}' (ID: {guild.id})")
            except Exception as e:
                logger.error(f"Не удалось очистить дубликаты для {guild.name}: {e}")

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
    """Синхронизация команд вручную с удалением дубликатов через !sync"""
    msg = await ctx.send("🔄 Удаляю дубликаты и синхронизирую слэш-команды...")
    try:
        # Очищаем команды гильдии, чтобы они не двоились с глобальными
        bot.tree.clear_commands(guild=ctx.guild)
        await bot.tree.sync(guild=ctx.guild)
        # Синхронизируем глобальные команды
        synced = await bot.tree.sync()
        await msg.edit(content=(
            f"✅ **Дубликаты успешно удалены!**\n"
            f"Синхронизировано **{len(synced)}** глобальных слэш-команд.\n\n"
            f"💡 *Если в списке команд они всё ещё отображаются дважды из-за кэша клиента, перезагрузите Discord нажатием `Ctrl + R`.*"
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
