import asyncio
import datetime
import json
import logging
import random
import re
from pathlib import Path
import discord
from discord import app_commands, ui
from discord.ext import commands, tasks
from config import DATA_DIR

try:
    from cogs.levels import levels_manager
except ImportError:
    levels_manager = None

logger = logging.getLogger("bot.giveaways")
GIVEAWAYS_FILE = DATA_DIR / "giveaways.json"


def parse_duration(duration_str: str) -> int | None:
    """
    Парсит строку длительности вида '10m', '2h', '1d', '30s', '1w' или '1ч 30м'.
    Поддерживает как английские (s, m, h, d, w), так и русские (с, м, ч, д, н) обозначения.
    Возвращает количество секунд или None, если формат не распознан.
    """
    if not duration_str:
        return None

    cleaned = duration_str.strip().lower()
    matches = re.findall(r"(\d+)\s*([smhdwсмчдн])", cleaned)
    if not matches:
        if cleaned.isdigit():
            # Если введено просто число — считаем минутами
            return int(cleaned) * 60
        return None

    unit_multipliers = {
        "s": 1, "с": 1,           # секунды
        "m": 60, "м": 60,         # минуты
        "h": 3600, "ч": 3600,     # часы
        "d": 86400, "д": 86400,   # дни
        "w": 604800, "н": 604800  # недели
    }

    total_seconds = 0
    for value_str, unit in matches:
        multiplier = unit_multipliers.get(unit, 0)
        total_seconds += int(value_str) * multiplier

    return total_seconds if total_seconds > 0 else None


class GiveawaysManager:
    """Менеджер базы данных розыгрышей с сохранением в JSON."""

    def __init__(self, file_path: Path = GIVEAWAYS_FILE):
        self.file_path = file_path
        self._data: dict[str, dict] = self._load()
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
            logger.error(f"Ошибка сохранения {self.file_path}: {e}")

    def add_giveaway(self, message_id: int, data: dict):
        self._data[str(message_id)] = data
        self.save()

    def get_giveaway(self, message_id: int) -> dict | None:
        return self._data.get(str(message_id))

    def get_all(self) -> dict[str, dict]:
        return self._data

    def get_all_active(self) -> list[dict]:
        return [g for g in self._data.values() if not g.get("ended", False)]

    def get_guild_giveaways(self, guild_id: int, active_only: bool = True) -> list[dict]:
        res = []
        for g in self._data.values():
            if g.get("guild_id") == guild_id:
                if not active_only or not g.get("ended", False):
                    res.append(g)
        return res

    def delete_giveaway(self, message_id: int):
        mid = str(message_id)
        if mid in self._data:
            del self._data[mid]
            self.save()


giveaways_manager = GiveawaysManager()


def build_giveaway_embed(giveaway: dict, guild: discord.Guild | None = None) -> discord.Embed:
    """Генерирует стильный Embed для розыгрыша."""
    prize = giveaway.get("prize", "Приз")
    description = giveaway.get("description")
    host_id = giveaway.get("host_id")
    winners_count = giveaway.get("winners_count", 1)
    end_ts = int(giveaway.get("end_timestamp", 0))
    participants = giveaway.get("participants", [])
    ended = giveaway.get("ended", False)
    cancelled = giveaway.get("cancelled", False)
    winners = giveaway.get("winners", [])
    req_role_id = giveaway.get("required_role_id")
    min_level = giveaway.get("min_level", 0)

    if cancelled:
        title = f"🚨 РОЗЫГРЫШ ОТМЕНЕН: {prize}"
        color = discord.Color.red()
    elif ended:
        title = f"🎉 РОЗЫГРЫШ ЗАВЕРШЕН: {prize}"
        color = discord.Color.gold() if winners else discord.Color.dark_grey()
    else:
        title = f"🎁 РОЗЫГРЫШ: {prize}"
        color = discord.Color.brand_green()

    embed = discord.Embed(
        title=title,
        color=color,
        timestamp=discord.utils.utcnow()
    )

    if description:
        embed.description = f"{description}\n"
    else:
        embed.description = ""

    # Блок информации
    embed.add_field(name="👑 Организатор", value=f"<@{host_id}>", inline=True)
    embed.add_field(name="🏆 Победителей", value=f"**{winners_count}**", inline=True)
    embed.add_field(name="👥 Участников", value=f"**{len(participants)}**", inline=True)

    # Требования к участию
    reqs = []
    if req_role_id:
        reqs.append(f"🎖️ Роль: <@&{req_role_id}>")
    if min_level > 0:
        reqs.append(f"⭐ Мин. уровень: **{min_level}**")

    if reqs:
        embed.add_field(name="📋 Условия для участия", value="\n".join(reqs), inline=False)

    # Время и итоги
    if cancelled:
        embed.add_field(name="Статус", value="⛔ Розыгрыш был отменен организатором.", inline=False)
    elif ended:
        if winners:
            winners_str = ", ".join(f"<@{w}>" for w in winners)
            embed.add_field(name="🏆 Победители", value=winners_str, inline=False)
        else:
            embed.add_field(name="🏆 Победители", value="*Победители не определены (недостаточно участников)*", inline=False)
        embed.add_field(name="⌛ Завершен", value=f"<t:{end_ts}:R> (<t:{end_ts}:f>)", inline=False)
    else:
        embed.add_field(
            name="⏳ Окончание",
            value=f"<t:{end_ts}:R> (<t:{end_ts}:f>)",
            inline=False
        )
        embed.set_footer(text="Нажмите '🎉 Участвовать' ниже для участия или выхода | ID: " + str(giveaway.get('message_id', '')))

    if guild and guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    return embed


class GiveawayJoinView(ui.View):
    """Постоянная панель с кнопками для участия в розыгрыше."""

    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="🎉 Участвовать",
        style=discord.ButtonStyle.primary,
        custom_id="giveaway_join_btn"
    )
    async def join_giveaway(self, interaction: discord.Interaction, button: ui.Button):
        giveaway = giveaways_manager.get_giveaway(interaction.message.id)
        if not giveaway:
            await interaction.response.send_message("❌ Этот розыгрыш не найден в базе данных.", ephemeral=True)
            return

        if giveaway.get("ended", False):
            await interaction.response.send_message("❌ Этот розыгрыш уже завершен.", ephemeral=True)
            return

        guild = interaction.guild
        user = interaction.user

        # 1. Проверка роли-требования
        req_role_id = giveaway.get("required_role_id")
        if req_role_id:
            role = guild.get_role(req_role_id) if guild else None
            if role and role not in user.roles:
                await interaction.response.send_message(
                    f"❌ Для участия в этом розыгрыше вам необходима роль {role.mention}!",
                    ephemeral=True
                )
                return

        # 2. Проверка минимального уровня активности
        min_level = giveaway.get("min_level", 0)
        if min_level > 0 and levels_manager and guild:
            user_data = levels_manager.get_user_data(guild.id, user.id)
            user_level = user_data.get("level", 0)
            if user_level < min_level:
                await interaction.response.send_message(
                    f"❌ Для участия в этом розыгрыше требуется как минимум **{min_level} уровень** активности!\n"
                    f"Ваш текущий уровень: **{user_level}**.\n"
                    f"💬 Общайтесь в текстовых и голосовых каналах сервера для повышения уровня (`/rank`).",
                    ephemeral=True
                )
                return

        participants: list = giveaway.setdefault("participants", [])
        if user.id in participants:
            # Выход из розыгрыша
            participants.remove(user.id)
            giveaways_manager._is_dirty = True
            giveaways_manager.save()
            msg = f"👋 Вы вышли из розыгрыша приза **{giveaway['prize']}**."
        else:
            # Вход в розыгрыш
            participants.append(user.id)
            giveaways_manager._is_dirty = True
            giveaways_manager.save()
            msg = f"🎉 Вы успешно зарегистрированы в розыгрыше приза **{giveaway['prize']}**! Желаем удачи!"

        # Обновляем эмбед и кнопку с новым числом участников
        button.label = f"🎉 Участвовать ({len(participants)})"
        new_embed = build_giveaway_embed(giveaway, guild)
        try:
            await interaction.message.edit(embed=new_embed, view=self)
        except Exception as e:
            logger.error(f"Не удалось обновить сообщение розыгрыша: {e}")

        await interaction.response.send_message(msg, ephemeral=True)

    @ui.button(
        label="👥 Участники",
        style=discord.ButtonStyle.secondary,
        custom_id="giveaway_participants_btn"
    )
    async def list_participants(self, interaction: discord.Interaction, button: ui.Button):
        giveaway = giveaways_manager.get_giveaway(interaction.message.id)
        if not giveaway:
            await interaction.response.send_message("❌ Розыгрыш не найден.", ephemeral=True)
            return

        participants = giveaway.get("participants", [])
        if not participants:
            await interaction.response.send_message(
                "👥 В этом розыгрыше пока нет участников. Будьте первым — нажмите кнопку **🎉 Участвовать**!",
                ephemeral=True
            )
            return

        # Показываем список участников
        total_count = len(participants)
        show_limit = 25
        sample_users = participants[:show_limit]
        mentions = [f"<@{uid}>" for uid in sample_users]
        text = ", ".join(mentions)

        if total_count > show_limit:
            text += f"\n\n*...и ещё {total_count - show_limit} участников*"

        embed = discord.Embed(
            title=f"👥 Список участников ({total_count})",
            description=f"Приз: **{giveaway.get('prize', 'Приз')}**\n\n{text}",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class Giveaways(commands.Cog):
    """Ког управления розыгрышами (Giveaways)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_giveaways_loop.start()

    def cog_unload(self):
        self.check_giveaways_loop.cancel()
        giveaways_manager.save()

    @tasks.loop(seconds=5.0)
    async def check_giveaways_loop(self):
        """Фоновая проверка завершения розыгрышей по таймеру."""
        await self.bot.wait_until_ready()
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()

        active_giveaways = giveaways_manager.get_all_active()
        for giveaway in active_giveaways:
            end_ts = giveaway.get("end_timestamp", 0)
            if now >= end_ts:
                try:
                    await self.finish_giveaway(giveaway)
                except Exception as e:
                    logger.error(f"Ошибка завершения розыгрыша {giveaway.get('message_id')}: {e}", exc_info=True)

    async def finish_giveaway(self, giveaway: dict) -> list[int]:
        """Завершает розыгрыш, производит отбор победителей и отправляет оповещения."""
        giveaway["ended"] = True
        guild_id = giveaway.get("guild_id")
        channel_id = giveaway.get("channel_id")
        message_id = giveaway.get("message_id")
        prize = giveaway.get("prize", "Приз")
        host_id = giveaway.get("host_id")
        winners_count = max(1, giveaway.get("winners_count", 1))

        guild = self.bot.get_guild(guild_id)
        if not guild:
            giveaways_manager.save()
            return []

        channel = guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            giveaways_manager.save()
            return []

        # Загружаем сообщение розыгрыша
        message = None
        try:
            message = await channel.fetch_message(message_id)
        except Exception:
            logger.warning(f"Сообщение розыгрыша {message_id} не найдено на канале {channel.name}")

        raw_participants = list(giveaway.get("participants", []))
        req_role_id = giveaway.get("required_role_id")
        min_level = giveaway.get("min_level", 0)

        # Валидация участников
        valid_participants = []
        for uid in raw_participants:
            member = guild.get_member(uid)
            if not member or member.bot:
                continue
            if req_role_id and not any(r.id == req_role_id for r in member.roles):
                continue
            if min_level > 0 and levels_manager:
                user_data = levels_manager.get_user_data(guild.id, uid)
                if user_data.get("level", 0) < min_level:
                    continue
            valid_participants.append(uid)

        winners_ids = []
        if valid_participants:
            actual_count = min(winners_count, len(valid_participants))
            winners_ids = random.sample(valid_participants, actual_count)

        giveaway["winners"] = winners_ids
        giveaways_manager.save()

        # Деактивированная кнопка
        disabled_view = ui.View(timeout=None)
        disabled_view.add_item(ui.Button(
            label=f"Розыгрыш завершен ({len(raw_participants)})",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            emoji="🎉"
        ))

        # Обновляем оригинальное сообщение
        end_embed = build_giveaway_embed(giveaway, guild)
        if message:
            try:
                await message.edit(embed=end_embed, view=disabled_view)
            except Exception as e:
                logger.error(f"Не удалось обновить карточку розыгрыша {message_id}: {e}")

        # Публикуем результат в канал
        if winners_ids:
            mentions = ", ".join(f"<@{wid}>" for wid in winners_ids)
            result_embed = discord.Embed(
                title="🎊 Итоги розыгрыша!",
                description=(
                    f"🎁 Приз: **{prize}**\n\n"
                    f"🏆 **Победители:** {mentions}\n\n"
                    f"👑 Организатор: <@{host_id}>\n"
                    f"👥 Всего участников: **{len(raw_participants)}**\n"
                    f"🔗 [Перейти к сообщению розыгрыша]({message.jump_url if message else ''})"
                ),
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )
            result_embed.set_footer(text="Поздравляем! Свяжитесь с организатором для получения награды.")
            try:
                await channel.send(content=f"🎉 {mentions}", embed=result_embed)
            except Exception as e:
                logger.error(f"Не удалось отправить объявление победителей: {e}")
        else:
            try:
                fail_embed = discord.Embed(
                    title="😢 Розыгрыш завершен без победителей",
                    description=(
                        f"В розыгрыше **{prize}** не набралось подходящих участников.\n\n"
                        f"👑 Организатор: <@{host_id}>\n"
                        f"🔗 [Перейти к розыгрышу]({message.jump_url if message else ''})"
                    ),
                    color=discord.Color.dark_grey(),
                    timestamp=discord.utils.utcnow()
                )
                await channel.send(embed=fail_embed)
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление о завершении: {e}")

        return winners_ids

    # ==========================================
    # СЛЭШ-КОМАНДЫ РОЗЫГРЫШЕЙ
    # ==========================================

    @app_commands.command(
        name="gstart",
        description="Запустить новый розыгрыш с призом, таймером и условиями"
    )
    @app_commands.describe(
        prize="Название приза (например: Discord Nitro, VIP роль, 1000 монет)",
        duration="Длительность розыгрыша (например: 10m, 2h, 1d, 30s, 1д, 2ч)",
        winners="Количество победителей (по умолчанию 1)",
        channel="Канал для публикации (по умолчанию текущий)",
        description="Дополнительное описание или правила розыгрыша",
        required_role="Обязательная роль для участия",
        min_level="Минимальный уровень в системе уровней сервера для участия"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def cmd_gstart(
        self,
        interaction: discord.Interaction,
        prize: str,
        duration: str,
        winners: app_commands.Range[int, 1, 20] = 1,
        channel: discord.TextChannel | None = None,
        description: str | None = None,
        required_role: discord.Role | None = None,
        min_level: app_commands.Range[int, 0, 100] = 0
    ):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        seconds = parse_duration(duration)
        if not seconds or seconds < 10:
            await interaction.response.send_message(
                "❌ **Неверный формат времени!**\n"
                "Примеры корректного времени:\n"
                "• `30s` (30 секунд)\n"
                "• `15m` или `15м` (15 минут)\n"
                "• `2h` или `2ч` (2 часа)\n"
                "• `1d` или `1д` (1 день)\n"
                "• `1h30m` или `1ч30м` (1 час 30 минут)\n"
                "*(Минимальная длительность: 10 секунд)*",
                ephemeral=True
            )
            return

        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message("❌ Выберите текстовый канал.", ephemeral=True)
            return

        # Проверка прав бота в целевом канале
        bot_member = guild.me
        perms = target_channel.permissions_for(bot_member)
        if not perms.send_messages or not perms.embed_links:
            await interaction.response.send_message(
                f"❌ У бота нет прав отправлять сообщения или эмбеды в канале {target_channel.mention}!",
                ephemeral=True
            )
            return

        now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
        end_ts = now_ts + seconds

        giveaway_data = {
            "guild_id": guild.id,
            "channel_id": target_channel.id,
            "message_id": 0,
            "prize": prize,
            "description": description,
            "host_id": interaction.user.id,
            "winners_count": winners,
            "created_at": now_ts,
            "end_timestamp": end_ts,
            "required_role_id": required_role.id if required_role else None,
            "min_level": min_level,
            "participants": [],
            "ended": False,
            "cancelled": False,
            "winners": []
        }

        # Отправляем сообщение в целевой канал
        embed = build_giveaway_embed(giveaway_data, guild)
        view = GiveawayJoinView()

        try:
            giveaway_msg = await target_channel.send(embed=embed, view=view)
        except Exception as e:
            await interaction.response.send_message(f"❌ Не удалось отправить сообщение розыгрыша: {e}", ephemeral=True)
            return

        giveaway_data["message_id"] = giveaway_msg.id
        giveaways_manager.add_giveaway(giveaway_msg.id, giveaway_data)

        # Обновляем ID в футере эмбеда
        updated_embed = build_giveaway_embed(giveaway_data, guild)
        await giveaway_msg.edit(embed=updated_embed)

        await interaction.response.send_message(
            f"✅ **Розыгрыш успешно запущен!**\n"
            f"🎁 Приз: **{prize}**\n"
            f"📍 Канал: {target_channel.mention}\n"
            f"🏆 Победителей: **{winners}**\n"
            f"⏳ Окончание: <t:{int(end_ts)}:R>\n"
            f"🔗 [Перейти к розыгрышу]({giveaway_msg.jump_url})",
            ephemeral=True
        )

    @app_commands.command(
        name="gend",
        description="Досрочно завершить розыгрыш и сразу определить победителей"
    )
    @app_commands.describe(message_id="ID сообщения розыгрыша")
    @app_commands.default_permissions(manage_guild=True)
    async def cmd_gend(self, interaction: discord.Interaction, message_id: str):
        mid = message_id.strip()
        if not mid.isdigit():
            await interaction.response.send_message("❌ ID сообщения должен состоять только из цифр.", ephemeral=True)
            return

        giveaway = giveaways_manager.get_giveaway(int(mid))
        if not giveaway:
            await interaction.response.send_message("❌ Розыгрыш с таким ID сообщения не найден.", ephemeral=True)
            return

        if giveaway.get("ended", False):
            await interaction.response.send_message("⚠️ Этот розыгрыш уже завершен.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        winners = await self.finish_giveaway(giveaway)

        if winners:
            mentions = ", ".join(f"<@{w}>" for w in winners)
            await interaction.followup.send(
                f"✅ Розыгрыш приза **{giveaway['prize']}** успешно завершен досрочно!\n🏆 Победители: {mentions}",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"✅ Розыгрыш приза **{giveaway['prize']}** завершен досрочно. Победители не определены (нет подходящих участников).",
                ephemeral=True
            )

    @app_commands.command(
        name="greroll",
        description="Перевыбрать случайных победителей в уже завершенном розыгрыше"
    )
    @app_commands.describe(
        message_id="ID сообщения завершенного розыгрыша",
        winners="Количество новых победителей (по умолчанию 1)"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def cmd_greroll(
        self,
        interaction: discord.Interaction,
        message_id: str,
        winners: app_commands.Range[int, 1, 20] = 1
    ):
        mid = message_id.strip()
        if not mid.isdigit():
            await interaction.response.send_message("❌ ID сообщения должен состоять только из цифр.", ephemeral=True)
            return

        giveaway = giveaways_manager.get_giveaway(int(mid))
        if not giveaway:
            await interaction.response.send_message("❌ Розыгрыш с таким ID сообщения не найден.", ephemeral=True)
            return

        if not giveaway.get("ended", False):
            await interaction.response.send_message(
                "❌ Этот розыгрыш еще не завершен. Дождитесь окончания таймера или завершите его через `/gend`.",
                ephemeral=True
            )
            return

        guild = interaction.guild
        if not guild:
            return

        channel = guild.get_channel(giveaway.get("channel_id"))
        if not channel or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("❌ Канал розыгрыша не найден.", ephemeral=True)
            return

        raw_participants = list(giveaway.get("participants", []))
        req_role_id = giveaway.get("required_role_id")
        min_level = giveaway.get("min_level", 0)

        # Фильтруем участников
        valid_participants = []
        for uid in raw_participants:
            member = guild.get_member(uid)
            if not member or member.bot:
                continue
            if req_role_id and not any(r.id == req_role_id for r in member.roles):
                continue
            if min_level > 0 and levels_manager:
                ud = levels_manager.get_user_data(guild.id, uid)
                if ud.get("level", 0) < min_level:
                    continue
            valid_participants.append(uid)

        if not valid_participants:
            await interaction.response.send_message("❌ Нет подходящих участников для выбора нового победителя.", ephemeral=True)
            return

        # Исключаем предыдущих победителей, если остаются другие кандидаты
        prev_winners = set(giveaway.get("winners", []))
        pool = [uid for uid in valid_participants if uid not in prev_winners]
        if not pool:
            pool = valid_participants

        actual_count = min(winners, len(pool))
        new_winners = random.sample(pool, actual_count)
        giveaway["winners"] = new_winners
        giveaways_manager.save()

        # Обновляем оригинальное сообщение
        try:
            msg = await channel.fetch_message(int(mid))
            updated_embed = build_giveaway_embed(giveaway, guild)
            await msg.edit(embed=updated_embed)
        except Exception:
            msg = None

        mentions = ", ".join(f"<@{w}>" for w in new_winners)
        reroll_embed = discord.Embed(
            title="🔄 Перевыбор победителя розыгрыша!",
            description=(
                f"🎁 Приз: **{giveaway['prize']}**\n\n"
                f"🏆 **Новые победители:** {mentions}\n\n"
                f"👑 Организатор: <@{giveaway.get('host_id')}>\n"
                f"🔗 [Перейти к сообщению розыгрыша]({msg.jump_url if msg else ''})"
            ),
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )
        reroll_embed.set_footer(text="Поздравляем новых победителей!")
        await channel.send(content=f"🎉 {mentions}", embed=reroll_embed)

        await interaction.response.send_message(
            f"✅ Новые победители выбраны: {mentions}",
            ephemeral=True
        )

    @app_commands.command(
        name="gcancel",
        description="Отменить активный розыгрыш без выбора победителей"
    )
    @app_commands.describe(message_id="ID сообщения розыгрыша")
    @app_commands.default_permissions(manage_guild=True)
    async def cmd_gcancel(self, interaction: discord.Interaction, message_id: str):
        mid = message_id.strip()
        if not mid.isdigit():
            await interaction.response.send_message("❌ ID сообщения должен состоять только из цифр.", ephemeral=True)
            return

        giveaway = giveaways_manager.get_giveaway(int(mid))
        if not giveaway:
            await interaction.response.send_message("❌ Розыгрыш с таким ID сообщения не найден.", ephemeral=True)
            return

        if giveaway.get("ended", False):
            await interaction.response.send_message("⚠️ Этот розыгрыш уже завершен.", ephemeral=True)
            return

        giveaway["ended"] = True
        giveaway["cancelled"] = True
        giveaway["winners"] = []
        giveaways_manager.save()

        guild = interaction.guild
        channel = guild.get_channel(giveaway.get("channel_id")) if guild else None
        if channel and isinstance(channel, discord.TextChannel):
            try:
                msg = await channel.fetch_message(int(mid))
                cancel_embed = build_giveaway_embed(giveaway, guild)
                disabled_view = ui.View(timeout=None)
                disabled_view.add_item(ui.Button(
                    label="Розыгрыш отменен",
                    style=discord.ButtonStyle.danger,
                    disabled=True,
                    emoji="🚨"
                ))
                await msg.edit(embed=cancel_embed, view=disabled_view)
            except Exception as e:
                logger.error(f"Не удалось обновить отмененный розыгрыш {mid}: {e}")

        await interaction.response.send_message(f"🚨 Розыгрыш **{giveaway['prize']}** успешно отменен.", ephemeral=True)

    @app_commands.command(
        name="glist",
        description="Показать список всех активных розыгрышей на этом сервере"
    )
    async def cmd_glist(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        active = giveaways_manager.get_guild_giveaways(guild.id, active_only=True)
        if not active:
            await interaction.response.send_message(
                "🎁 На сервере сейчас нет активных розыгрышей.\n"
                "Администраторы могут запустить новый розыгрыш с помощью команды `/gstart`!",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"🎁 Активные розыгрыши — {guild.name}",
            description=f"Сейчас проводится **{len(active)}** розыгрышей:\n",
            color=discord.Color.brand_green(),
            timestamp=discord.utils.utcnow()
        )

        for g in active:
            ch_id = g.get("channel_id")
            ch = guild.get_channel(ch_id)
            ch_str = ch.mention if ch else f"`ID: {ch_id}`"
            end_ts = int(g.get("end_timestamp", 0))
            prize = g.get("prize", "Приз")
            mid = g.get("message_id")
            participants_count = len(g.get("participants", []))
            winners_count = g.get("winners_count", 1)

            embed.add_field(
                name=f"🎉 {prize}",
                value=(
                    f"📍 Канал: {ch_str}\n"
                    f"🏆 Победителей: **{winners_count}** | 👥 Участников: **{participants_count}**\n"
                    f"⏳ Завершение: <t:{end_ts}:R> (<t:{end_ts}:f>)\n"
                    f"🆔 Сообщения: `{mid}`"
                ),
                inline=False
            )

        embed.set_footer(text="Используйте кнопки под сообщениями для участия")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaways(bot))
