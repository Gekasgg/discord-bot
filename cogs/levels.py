import asyncio
import datetime
import json
import logging
import random
import time
from pathlib import Path
import discord
from discord import app_commands, ui
from discord.ext import commands, tasks
from config import config_manager, DATA_DIR

logger = logging.getLogger("bot.levels")
LEVELS_FILE = DATA_DIR / "levels.json"


def get_xp_for_next_level(level: int) -> int:
    """Опыт, необходимый для перехода с уровня level на level + 1."""
    return 5 * (level ** 2) + 50 * level + 100


def get_total_xp_for_level(level: int) -> int:
    """Суммарный опыт, необходимый для достижения уровня level с нуля."""
    total = 0
    for l in range(level):
        total += get_xp_for_next_level(l)
    return total


def calculate_level_from_xp(total_xp: int) -> tuple[int, int, int]:
    """
    Рассчитывает текущий уровень и прогресс по суммарному XP.
    Возвращает: (level, current_level_xp, xp_needed_for_next)
    """
    level = 0
    while True:
        needed = get_xp_for_next_level(level)
        if total_xp >= needed:
            total_xp -= needed
            level += 1
        else:
            return level, total_xp, needed


class LevelsManager:
    """Менеджер базы данных уровней с кэшированием в памяти и фоновым сохранением."""

    def __init__(self, file_path: Path = LEVELS_FILE):
        self.file_path = file_path
        self._data: dict[str, dict[str, dict]] = self._load()
        self._is_dirty = False

    def _load(self) -> dict:
        if not self.file_path.exists():
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки {self.file_path}: {e}")
            return {}

    def save(self):
        """Атомарное сохранение данных на диск."""
        try:
            temp_file = self.file_path.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            temp_file.replace(self.file_path)
            self._is_dirty = False
        except Exception as e:
            logger.error(f"Ошибка при сохранении {self.file_path}: {e}")

    def get_user_data(self, guild_id: int, user_id: int) -> dict:
        gid = str(guild_id)
        uid = str(user_id)
        if gid not in self._data:
            self._data[gid] = {}
        if uid not in self._data[gid]:
            self._data[gid][uid] = {
                "xp": 0,
                "level": 0,
                "messages": 0,
                "voice_seconds": 0
            }
            self._is_dirty = True
        return self._data[gid][uid]

    def add_xp(self, guild_id: int, user_id: int, amount: int, inc_message: bool = False, inc_voice: int = 0) -> tuple[int, int, bool]:
        """
        Добавляет опыт пользователю.
        Возвращает: (old_level, new_level, is_level_up)
        """
        user_data = self.get_user_data(guild_id, user_id)
        old_level = user_data["level"]
        user_data["xp"] = max(0, user_data.get("xp", 0) + amount)

        if inc_message:
            user_data["messages"] = user_data.get("messages", 0) + 1
        if inc_voice > 0:
            user_data["voice_seconds"] = user_data.get("voice_seconds", 0) + inc_voice

        new_level, _, _ = calculate_level_from_xp(user_data["xp"])
        user_data["level"] = new_level
        self._is_dirty = True

        return old_level, new_level, (new_level > old_level)

    def set_xp(self, guild_id: int, user_id: int, total_xp: int) -> tuple[int, int]:
        user_data = self.get_user_data(guild_id, user_id)
        old_level = user_data["level"]
        user_data["xp"] = max(0, total_xp)
        new_level, _, _ = calculate_level_from_xp(user_data["xp"])
        user_data["level"] = new_level
        self._is_dirty = True
        return old_level, new_level

    def reset_user(self, guild_id: int, user_id: int):
        gid = str(guild_id)
        uid = str(user_id)
        if gid in self._data and uid in self._data[gid]:
            del self._data[gid][uid]
            self._is_dirty = True

    def reset_guild(self, guild_id: int):
        gid = str(guild_id)
        if gid in self._data:
            self._data[gid] = {}
            self._is_dirty = True

    def get_leaderboard(self, guild_id: int, limit: int = 10) -> list[tuple[int, dict]]:
        gid = str(guild_id)
        guild_data = self._data.get(gid, {})
        # Сортировка по общему опыту (XP) по убыванию
        sorted_users = sorted(
            [(int(uid), data) for uid, data in guild_data.items()],
            key=lambda x: x[1].get("xp", 0),
            reverse=True
        )
        return sorted_users[:limit]

    def get_user_rank(self, guild_id: int, user_id: int) -> tuple[int, int]:
        """Возвращает (место в топе, общее количество участников в базе)."""
        gid = str(guild_id)
        guild_data = self._data.get(gid, {})
        sorted_users = sorted(
            [(int(uid), data.get("xp", 0)) for uid, data in guild_data.items()],
            key=lambda x: x[1],
            reverse=True
        )
        total = len(sorted_users)
        for rank, (uid, _) in enumerate(sorted_users, start=1):
            if uid == user_id:
                return rank, total
        return total + 1, total + 1


levels_manager = LevelsManager()


def make_progress_bar(current: int, total: int, length: int = 12) -> str:
    """Генерирует аккуратную полоску прогресса [██████░░░░░░]."""
    if total <= 0:
        percent = 1.0
    else:
        percent = max(0.0, min(1.0, current / total))
    filled = int(round(length * percent))
    empty = length - filled
    return "█" * filled + "░" * empty


class Leveling(commands.Cog):
    """Ког системы уровней, опыта за активность и наград ролями."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Кулдаун опыта сообщений: {(guild_id, user_id): timestamp}
        self._message_cooldowns: dict[tuple[int, int], float] = {}
        # Запуск фоновых задач
        self.save_data_loop.start()
        self.voice_xp_loop.start()

    def cog_unload(self):
        self.save_data_loop.cancel()
        self.voice_xp_loop.cancel()
        levels_manager.save()

    @tasks.loop(seconds=30.0)
    async def save_data_loop(self):
        """Периодическое сбрасывание изменений уровней на диск."""
        if levels_manager._is_dirty:
            levels_manager.save()

    @tasks.loop(seconds=60.0)
    async def voice_xp_loop(self):
        """Начисление опыта участникам за активное общение в голосовых каналах."""
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            settings = config_manager.get_guild(guild.id)
            if not settings.get("levels_enabled", True):
                continue

            for vc in guild.voice_channels:
                # Игнорируем AFK-канал сервера
                if guild.afk_channel and vc.id == guild.afk_channel.id:
                    continue

                # Фильтруем реальных участников (не ботов)
                active_members = [
                    m for m in vc.members
                    if not m.bot and not m.voice.self_deaf and not m.voice.deaf
                ]

                # Опыт начисляется, если в голосовом канале общаются как минимум 2 человека
                if len(active_members) < 2:
                    continue

                for member in active_members:
                    # 10-15 XP за минуту в войсе
                    voice_xp = random.randint(10, 15)
                    old_lvl, new_lvl, is_lvl_up = levels_manager.add_xp(
                        guild_id=guild.id,
                        user_id=member.id,
                        amount=voice_xp,
                        inc_voice=60
                    )

                    if is_lvl_up:
                        await self.handle_level_up(guild, member, new_lvl, context_channel=None)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Обработка сообщений и начисление опыта."""
        if message.author.bot or not message.guild:
            return

        # Игнорируем сообщения короче 3 символов или начинающиеся с префикса команд
        content = message.content.strip()
        if len(content) < 3 or content.startswith(self.bot.command_prefix):
            return

        guild = message.guild
        member = message.author
        settings = config_manager.get_guild(guild.id)
        if not settings.get("levels_enabled", True):
            return

        now = time.time()
        cd_key = (guild.id, member.id)
        last_time = self._message_cooldowns.get(cd_key, 0)

        # Кулдаун 60 секунд между начислением опыта за сообщения
        if now - last_time < 60:
            # Инкрементируем только количество сообщений без добавления XP
            user_data = levels_manager.get_user_data(guild.id, member.id)
            user_data["messages"] = user_data.get("messages", 0) + 1
            levels_manager._is_dirty = True
            return

        self._message_cooldowns[cd_key] = now
        xp_gain = random.randint(15, 25)

        old_lvl, new_lvl, is_lvl_up = levels_manager.add_xp(
            guild_id=guild.id,
            user_id=member.id,
            amount=xp_gain,
            inc_message=True
        )

        if is_lvl_up:
            await self.handle_level_up(guild, member, new_lvl, context_channel=message.channel)

    async def handle_level_up(self, guild: discord.Guild, member: discord.Member, new_level: int, context_channel: discord.TextChannel | None):
        """Оповещение о повышении уровня и выдача роли-награды."""
        settings = config_manager.get_guild(guild.id)
        level_roles = settings.get("level_roles", {})

        # Проверка и выдача роли за уровень
        role_reward = None
        role_id = level_roles.get(str(new_level))
        if role_id:
            role = guild.get_role(int(role_id))
            if role:
                try:
                    if guild.me.top_role > role:
                        await member.add_roles(role, reason=f"Награда за достижение {new_level} уровня")
                        role_reward = role
                    else:
                        logger.warning(f"Роль бота ниже роли награды {role.name} на сервере {guild.name}")
                except Exception as e:
                    logger.error(f"Ошибка при выдаче роли {role.name} пользователю {member}: {e}")

        # Поиск канала для отправки оповещения
        target_channel = context_channel
        level_up_cid = settings.get("level_up_channel_id")
        if level_up_cid:
            cfg_channel = guild.get_channel(int(level_up_cid))
            if isinstance(cfg_channel, discord.TextChannel):
                target_channel = cfg_channel

        if not target_channel:
            # Если канал не определен (например, апнул в войсе), ищем дефолтный системный
            target_channel = guild.system_channel

        if target_channel and target_channel.permissions_for(guild.me).send_messages:
            embed = discord.Embed(
                title="🎉 Повышение уровня!",
                description=f"Поздравляем, {member.mention}! Твоя активность на сервере принесла плоды — ты достиг **{new_level} уровня**!",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_thumbnail(url=member.display_avatar.url)

            user_data = levels_manager.get_user_data(guild.id, member.id)
            lvl, cur_xp, next_xp = calculate_level_from_xp(user_data["xp"])
            bar = make_progress_bar(cur_xp, next_xp, length=12)
            embed.add_field(name="Прогресс уровня", value=f"`{bar}` `{cur_xp} / {next_xp} XP`", inline=False)

            if role_reward:
                embed.add_field(name="🎁 Новая роль", value=f"Тебе присвоена роль: {role_reward.mention}", inline=False)

            embed.set_footer(text=f"Всего сообщений: {user_data.get('messages', 0)} | Используйте /rank")

            try:
                await target_channel.send(content=member.mention, embed=embed)
            except Exception as e:
                logger.error(f"Не удалось отправить оповещение о левелапе: {e}")

    # ==========================================
    # ПОЛЬЗОВАТЕЛЬСКИЕ СЛЭШ-КОМАНДЫ
    # ==========================================

    @app_commands.command(
        name="rank",
        description="Посмотреть свой текущий уровень, опыт и ранг активности на сервере"
    )
    @app_commands.describe(user="Пользователь, чей ранг вы хотите посмотреть (по умолчанию — ваш)")
    async def cmd_rank(self, interaction: discord.Interaction, user: discord.Member | None = None):
        target = user or interaction.user
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        user_data = levels_manager.get_user_data(guild.id, target.id)
        total_xp = user_data.get("xp", 0)
        level, cur_xp, next_xp = calculate_level_from_xp(total_xp)
        rank, total_ranked = levels_manager.get_user_rank(guild.id, target.id)

        bar = make_progress_bar(cur_xp, next_xp, length=14)
        percent = int(round((cur_xp / next_xp) * 100)) if next_xp > 0 else 100

        # Время в голосовых каналах
        voice_secs = user_data.get("voice_seconds", 0)
        v_hours = voice_secs // 3600
        v_mins = (voice_secs % 3600) // 60

        embed = discord.Embed(
            title=f"📊 Ранг активности — {target.display_name}",
            color=target.color if target.color != discord.Color.default() else discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        embed.add_field(name="🏆 Место в топе", value=f"**#{rank}** из {total_ranked}", inline=True)
        embed.add_field(name="⭐ Уровень", value=f"**{level}**", inline=True)
        embed.add_field(name="✨ Всего XP", value=f"**{total_xp:,}**", inline=True)

        embed.add_field(
            name=f"Прогресс до {level + 1} уровня ({percent}%)",
            value=f"`{bar}` `{cur_xp:,} / {next_xp:,} XP`",
            inline=False
        )

        embed.add_field(name="💬 Сообщений", value=f"{user_data.get('messages', 0):,}", inline=True)
        embed.add_field(name="🎙️ В войсе", value=f"{v_hours} ч {v_mins} мин", inline=True)

        embed.set_footer(text=f"Сервер: {guild.name} | Пишите сообщения и общайтесь в войсе для роста!")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="leaderboard",
        description="Таблица лидеров сервера по уровням и активности"
    )
    async def cmd_leaderboard(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        top_users = levels_manager.get_leaderboard(guild.id, limit=10)
        if not top_users:
            await interaction.response.send_message(
                "📜 На сервере пока нет данных об активности. Пишите сообщения и общайтесь в войсе, чтобы попасть в топ!",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"🏆 Доска лидеров активности — {guild.name}",
            description="Топ-10 самых активных участников сервера по опыту и уровням:\n",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}

        lines = []
        for rank, (uid, data) in enumerate(top_users, start=1):
            member = guild.get_member(uid)
            mention_str = member.mention if member else f"`User ID: {uid}`"
            medal = medals.get(rank, f"`#{rank}`")
            total_xp = data.get("xp", 0)
            level = data.get("level", 0)
            msgs = data.get("messages", 0)

            lines.append(
                f"{medal} **{mention_str}** — **Уровень {level}**\n"
                f"   └ ✨ `{total_xp:,} XP` | 💬 `{msgs:,} сообщ.`"
            )

        embed.description = "\n\n".join(lines)
        embed.set_footer(text="Позиции обновляются в реальном времени • Используйте /rank")
        await interaction.response.send_message(embed=embed)

    # ==========================================
    # АДМИНИСТРАТИВНЫЕ СЛЭШ-КОМАНДЫ
    # ==========================================

    @app_commands.command(
        name="set-level-channel",
        description="Настроить отдельный канал для оповещений о повышении уровня"
    )
    @app_commands.describe(channel="Текстовый канал для поздравлений (оставьте пустым для отправки в текущий)")
    @app_commands.default_permissions(administrator=True)
    async def cmd_set_level_channel(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        guild = interaction.guild
        if channel:
            config_manager.set_guild_value(guild.id, "level_up_channel_id", channel.id)
            embed = discord.Embed(
                title="✅ Канал оповещений установлен",
                description=f"Все поздравления о повышении уровней будут приходить в {channel.mention}.",
                color=discord.Color.green()
            )
        else:
            config_manager.set_guild_value(guild.id, "level_up_channel_id", None)
            embed = discord.Embed(
                title="✅ Настройки обновлены",
                description="Поздравления о повышении уровня будут отправляться в канал, где было написано последнее сообщение.",
                color=discord.Color.blue()
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="set-level-role",
        description="Назначить роль, выдаваемую за достижение определенного уровня"
    )
    @app_commands.describe(
        level="Уровень, за который будет выдаваться роль (например, 5, 10, 20)",
        role="Роль, которая будет выдаваться участнику"
    )
    @app_commands.default_permissions(administrator=True)
    async def cmd_set_level_role(self, interaction: discord.Interaction, level: int, role: discord.Role):
        guild = interaction.guild
        if level < 1:
            await interaction.response.send_message("❌ Уровень должен быть 1 или выше.", ephemeral=True)
            return

        if role.is_default() or role.managed:
            await interaction.response.send_message("❌ Нельзя назначить системную роль или роль интеграции.", ephemeral=True)
            return

        warning = ""
        if guild.me.top_role <= role:
            warning = f"\n\n⚠️ **Внимание:** Роль {role.mention} находится выше или на одном уровне с ролью бота. Поднимите роль бота выше в настройках сервера."

        settings = config_manager.get_guild(guild.id)
        level_roles = settings.get("level_roles", {})
        level_roles[str(level)] = role.id
        config_manager.set_guild_value(guild.id, "level_roles", level_roles)

        embed = discord.Embed(
            title="✅ Награда за уровень настроена",
            description=f"При достижении **{level} уровня** участники будут получать роль {role.mention}.{warning}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="remove-level-role",
        description="Удалить роль-награду за определенный уровень"
    )
    @app_commands.describe(level="Уровень, с которого нужно снять награду ролью")
    @app_commands.default_permissions(administrator=True)
    async def cmd_remove_level_role(self, interaction: discord.Interaction, level: int):
        guild = interaction.guild
        settings = config_manager.get_guild(guild.id)
        level_roles = settings.get("level_roles", {})

        if str(level) in level_roles:
            del level_roles[str(level)]
            config_manager.set_guild_value(guild.id, "level_roles", level_roles)
            await interaction.response.send_message(f"✅ Награда за **{level} уровень** успешно удалена.", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ Для **{level} уровня** не было настроено роли-награды.", ephemeral=True)

    @app_commands.command(
        name="level-roles",
        description="Посмотреть все настроенные на сервере роли за уровни"
    )
    async def cmd_level_roles(self, interaction: discord.Interaction):
        guild = interaction.guild
        settings = config_manager.get_guild(guild.id)
        level_roles = settings.get("level_roles", {})

        if not level_roles:
            await interaction.response.send_message("ℹ️ На этом сервере еще не настроены роли за уровни. Используйте `/set-level-role`.", ephemeral=True)
            return

        sorted_levels = sorted([(int(lvl), rid) for lvl, rid in level_roles.items()], key=lambda x: x[0])
        lines = []
        for lvl, rid in sorted_levels:
            role = guild.get_role(rid)
            role_str = role.mention if role else f"`ID: {rid} (Удалена)`"
            lines.append(f"⭐ **Уровень {lvl}** ➔ {role_str}")

        embed = discord.Embed(
            title=f"🎖️ Роли за уровни — {guild.name}",
            description="\n".join(lines),
            color=discord.Color.blue()
        )
        embed.set_footer(text="Роли выдаются автоматически при повышении уровня")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="add-xp",
        description="Выдать опыт пользователю вручную"
    )
    @app_commands.describe(user="Пользователь", amount="Количество добавляемого опыта")
    @app_commands.default_permissions(administrator=True)
    async def cmd_add_xp(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message("❌ Количество опыта должно быть больше нуля.", ephemeral=True)
            return

        old_lvl, new_lvl, is_lvl_up = levels_manager.add_xp(interaction.guild_id, user.id, amount)
        user_data = levels_manager.get_user_data(interaction.guild_id, user.id)

        msg = f"✅ Пользователю {user.mention} добавлено **+{amount:,} XP**!\nТекущий баланс: **{user_data['xp']:,} XP** (Уровень {new_lvl})."
        if is_lvl_up:
            msg += f"\n🎉 **Уровень повышен с {old_lvl} до {new_lvl}!**"
            await self.handle_level_up(interaction.guild, user, new_lvl, context_channel=interaction.channel)

        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(
        name="remove-xp",
        description="Списать опыт у пользователя"
    )
    @app_commands.describe(user="Пользователь", amount="Количество списываемого опыта")
    @app_commands.default_permissions(administrator=True)
    async def cmd_remove_xp(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message("❌ Количество опыта должно быть больше нуля.", ephemeral=True)
            return

        user_data = levels_manager.get_user_data(interaction.guild_id, user.id)
        new_xp = max(0, user_data.get("xp", 0) - amount)
        old_lvl, new_lvl = levels_manager.set_xp(interaction.guild_id, user.id, new_xp)

        await interaction.response.send_message(
            f"✅ У пользователя {user.mention} списано **-{amount:,} XP**.\nНовый баланс: **{new_xp:,} XP** (Уровень {new_lvl}).",
            ephemeral=True
        )

    @app_commands.command(
        name="reset-levels",
        description="Сбросить уровни и опыт пользователю или всему серверу"
    )
    @app_commands.describe(
        user="Пользователь для сброса (оставьте пустым для сброса всего сервера)",
        confirm="Введите ДА для подтверждения сброса всего сервера"
    )
    @app_commands.default_permissions(administrator=True)
    async def cmd_reset_levels(self, interaction: discord.Interaction, user: discord.Member | None = None, confirm: str | None = None):
        guild = interaction.guild
        if user:
            levels_manager.reset_user(guild.id, user.id)
            await interaction.response.send_message(f"✅ Уровень и опыт для {user.mention} полностью сброшены.", ephemeral=True)
            return

        if confirm != "ДА":
            await interaction.response.send_message(
                "⚠️ **Внимание:** Вы собираетесь сбросить опыт и уровни **ВСЕХ** участников сервера!\n"
                "Чтобы подтвердить это действие, вызовите команду с параметром `confirm: ДА`.",
                ephemeral=True
            )
            return

        levels_manager.reset_guild(guild.id)
        await interaction.response.send_message(f"🚨 **Все уровни и опыт участников сервера {guild.name} были успешно сброшены.**", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
