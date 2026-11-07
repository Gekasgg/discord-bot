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
            "cogs.giveaways",
            "cogs.dashboard"
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

    async def ensure_member_command_permissions(self, guild: discord.Guild) -> list[str]:
        """
        Автоматически проверяет и восстанавливает право 'Использовать команды приложений'
        (use_application_commands) у @everyone, ролей участников и в текстовых каналах,
        чтобы обычные игроки могли пользоваться /rank, /ранг, /leaderboard и другими командами.
        """
        fixed_items = []
        if not guild.me:
            return fixed_items

        # 1. Проверяем роль @everyone
        if guild.me.guild_permissions.manage_roles:
            try:
                if not guild.default_role.permissions.use_application_commands:
                    perms = guild.default_role.permissions
                    perms.update(use_application_commands=True)
                    await guild.default_role.edit(
                        permissions=perms,
                        reason="Авто-восстановление доступа участников к слэш-командам (/rank)"
                    )
                    fixed_items.append("Роль @everyone")
                    logger.info(f"🔧 Включено право 'Использовать команды приложений' для @everyone на сервере '{guild.name}'")
            except Exception as e:
                logger.warning(f"Не удалось обновить права @everyone на '{guild.name}': {e}")

            # 2. Проверяем остальные не-админские роли, где могло быть выключено право
            for role in guild.roles:
                if role.is_default() or role.managed or role.permissions.administrator:
                    continue
                if guild.me.top_role > role and not role.permissions.use_application_commands:
                    try:
                        r_perms = role.permissions
                        r_perms.update(use_application_commands=True)
                        await role.edit(
                            permissions=r_perms,
                            reason="Авто-восстановление доступа к слэш-командам (/rank)"
                        )
                        fixed_items.append(f"Роль @{role.name}")
                    except Exception:
                        pass

        # 3. Проверяем категории и текстовые каналы, где право могло быть запрещено (❌) в настройках канала
        if guild.me.guild_permissions.manage_channels or guild.me.guild_permissions.administrator:
            all_channels = list(guild.categories) + list(guild.text_channels)
            for ch in all_channels:
                try:
                    for target, overwrite in ch.overwrites.items():
                        if isinstance(target, discord.Role) and overwrite.use_application_commands is False:
                            overwrite.use_application_commands = True
                            await ch.set_permissions(
                                target,
                                overwrite=overwrite,
                                reason="Разблокировка слэш-команд (/rank) для участников в канале"
                            )
                            fixed_items.append(f"Канал #{ch.name} (для @{target.name})")
                            logger.info(f"🔧 Разблокированы слэш-команды в '{ch.name}' для роли '@{target.name}'")
                except Exception as e:
                    logger.debug(f"Не удалось проверить права канала {ch.name}: {e}")

        return fixed_items

    async def on_ready(self):
        logger.info("=" * 50)
        logger.info(f"Бот успешно запущен как: {self.user} (ID: {self.user.id})")
        logger.info(f"Подключен к {len(self.guilds)} серверам.")
        logger.info("=" * 50)

        # Мгновенная регистрация слэш-команд и проверка прав доступа для участников
        for guild in self.guilds:
            try:
                fixed = await self.ensure_member_command_permissions(guild)
                if fixed:
                    logger.info(f"🔧 На сервере '{guild.name}' восстановлен доступ к командам: {', '.join(fixed)}")
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logger.info(f"✅ Мгновенно синхронизировано {len(synced)} слэш-команд на сервере '{guild.name}' (ID: {guild.id})")
            except Exception as e:
                logger.error(f"Не удалось синхронизировать команды для {guild.name}: {e}")

        # Установка статуса активности
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="за сервером | /rank • /ранг"
        )
        await self.change_presence(status=discord.Status.online, activity=activity)


bot = DiscordBot()


@bot.command(name="sync")
@commands.has_permissions(administrator=True)
async def manual_sync(ctx: commands.Context):
    """Мгновенная синхронизация команд и прав на сервере через !sync"""
    msg = await ctx.send("🔄 Мгновенно обновляю слэш-команды и проверяю права доступа участников...")
    try:
        fixed = await bot.ensure_member_command_permissions(ctx.guild)
        # Копируем глобальные команды на текущий сервер для моментального появления в Discord
        bot.tree.copy_global_to(guild=ctx.guild)
        synced_guild = await bot.tree.sync(guild=ctx.guild)
        # Также обновляем глобальные команды
        await bot.tree.sync()

        fixed_str = f"\n🔧 **Автоматически исправлены права доступа в:** {', '.join(fixed)}" if fixed else "\n✅ **Права ролей и каналов для использования команд в полном порядке!**"

        await msg.edit(content=(
            f"✅ **Все слэш-команды успешно зарегистрированы и открыты для участников!**\n\n"
            f"📊 На сервере доступно: **{len(synced_guild)}** команд (включая `/сайт`, `/dashboard`, `/rank`, `/ранг`)."
            f"{fixed_str}\n\n"
            f"💡 *Для открытия веб-панели настроек введите `/сайт` (или `!сайт`).*"
        ))
    except Exception as e:
        await msg.edit(content=f"❌ Ошибка синхронизации: {e}")


@bot.command(name="сайт", aliases=["dashboard", "панель"])
@commands.has_permissions(administrator=True)
async def cmd_site_prefix(ctx: commands.Context):
    """Отправляет администратору персональную ссылку на веб-панель в ЛС."""
    dash_cog = bot.get_cog("WebDashboard")
    if not dash_cog:
        await ctx.send("❌ Модуль веб-панели ещё загружается.")
        return

    url = dash_cog.get_dashboard_url()
    try:
        await ctx.author.send(
            f"🌐 **Ваша персональная ссылка для входа в Веб-Панель управления ботом:**\n{url}\n\n"
            f"*(Не передавайте эту ссылку посторонним)*"
        )
        await ctx.reply("✅ Ссылка на сайт управления ботом отправлена вам в **Личные сообщения**! (Также вы можете использовать слэш-команду `/сайт` или `/dashboard`).", mention_author=False)
    except discord.Forbidden:
        await ctx.reply("⚠️ У вас закрыты личные сообщения. Пожалуйста, введите слэш-команду **`/сайт`** или **`/dashboard`** — бот покажет ссылку скрытым сообщением прямо здесь!", mention_author=False)


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
