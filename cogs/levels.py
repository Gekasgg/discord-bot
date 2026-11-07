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

    def get_leaderboard(
        self,
        guild_id: int,
        limit: int = 10,
        excluded_user_ids: set[int] | None = None
    ) -> list[tuple[int, dict]]:
        gid = str(guild_id)
        guild_data = self._data.get(gid, {})
        excluded = excluded_user_ids or set()
        # Сортировка по общему опыту (XP) по убыванию с фильтрацией скрытых ролей
        sorted_users = sorted(
            [(int(uid), data) for uid, data in guild_data.items() if int(uid) not in excluded],
            key=lambda x: x[1].get("xp", 0),
            reverse=True
        )
        return sorted_users[:limit]

    def get_user_rank(
        self,
        guild_id: int,
        user_id: int,
        excluded_user_ids: set[int] | None = None
    ) -> tuple[int, int]:
        """Возвращает (место в топе, общее количество участников в базе)."""
        gid = str(guild_id)
        guild_data = self._data.get(gid, {})
        excluded = excluded_user_ids or set()
        sorted_users = sorted(
            [(int(uid), data.get("xp", 0)) for uid, data in guild_data.items() if int(uid) not in excluded],
            key=lambda x: x[1],
            reverse=True
        )
        total = len(sorted_users)
        for rank, (uid, _) in enumerate(sorted_users, start=1):
            if uid == user_id:
                return rank, total
        return total + 1, total + 1


levels_manager = LevelsManager()


def get_excluded_top_user_ids(guild: discord.Guild) -> set[int]:
    """Возвращает множество ID участников сервера, имеющих роли, скрытые из топа."""
    settings = config_manager.get_guild(guild.id)
    raw_roles = settings.get("level_ignored_roles", []) or []
    ignored_role_ids: set[int] = set()
    for r in raw_roles:
        try:
            ignored_role_ids.add(int(r))
        except (ValueError, TypeError):
            continue
    if not ignored_role_ids:
        return set()

    excluded: set[int] = set()
    for member in guild.members:
        if any(role.id in ignored_role_ids for role in member.roles):
            excluded.add(member.id)
    return excluded


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
        """Обработка сообщений, текстовых команд ранга и начисление опыта."""
        if message.author.bot or not message.guild:
            return

        content = message.content.strip()
        if not content:
            return

        guild = message.guild
        member = message.author
        lower_content = content.lower()
        parts = lower_content.split()
        cmd_word = parts[0] if parts else ""

        # Поддержка вызова ранга через текстовый чат (!ранг, !rank, /ранг, /rank, !уровень, !лвл)
        if cmd_word in ("!rank", "!ранг", "/rank", "/ранг", "!уровень", "!lvl", "!лвл"):
            target = message.mentions[0] if message.mentions else member
            embed = self._build_rank_embed(guild, target)
            try:
                await message.reply(embed=embed, mention_author=False)
            except Exception:
                try:
                    await message.channel.send(embed=embed)
                except Exception:
                    pass
            return

        # Поддержка вызова таблицы лидеров через текстовый чат (!топ, !top, !лидеры, /топ, /leaderboard)
        if cmd_word in ("!top", "!топ", "!leaderboard", "/leaderboard", "/топ", "!лидеры"):
            embed = self._build_leaderboard_embed(guild)
            try:
                if embed:
                    await message.reply(embed=embed, mention_author=False)
                else:
                    await message.reply(
                        "📜 На сервере пока нет данных об активности. Пишите сообщения и общайтесь в войсе, чтобы попасть в топ!",
                        mention_author=False
                    )
            except Exception:
                pass
            return

        # Игнорируем сообщения короче 3 символов или начинающиеся с префикса команд
        if len(content) < 3 or content.startswith(self.bot.command_prefix):
            return
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

    async def update_member_level_roles(
        self,
        guild: discord.Guild,
        member: discord.Member,
        current_level: int
    ) -> tuple[discord.Role | None, list[discord.Role]]:
        """
        Синхронизирует роли уровней участника в зависимости от текущего уровня и режима (замена старых ролей/накопление).
        Возвращает (добавленная_роль, список_снятых_ролей).
        """
        settings = config_manager.get_guild(guild.id)
        level_roles = settings.get("level_roles", {})
        if not level_roles:
            return None, []

        replace_mode = settings.get("level_roles_replace", True)

        # Сортируем пары (требуемый_уровень, role_id) по возрастанию
        sorted_tiers = sorted(
            [(int(lvl), int(rid)) for lvl, rid in level_roles.items() if str(lvl).isdigit()],
            key=lambda x: x[0]
        )

        all_level_role_ids = {rid for _, rid in sorted_tiers}

        # Определяем наивысшую подходящую роль для текущего уровня
        target_role = None
        target_role_id = None
        for req_level, role_id in sorted_tiers:
            if current_level >= req_level:
                target_role_id = role_id

        if target_role_id:
            target_role = guild.get_role(target_role_id)

        roles_to_add: list[discord.Role] = []
        roles_to_remove: list[discord.Role] = []

        if replace_mode:
            # РЕЖИМ РАНГОВ (активна только текущая роль диапазона, предыдущие снимаются)
            if target_role:
                if target_role not in member.roles:
                    roles_to_add.append(target_role)

                # Снимаем любые другие роли уровней, которые есть у участника
                for r in member.roles:
                    if r.id in all_level_role_ids and r.id != target_role.id:
                        roles_to_remove.append(r)
            else:
                # Уровень ниже минимального настроенного — снимаем все роли уровней, если они есть
                for r in member.roles:
                    if r.id in all_level_role_ids:
                        roles_to_remove.append(r)
        else:
            # НАКОПИТЕЛЬНЫЙ РЕЖИМ (сохранять все ранее полученные роли)
            for req_level, role_id in sorted_tiers:
                r = guild.get_role(role_id)
                if not r:
                    continue
                if current_level >= req_level:
                    if r not in member.roles:
                        roles_to_add.append(r)
                else:
                    if r in member.roles:
                        roles_to_remove.append(r)

        # Фильтрация по иерархии прав бота
        bot_top = guild.me.top_role
        filtered_add = [r for r in roles_to_add if bot_top > r]
        filtered_remove = [r for r in roles_to_remove if bot_top > r]

        if len(filtered_add) < len(roles_to_add):
            logger.warning(f"Роль бота ниже одной из выдаваемых ролей на сервере {guild.name}")
        if len(filtered_remove) < len(roles_to_remove):
            logger.warning(f"Роль бота ниже одной из снимаемых ролей на сервере {guild.name}")

        added_role = None
        if filtered_add:
            try:
                await member.add_roles(*filtered_add, reason=f"Награда за {current_level} уровень активности")
                added_role = filtered_add[0]
            except Exception as e:
                logger.error(f"Ошибка при выдаче ролей {filtered_add} участнику {member}: {e}")

        if filtered_remove:
            try:
                await member.remove_roles(*filtered_remove, reason=f"Замена ранга активности на {current_level} уровень")
            except Exception as e:
                logger.error(f"Ошибка при снятии предыдущих ролей {filtered_remove} у {member}: {e}")

        return added_role, filtered_remove

    async def handle_level_up(self, guild: discord.Guild, member: discord.Member, new_level: int, context_channel: discord.TextChannel | None):
        """Оповещение о повышении уровня и выдача роли-награды."""
        settings = config_manager.get_guild(guild.id)

        # Обновление и синхронизация ролей за уровень (с автоматическим снятием старых ролей)
        role_reward, removed_roles = await self.update_member_level_roles(guild, member, new_level)

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
                if removed_roles:
                    rem_str = ", ".join(r.mention for r in removed_roles)
                    embed.add_field(
                        name="🎖️ Новый ранг!",
                        value=f"Тебе присвоена роль: {role_reward.mention}\n*(Предыдущая роль {rem_str} снята)*",
                        inline=False
                    )
                else:
                    embed.add_field(name="🎁 Новая роль", value=f"Тебе присвоена роль: {role_reward.mention}", inline=False)

            embed.set_footer(text=f"Всего сообщений: {user_data.get('messages', 0)} | Используйте /rank")

            try:
                await target_channel.send(content=member.mention, embed=embed)
            except Exception as e:
                logger.error(f"Не удалось отправить оповещение о левелапе: {e}")

    # ==========================================
    # ПОЛЬЗОВАТЕЛЬСКИЕ СЛЭШ-КОМАНДЫ
    # ==========================================

    def _build_rank_embed(self, guild: discord.Guild, target: discord.Member | discord.User) -> discord.Embed:
        """Формирует красивую карточку ранга для слэш- и текстовых команд."""
        user_data = levels_manager.get_user_data(guild.id, target.id)
        total_xp = user_data.get("xp", 0)
        level, cur_xp, next_xp = calculate_level_from_xp(total_xp)
        excluded_ids = get_excluded_top_user_ids(guild)
        is_excluded = target.id in excluded_ids
        rank, total_ranked = levels_manager.get_user_rank(guild.id, target.id, excluded_user_ids=excluded_ids)

        bar = make_progress_bar(cur_xp, next_xp, length=14)
        percent = int(round((cur_xp / next_xp) * 100)) if next_xp > 0 else 100

        voice_secs = user_data.get("voice_seconds", 0)
        v_hours = voice_secs // 3600
        v_mins = (voice_secs % 3600) // 60

        target_color = getattr(target, "color", discord.Color.default())
        embed = discord.Embed(
            title=f"📊 Ранг активности — {target.display_name}",
            color=target_color if target_color != discord.Color.default() else discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        rank_value = "Скрыт из /топ" if is_excluded else f"**#{rank}** из {total_ranked}"
        embed.add_field(name="🏆 Место в топе", value=rank_value, inline=True)
        embed.add_field(name="⭐ Уровень", value=f"**{level}**", inline=True)
        embed.add_field(name="✨ Всего XP", value=f"**{total_xp:,}**", inline=True)

        embed.add_field(
            name=f"Прогресс до {level + 1} уровня ({percent}%)",
            value=f"`{bar}` `{cur_xp:,} / {next_xp:,} XP`",
            inline=False
        )

        embed.add_field(name="💬 Сообщений", value=f"{user_data.get('messages', 0):,}", inline=True)
        embed.add_field(name="🎙️ В войсе", value=f"{v_hours} ч {v_mins} мин", inline=True)

        embed.set_footer(text=f"Сервер: {guild.name} | Команды: /rank, /ранг, !ранг")
        return embed

    def _build_leaderboard_embed(self, guild: discord.Guild) -> discord.Embed | None:
        """Формирует таблицу лидеров сервера."""
        excluded_ids = get_excluded_top_user_ids(guild)
        top_users = levels_manager.get_leaderboard(guild.id, limit=10, excluded_user_ids=excluded_ids)
        if not top_users:
            return None

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
        embed.set_footer(text="Позиции обновляются в реальном времени • Используйте /rank или /ранг")
        return embed

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

        embed = self._build_rank_embed(guild, target)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="ранг",
        description="Посмотреть свой текущий уровень, опыт и ранг активности на сервере"
    )
    @app_commands.describe(user="Пользователь, чей ранг вы хотите посмотреть (по умолчанию — ваш)")
    async def cmd_rank_ru(self, interaction: discord.Interaction, user: discord.Member | None = None):
        target = user or interaction.user
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        embed = self._build_rank_embed(guild, target)
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

        embed = self._build_leaderboard_embed(guild)
        if not embed:
            await interaction.response.send_message(
                "📜 На сервере пока нет данных об активности. Пишите сообщения и общайтесь в войсе, чтобы попасть в топ!",
                ephemeral=True
            )
            return
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="топ",
        description="Таблица лидеров сервера по уровням и активности"
    )
    async def cmd_top_ru(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        embed = self._build_leaderboard_embed(guild)
        if not embed:
            await interaction.response.send_message(
                "📜 На сервере пока нет данных об активности. Пишите сообщения и общайтесь в войсе, чтобы попасть в топ!",
                ephemeral=True
            )
            return
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
