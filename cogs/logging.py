import asyncio
import logging
import discord
from discord.ext import commands
import datetime
from config import config_manager

logger = logging.getLogger("bot.logging")


class ServerLogging(commands.Cog):
    """Ког для комплексного логирования всех событий сервера в чистом элегантном стиле."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def format_channel_type(self, channel: discord.abc.GuildChannel) -> str:
        """Красивое форматирование типа канала."""
        if isinstance(channel, discord.TextChannel):
            return "Текстовый канал"
        elif isinstance(channel, discord.VoiceChannel):
            return "Голосовой канал"
        elif isinstance(channel, discord.CategoryChannel):
            return "Категория"
        elif isinstance(channel, discord.StageChannel):
            return "Сцена"
        elif isinstance(channel, discord.ForumChannel):
            return "Форум"
        return str(channel.type).capitalize()

    async def get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """Получает канал для отправки логов с поддержкой кэша и API."""
        if not guild:
            return None
        settings = config_manager.get_guild(guild.id)
        cid = settings.get("log_channel_id")
        if not cid:
            return None

        # 1. Поиск в кэше гильдии
        channel = guild.get_channel(cid) or self.bot.get_channel(cid)
        if isinstance(channel, discord.TextChannel):
            return channel

        # 2. Если в кэше нет, запрашиваем через API Discord
        try:
            channel = await self.bot.fetch_channel(cid)
            if isinstance(channel, discord.TextChannel):
                return channel
        except Exception:
            pass

        return None

    async def send_log(self, guild: discord.Guild, embed: discord.Embed):
        """Безопасная отправка лога в настроенный канал."""
        if not guild:
            return

        channel = await self.get_log_channel(guild)
        if not channel:
            return

        perms = channel.permissions_for(guild.me)
        if not perms.send_messages:
            logger.warning(f"У бота нет прав на отправку сообщений в канале #{channel.name} на сервере '{guild.name}'")
            return
        if not perms.embed_links:
            logger.warning(f"У бота нет прав на встраивание ссылок (Embed Links) в канале #{channel.name} на сервере '{guild.name}'")
            return

        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Не удалось отправить лог на сервере '{guild.name}': {e}", exc_info=True)

    async def get_audit_moderator(
        self,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        target_id: int,
        fallback: str = "Неизвестно",
        check_attr: str | None = None
    ) -> str:
        """Определяет модератора или автора действия через Audit Log с фильтрацией по времени."""
        if not guild.me or not guild.me.guild_permissions.view_audit_log:
            return fallback

        await asyncio.sleep(0.5)
        try:
            async for entry in guild.audit_logs(limit=5, action=action):
                if entry.target and entry.target.id == target_id:
                    if check_attr and hasattr(entry, 'after') and not hasattr(entry.after, check_attr):
                        continue
                    diff = (discord.utils.utcnow() - entry.created_at).total_seconds()
                    if diff < 15:
                        if entry.user:
                            return entry.user.display_name
                        break
        except Exception as e:
            logger.debug(f"Ошибка при запросе Audit Log ({action}): {e}")

        return fallback

    # ==========================================
    # 1. СООБЩЕНИЯ
    # ==========================================

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        embed = discord.Embed(
            title="Удаление сообщения",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=message.author.display_avatar.url)
        embed.add_field(name="Пользователь", value=message.author.mention, inline=False)
        embed.add_field(name="Канал", value=message.channel.mention, inline=True)

        content = message.content or "*[Пустое сообщение или вложения]*"
        if len(content) > 1000:
            content = content[:1000] + "... (обрезано)"
        embed.add_field(name="Содержимое", value=content, inline=False)

        if message.attachments:
            att_names = "\n".join([f"📎 [{att.filename}]({att.url})" for att in message.attachments])
            embed.add_field(name="Вложения", value=att_names[:1000], inline=False)

        mod_name = await self.get_audit_moderator(
            guild=message.guild,
            action=discord.AuditLogAction.message_delete,
            target_id=message.author.id,
            fallback=None
        )
        if mod_name and mod_name != message.author.display_name:
            embed.set_footer(text=f"Удалил: {mod_name}")
        else:
            embed.set_footer(text=f"ID сообщения: {message.id}")

        await self.send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot:
            return
        if before.content == after.content:
            return

        embed = discord.Embed(
            title="Редактирование сообщения",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=before.author.display_avatar.url)
        embed.add_field(name="Пользователь", value=before.author.mention, inline=False)
        embed.add_field(name="Канал", value=before.channel.mention, inline=True)
        embed.add_field(name="Сообщение", value=f"[Перейти к сообщению]({after.jump_url})", inline=True)

        before_text = before.content or "*[Пусто]*"
        after_text = after.content or "*[Пусто]*"

        if len(before_text) > 900:
            before_text = before_text[:900] + "..."
        if len(after_text) > 900:
            after_text = after_text[:900] + "..."

        embed.add_field(name="До", value=before_text, inline=True)
        embed.add_field(name="После", value=after_text, inline=True)
        embed.set_footer(text=f"ID сообщения: {before.id}")
        await self.send_log(before.guild, embed)

    # ==========================================
    # 2. УЧАСТНИКИ (ВХОД, ВЫХОД, РОЛИ, НИКНЕЙМ)
    # ==========================================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        try:
            guild = member.guild
            logger.info(f"📥 Участник {member} ({member.id}) зашел на сервер '{guild.name}'")
            settings = config_manager.get_guild(guild.id)

            # 1. Автоматическая выдача роли при входе (Autorole)
            autorole_id = settings.get("auto_role_id")
            given_role = None
            if autorole_id:
                role = guild.get_role(autorole_id)
                if role:
                    try:
                        await member.add_roles(role, reason="Автовыдача роли при входе на сервер (Autorole)")
                        given_role = role
                    except Exception as e:
                        logger.warning(f"Не удалось выдать автороль участнику {member}: {e}")

            # 2. Формирование лога входа на сервер
            embed = discord.Embed(
                title="Вход на сервер",
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="Пользователь", value=member.mention, inline=False)
            embed.add_field(
                name="Аккаунт создан",
                value=f"<t:{int(member.created_at.timestamp())}:F>\n(<t:{int(member.created_at.timestamp())}:R>)",
                inline=True
            )
            embed.add_field(
                name="Всего участников",
                value=f"**{guild.member_count}**",
                inline=True
            )

            if given_role:
                embed.add_field(name="Выдана роль", value=given_role.mention, inline=False)

            embed.set_footer(text=f"Сервер: {guild.name}")
            await self.send_log(guild, embed)
        except Exception as e:
            logger.error(f"Ошибка при обработке входа участника {member}: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_raw_member_remove(self, payload: discord.RawMemberRemoveEvent):
        try:
            guild = self.bot.get_guild(payload.guild_id)
            if not guild:
                try:
                    guild = await self.bot.fetch_guild(payload.guild_id)
                except Exception:
                    return

            user = payload.user
            member_id = user.id
            avatar_url = user.display_avatar.url
            logger.info(f"📤 Участник {user} ({member_id}) покинул сервер '{guild.name}'")

            # Проверка, не был ли участник кикнут модератором
            kick_entry = None
            if guild.me and guild.me.guild_permissions.view_audit_log:
                await asyncio.sleep(0.5)
                try:
                    async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.kick):
                        if entry.target and entry.target.id == member_id:
                            diff = (discord.utils.utcnow() - entry.created_at).total_seconds()
                            if diff < 15:
                                kick_entry = entry
                                break
                except Exception:
                    pass

            if kick_entry:
                embed = discord.Embed(
                    title="Исключение (Кик)",
                    color=discord.Color.orange()
                )
                embed.set_thumbnail(url=avatar_url)
                embed.add_field(name="Пользователь", value=f"<@{member_id}>", inline=False)
                embed.add_field(name="Осталось участников", value=f"**{guild.member_count}**", inline=True)
                mod_name = kick_entry.user.display_name if kick_entry.user else str(kick_entry.user)
                footer_text = f"Исключил: {mod_name}"
                if kick_entry.reason:
                    footer_text += f" | Причина: {kick_entry.reason}"
                embed.set_footer(text=footer_text)
            else:
                embed = discord.Embed(
                    title="Выход с сервера",
                    color=discord.Color.red()
                )
                embed.set_thumbnail(url=avatar_url)
                embed.add_field(name="Пользователь", value=f"<@{member_id}>", inline=False)
                embed.add_field(name="Осталось участников", value=f"**{guild.member_count}**", inline=True)
                embed.set_footer(text=f"Сервер: {guild.name}")

            await self.send_log(guild, embed)
        except Exception as e:
            logger.error(f"Ошибка при обработке выхода участника: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        guild = before.guild
        embeds_to_send = []

        # 1. Смена никнейма (Точно в стиле скриншота)
        if before.nick != after.nick:
            mod_name = await self.get_audit_moderator(
                guild=guild,
                action=discord.AuditLogAction.member_update,
                target_id=after.id,
                fallback=after.display_name,
                check_attr="nick"
            )
            embed = discord.Embed(
                title="Смена никнейма",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=after.display_avatar.url)
            embed.add_field(name="Пользователь", value=after.mention, inline=False)
            embed.add_field(name="До", value=before.nick or before.name, inline=True)
            embed.add_field(name="После", value=after.nick or after.name, inline=True)
            embed.set_footer(text=f"Изменил: {mod_name}")
            embeds_to_send.append(embed)

        # 2. Смена ролей: добавление и удаление отдельными карточками (В стиле скриншота)
        if before.roles != after.roles:
            added = [r for r in after.roles if r not in before.roles]
            removed = [r for r in before.roles if r not in after.roles]

            if added or removed:
                mod_name = await self.get_audit_moderator(
                    guild=guild,
                    action=discord.AuditLogAction.member_role_update,
                    target_id=after.id,
                    fallback=guild.me.display_name
                )

                if added:
                    embed_add = discord.Embed(
                        title="Изменение ролей",
                        color=discord.Color.orange()
                    )
                    embed_add.set_thumbnail(url=after.display_avatar.url)
                    embed_add.add_field(name="Пользователь", value=after.mention, inline=False)
                    embed_add.add_field(name="Добавлены роли", value=", ".join(r.mention for r in added), inline=False)
                    embed_add.set_footer(text=f"Изменил: {mod_name}")
                    embeds_to_send.append(embed_add)

                if removed:
                    embed_rem = discord.Embed(
                        title="Изменение ролей",
                        color=discord.Color.orange()
                    )
                    embed_rem.set_thumbnail(url=after.display_avatar.url)
                    embed_rem.add_field(name="Пользователь", value=after.mention, inline=False)
                    embed_rem.add_field(name="Удалены роли", value=", ".join(r.mention for r in removed), inline=False)
                    embed_rem.set_footer(text=f"Изменил: {mod_name}")
                    embeds_to_send.append(embed_rem)

        # 3. Тайм-аут (мут)
        if before.timed_out_until != after.timed_out_until:
            mod_name = await self.get_audit_moderator(
                guild=guild,
                action=discord.AuditLogAction.member_update,
                target_id=after.id,
                fallback="Модератор",
                check_attr="timed_out_until"
            )
            is_timeout = bool(after.timed_out_until)
            embed = discord.Embed(
                title="Тайм-аут",
                color=discord.Color.orange() if is_timeout else discord.Color.green()
            )
            embed.set_thumbnail(url=after.display_avatar.url)
            embed.add_field(name="Пользователь", value=after.mention, inline=False)
            if is_timeout:
                embed.add_field(
                    name="Действует до",
                    value=f"<t:{int(after.timed_out_until.timestamp())}:F> (<t:{int(after.timed_out_until.timestamp())}:R>)",
                    inline=False
                )
            else:
                embed.add_field(name="Статус", value="Снят", inline=False)
            embed.set_footer(text=f"Изменил: {mod_name}")
            embeds_to_send.append(embed)

        for emb in embeds_to_send:
            await self.send_log(guild, emb)

    # ==========================================
    # 3. МОДЕРАЦИЯ (БАН / РАЗБАН)
    # ==========================================

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member):
        mod_name = "Модератор"
        reason = None
        if guild.me.guild_permissions.view_audit_log:
            try:
                async for entry in guild.audit_logs(limit=2, action=discord.AuditLogAction.ban):
                    if entry.target and entry.target.id == user.id:
                        if entry.user:
                            mod_name = entry.user.display_name
                        reason = entry.reason
                        break
            except Exception:
                pass

        embed = discord.Embed(
            title="Блокировка участника",
            color=discord.Color.dark_red()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Пользователь", value=f"{user.mention} (`{user}`)", inline=False)
        if reason:
            embed.add_field(name="Причина", value=reason, inline=False)
        embed.set_footer(text=f"Заблокировал: {mod_name}")
        await self.send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        mod_name = "Модератор"
        if guild.me.guild_permissions.view_audit_log:
            try:
                async for entry in guild.audit_logs(limit=2, action=discord.AuditLogAction.unban):
                    if entry.target and entry.target.id == user.id:
                        if entry.user:
                            mod_name = entry.user.display_name
                        break
            except Exception:
                pass

        embed = discord.Embed(
            title="Разблокировка участника",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Пользователь", value=f"{user.mention} (`{user}`)", inline=False)
        embed.set_footer(text=f"Разблокировал: {mod_name}")
        await self.send_log(guild, embed)

    # ==========================================
    # 4. ГОЛОСОВЫЕ КАНАЛЫ
    # ==========================================

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        guild = member.guild
        embed = None

        if before.channel is None and after.channel is not None:
            # Зашел в голосовой
            embed = discord.Embed(
                title="Подключение к голосовому каналу",
                color=discord.Color.teal()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="Пользователь", value=member.mention, inline=False)
            embed.add_field(name="Канал", value=f"🔊 {after.channel.name} ({after.channel.mention})", inline=False)
            embed.set_footer(text=f"Сервер: {guild.name}")

        elif before.channel is not None and after.channel is None:
            # Вышел из голосового
            embed = discord.Embed(
                title="Отключение от голосового канала",
                color=discord.Color.light_grey()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="Пользователь", value=member.mention, inline=False)
            embed.add_field(name="Был в канале", value=f"🔊 {before.channel.name}", inline=False)
            embed.set_footer(text=f"Сервер: {guild.name}")

        elif before.channel != after.channel:
            # Переместился между каналами
            embed = discord.Embed(
                title="Перемещение между голосовыми каналами",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="Пользователь", value=member.mention, inline=False)
            embed.add_field(name="Из канала", value=f"🔊 {before.channel.name}", inline=True)
            embed.add_field(name="В канал", value=f"🔊 {after.channel.name} ({after.channel.mention})", inline=True)
            embed.set_footer(text=f"Сервер: {guild.name}")

        if embed:
            await self.send_log(guild, embed)

    # ==========================================
    # 5. КАНАЛЫ (СОЗДАНИЕ / УДАЛЕНИЕ / ИЗМЕНЕНИЕ)
    # ==========================================

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        embed = discord.Embed(
            title="Создание канала",
            color=discord.Color.green()
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="Название", value=f"{channel.name} ({channel.mention})", inline=False)
        embed.add_field(name="Тип", value=self.format_channel_type(channel), inline=True)
        if channel.category:
            embed.add_field(name="Категория", value=channel.category.name, inline=True)

        mod_name = await self.get_audit_moderator(
            guild=guild,
            action=discord.AuditLogAction.channel_create,
            target_id=channel.id,
            fallback="Модератор"
        )
        embed.set_footer(text=f"Создал: {mod_name}")
        await self.send_log(guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        embed = discord.Embed(
            title="Удаление канала",
            color=discord.Color.red()
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="Название", value=f"#{channel.name}", inline=False)
        embed.add_field(name="Тип", value=self.format_channel_type(channel), inline=True)
        if channel.category:
            embed.add_field(name="Была категория", value=channel.category.name, inline=True)

        mod_name = await self.get_audit_moderator(
            guild=guild,
            action=discord.AuditLogAction.channel_delete,
            target_id=channel.id,
            fallback="Модератор"
        )
        embed.set_footer(text=f"Удалил: {mod_name}")
        await self.send_log(guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        guild = before.guild
        changes = []

        if before.name != after.name:
            changes.append(f"**Название:** `{before.name}` ➔ `{after.name}`")

        if isinstance(before, discord.TextChannel) and isinstance(after, discord.TextChannel):
            if before.topic != after.topic:
                changes.append(f"**Тема:** `{before.topic or 'Отсутствует'}` ➔ `{after.topic or 'Отсутствует'}`")
            if before.slowmode_delay != after.slowmode_delay:
                changes.append(f"**Медленный режим:** `{before.slowmode_delay}с` ➔ `{after.slowmode_delay}с`")

        if isinstance(before, discord.VoiceChannel) and isinstance(after, discord.VoiceChannel):
            if before.user_limit != after.user_limit:
                changes.append(f"**Лимит мест:** `{before.user_limit}` ➔ `{after.user_limit}`")

        if changes:
            embed = discord.Embed(
                title="Обновление канала",
                description="\n".join(changes),
                color=discord.Color.blue()
            )
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)

            embed.add_field(name="Канал", value=after.mention, inline=False)
            embed.add_field(name="Тип", value=self.format_channel_type(after), inline=True)

            mod_name = await self.get_audit_moderator(
                guild=guild,
                action=discord.AuditLogAction.channel_update,
                target_id=after.id,
                fallback="Модератор"
            )
            embed.set_footer(text=f"Изменил: {mod_name}")
            await self.send_log(guild, embed)

    # ==========================================
    # 6. РОЛИ (СОЗДАНИЕ / УДАЛЕНИЕ / ИЗМЕНЕНИЕ)
    # ==========================================

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        guild = role.guild
        embed = discord.Embed(
            title="Создание роли",
            color=discord.Color.green()
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="Роль", value=f"{role.mention} ({role.name})", inline=False)

        mod_name = await self.get_audit_moderator(
            guild=guild,
            action=discord.AuditLogAction.role_create,
            target_id=role.id,
            fallback="Модератор"
        )
        embed.set_footer(text=f"Создал: {mod_name}")
        await self.send_log(guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        guild = role.guild
        embed = discord.Embed(
            title="Удаление роли",
            color=discord.Color.red()
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="Имя роли", value=role.name, inline=False)

        mod_name = await self.get_audit_moderator(
            guild=guild,
            action=discord.AuditLogAction.role_delete,
            target_id=role.id,
            fallback="Модератор"
        )
        embed.set_footer(text=f"Удалил: {mod_name}")
        await self.send_log(guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        changes = []
        if before.name != after.name:
            changes.append(f"**Имя:** `{before.name}` ➔ `{after.name}`")
        if before.color != after.color:
            changes.append(f"**Цвет:** `{before.color}` ➔ `{after.color}`")
        if before.permissions != after.permissions:
            changes.append("**Права:** права роли были изменены.")

        if changes:
            guild = after.guild
            embed = discord.Embed(
                title="Обновление роли",
                description="\n".join(changes),
                color=discord.Color.gold()
            )
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)

            embed.add_field(name="Роль", value=after.mention, inline=False)

            mod_name = await self.get_audit_moderator(
                guild=guild,
                action=discord.AuditLogAction.role_update,
                target_id=after.id,
                fallback="Модератор"
            )
            embed.set_footer(text=f"Изменил: {mod_name}")
            await self.send_log(guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerLogging(bot))
