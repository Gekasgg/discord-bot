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
from config import DATA_DIR, config_manager

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


def check_giveaway_permission(interaction: discord.Interaction) -> tuple[bool, str]:
    """
    Проверяет, имеет ли пользователь право управлять розыгрышами:
    1. Администраторы сервера (или владелец)
    2. Участники с правом управления сервером (manage_guild)
    3. Участники с настроенной ролью ведущего розыгрышей (giveaway_role_id)
    4. Конкретные пользователи из списка разрешенных (giveaway_users)
    """
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False, "❌ Команда доступна только на сервере."

    member = interaction.user

    # Владелец сервера
    if member.id == interaction.guild.owner_id:
        return True, ""

    # Права администратора или управления сервером
    if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
        return True, ""

    settings = config_manager.get_guild(interaction.guild.id)

    # Проверка настроенной роли ведущего розыгрышей
    giveaway_role_id = settings.get("giveaway_role_id")
    if giveaway_role_id:
        role = interaction.guild.get_role(int(giveaway_role_id))
        if role and role in member.roles:
            return True, ""

    # Проверка списка персональных пользователей
    giveaway_users = settings.get("giveaway_users", [])
    if member.id in giveaway_users:
        return True, ""

    msg = (
        "❌ **Отказано в доступе!**\n"
        "Создавать и проводить розыгрыши могут только администраторы сервера или участники со специальным разрешением.\n\n"
        "💡 *Администратор сервера может назначить роль командой `/set-giveaway-role` или добавить вас персонально через `/add-giveaway-manager`.*"
    )
    return False, msg


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


async def send_winner_dm(bot: commands.Bot, guild: discord.Guild, user_id: int, giveaway: dict, jump_url: str | None = None) -> bool:
    """
    Отправляет личное сообщение победителю розыгрыша с поздравлением и секретным текстом/наградой.
    Возвращает True при успешной доставке, False если у пользователя закрыты ЛС.
    """
    try:
        user = guild.get_member(user_id) or await bot.fetch_user(user_id)
        if not user or user.bot:
            return False

        prize = giveaway.get("prize", "Приз")
        host_id = giveaway.get("host_id")
        custom_dm = giveaway.get("dm_message")

        embed = discord.Embed(
            title="🎉 Поздравляем с победой в розыгрыше!",
            description=f"Вы стали победителем розыгрыша приза **{prize}** на сервере **{guild.name}**! 🎁",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        if custom_dm:
            # Форматирование плейсхолдеров {prize}, {server}, {user}, {host}
            formatted = (
                custom_dm
                .replace("{prize}", prize)
                .replace("{server}", guild.name)
                .replace("{guild}", guild.name)
                .replace("{user}", user.display_name)
                .replace("{host}", f"<@{host_id}>")
            )
            embed.add_field(
                name="📩 Сообщение от организатора / Награда",
                value=formatted[:1024],
                inline=False
            )
        else:
            embed.add_field(
                name="ℹ️ Как получить приз",
                value=f"Свяжитесь с организатором розыгрыша <@{host_id}> на сервере **{guild.name}** для вручения приза!",
                inline=False
            )

        if jump_url:
            embed.add_field(
                name="🔗 Ссылка на розыгрыш",
                value=f"[Перейти к сообщению]({jump_url})",
                inline=False
            )

        embed.set_footer(text=f"Сервер: {guild.name} • Antigravity Bot")

        await user.send(embed=embed)
        logger.info(f"Успешно отправлено ЛС победителю {user} (ID: {user_id}) по розыгрышу {giveaway.get('message_id')}")
        return True
    except (discord.Forbidden, discord.HTTPException) as e:
        logger.warning(f"Не удалось отправить ЛС победителю {user_id} (ЛС закрыто или бот заблокирован): {e}")
        return False
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при отправке ЛС победителю {user_id}: {e}")
        return False


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

        # Отправка сообщений в ЛС победителям
        closed_dm_winners = []
        if winners_ids:
            for wid in winners_ids:
                sent = await send_winner_dm(
                    self.bot,
                    guild,
                    wid,
                    giveaway,
                    jump_url=message.jump_url if message else None
                )
                if not sent:
                    closed_dm_winners.append(wid)

            mentions = ", ".join(f"<@{wid}>" for wid in winners_ids)
            desc_lines = [
                f"🎁 Приз: **{prize}**\n",
                f"🏆 **Победители:** {mentions}",
                f"👑 Организатор: <@{host_id}>",
                f"👥 Всего участников: **{len(raw_participants)}**\n"
            ]

            if message:
                desc_lines.append(f"🔗 [Перейти к сообщению розыгрыша]({message.jump_url})\n")

            if closed_dm_winners:
                cdm_mentions = ", ".join(f"<@{uid}>" for uid in closed_dm_winners)
                desc_lines.append(f"⚠️ **Внимание:** У {cdm_mentions} **закрыты личные сообщения (ЛС)**! Пожалуйста, откройте ЛС или напишите организатору <@{host_id}>!")
            else:
                desc_lines.append("📬 *Победителям отправлено личное сообщение в ЛС с наградой/инструкцией!*")

            result_embed = discord.Embed(
                title="🎊 Итоги розыгрыша!",
                description="\n".join(desc_lines),
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


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaways(bot))
