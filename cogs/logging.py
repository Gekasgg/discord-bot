import asyncio
import discord
from discord.ext import commands
import datetime
from config import config_manager


class ServerLogging(commands.Cog):
    """Ког для комплексного логирования всех событий сервера."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def format_channel_type(self, channel: discord.abc.GuildChannel) -> str:
        """Красивое форматирование типа канала."""
        if isinstance(channel, discord.TextChannel):
            return "💬 Текстовый канал"
        elif isinstance(channel, discord.VoiceChannel):
            return "🔊 Голосовой канал"
        elif isinstance(channel, discord.CategoryChannel):
            return "📁 Категория"
        elif isinstance(channel, discord.StageChannel):
            return "🎭 Сцена"
        elif isinstance(channel, discord.ForumChannel):
            return "📋 Форум"
        return str(channel.type).capitalize()

    def get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """Получает канал для отправки логов."""
        if not guild:
            return None
        settings = config_manager.get_guild(guild.id)
        cid = settings.get("log_channel_id")
        if not cid:
            return None
        channel = guild.get_channel(cid)
        if isinstance(channel, discord.TextChannel):
            return channel
        return None

    async def send_log(self, guild: discord.Guild, embed: discord.Embed):
        """Безопасная отправка лога в настроенный канал."""
        channel = self.get_log_channel(guild)
        if not channel:
            return
        # Проверяем права бота на отправку сообщений и эмбедов
        perms = channel.permissions_for(guild.me)
        if not (perms.send_messages and perms.embed_links):
            return
        try:
            await channel.send(embed=embed)
        except Exception as e:
            print(f"[Logging Error] Не удалось отправить лог на сервере {guild.name}: {e}")

    # ==========================================
    # 1. СООБЩЕНИЯ
    # ==========================================

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        embed = discord.Embed(
            title="🗑️ Сообщение удалено",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=f"{message.author} ({message.author.id})", icon_url=message.author.display_avatar.url)
        embed.add_field(name="Канал", value=message.channel.mention, inline=True)
        embed.add_field(name="Автор", value=message.author.mention, inline=True)

        content = message.content or "*[Пустое сообщение или вложения]*"
        if len(content) > 1000:
            content = content[:1000] + "... (обрезано)"
        embed.add_field(name="Содержимое", value=content, inline=False)

        if message.attachments:
            att_names = "\n".join([f"📎 [{att.filename}]({att.url})" for att in message.attachments])
            embed.add_field(name="Вложения", value=att_names[:1000], inline=False)

        # Проверка, не удалил ли сообщение модератор
        if message.guild.me.guild_permissions.view_audit_log:
            await asyncio.sleep(0.5)
            try:
                async for entry in message.guild.audit_logs(limit=3, action=discord.AuditLogAction.message_delete):
                    if entry.target and entry.target.id == message.author.id:
                        if entry.user and entry.user.id != message.author.id:
                            embed.add_field(name="👤 Удалил модератор", value=f"{entry.user.mention} ({entry.user})", inline=False)
                        break
            except Exception:
                pass

        embed.set_footer(text=f"ID сообщения: {message.id}")
        await self.send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot:
            return
        if before.content == after.content:
            return

        embed = discord.Embed(
            title="✏️ Сообщение отредактировано",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=f"{before.author} ({before.author.id})", icon_url=before.author.display_avatar.url)
        embed.add_field(name="Канал", value=before.channel.mention, inline=True)
        embed.add_field(name="Перейти к сообщению", value=f"[Клик]({after.jump_url})", inline=True)

        before_text = before.content or "*[Пусто]*"
        after_text = after.content or "*[Пусто]*"

        if len(before_text) > 900:
            before_text = before_text[:900] + "..."
        if len(after_text) > 900:
            after_text = after_text[:900] + "..."

        embed.add_field(name="До изменения", value=before_text, inline=False)
        embed.add_field(name="После изменения", value=after_text, inline=False)
        embed.set_footer(text=f"ID сообщения: {before.id}")
        await self.send_log(before.guild, embed)

    # ==========================================
    # 2. УЧАСТНИКИ
    # ==========================================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(
            title="👋 Новый участник присоединился",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Участник", value=f"{member.mention} ({member})", inline=False)
        embed.add_field(name="ID участника", value=str(member.id), inline=True)
        embed.add_field(
            name="Аккаунт создан",
            value=f"<t:{int(member.created_at.timestamp())}:R>",
            inline=True
        )
        embed.add_field(name="Всего участников", value=str(member.guild.member_count), inline=True)
        await self.send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        embed = discord.Embed(
            title="🚪 Участник покинул сервер",
            color=discord.Color.dark_red(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Участник", value=f"{member} ({member.id})", inline=False)

        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        if roles:
            embed.add_field(name="Были роли", value=", ".join(roles)[:1000], inline=False)

        if member.joined_at:
            embed.add_field(
                name="Был на сервере с",
                value=f"<t:{int(member.joined_at.timestamp())}:R>",
                inline=True
            )

        # Проверка, не был ли участник кикнут модератором
        if guild.me.guild_permissions.view_audit_log:
            await asyncio.sleep(0.5)
            try:
                async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.kick):
                    if entry.target and entry.target.id == member.id:
                        embed.title = "👢 Участник исключен (Кик)"
                        embed.add_field(name="👤 Модератор", value=f"{entry.user.mention} ({entry.user})", inline=False)
                        if entry.reason:
                            embed.add_field(name="Причина", value=entry.reason, inline=False)
                        break
            except Exception:
                pass

        embed.add_field(name="Осталось участников", value=str(guild.member_count), inline=True)
        await self.send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        guild = before.guild
        embeds_to_send = []

        # 1. Смена никнейма
        if before.nick != after.nick:
            embed = discord.Embed(
                title="📝 Изменение никнейма",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=f"{after} ({after.id})", icon_url=after.display_avatar.url)
            embed.add_field(name="Участник", value=after.mention, inline=False)
            embed.add_field(name="Старый ник", value=before.nick or before.name, inline=True)
            embed.add_field(name="Новый ник", value=after.nick or after.name, inline=True)

            if guild.me.guild_permissions.view_audit_log:
                await asyncio.sleep(0.5)
                try:
                    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                        if entry.target and entry.target.id == after.id and hasattr(entry.after, 'nick'):
                            embed.add_field(name="👤 Изменил", value=f"{entry.user.mention} ({entry.user})", inline=False)
                            break
                except Exception:
                    pass

            embeds_to_send.append(embed)

        # 2. Смена ролей (выдача / снятие)
        if before.roles != after.roles:
            added = [r for r in after.roles if r not in before.roles]
            removed = [r for r in before.roles if r not in after.roles]

            if added or removed:
                embed = discord.Embed(
                    title="🛡️ Изменение ролей участника",
                    color=discord.Color.purple(),
                    timestamp=discord.utils.utcnow()
                )
                embed.set_author(name=f"{after} ({after.id})", icon_url=after.display_avatar.url)
                embed.add_field(name="Участник", value=f"{after.mention} ({after})", inline=False)
                if added:
                    embed.add_field(name="➕ Выданы роли", value=", ".join([r.mention for r in added]), inline=False)
                if removed:
                    embed.add_field(name="➖ Сняты роли", value=", ".join([r.mention for r in removed]), inline=False)

                # Поиск того, кто выдал или снял роли (через Audit Log)
                if guild.me.guild_permissions.view_audit_log:
                    await asyncio.sleep(0.5)
                    try:
                        async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
                            if entry.target and entry.target.id == after.id:
                                embed.add_field(name="👤 Выдал / Снял", value=f"{entry.user.mention} ({entry.user})", inline=False)
                                if entry.reason:
                                    embed.add_field(name="Причина", value=entry.reason, inline=False)
                                break
                    except Exception:
                        pass

                embeds_to_send.append(embed)

        # 3. Тайм-аут (мут)
        if before.timed_out_until != after.timed_out_until:
            embed = discord.Embed(
                title="⏳ Изменение таймаута",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=f"{after} ({after.id})", icon_url=after.display_avatar.url)
            if after.timed_out_until:
                embed.description = f"Участник {after.mention} отправлен в таймаут до <t:{int(after.timed_out_until.timestamp())}:F> (<t:{int(after.timed_out_until.timestamp())}:R>)"
            else:
                embed.description = f"С участника {after.mention} снят таймаут."

            if guild.me.guild_permissions.view_audit_log:
                await asyncio.sleep(0.5)
                try:
                    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                        if entry.target and entry.target.id == after.id and hasattr(entry.after, 'timed_out_until'):
                            embed.add_field(name="👤 Модератор", value=f"{entry.user.mention} ({entry.user})", inline=False)
                            if entry.reason:
                                embed.add_field(name="Причина", value=entry.reason, inline=False)
                            break
                except Exception:
                    pass

            embeds_to_send.append(embed)

        for emb in embeds_to_send:
            await self.send_log(guild, emb)

    # ==========================================
    # 3. МОДЕРАЦИЯ (БАН / РАЗБАН)
    # ==========================================

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member):
        embed = discord.Embed(
            title="🔨 Участник заблокирован (Бан)",
            color=discord.Color.dark_red(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Пользователь", value=f"{user} ({user.id})", inline=False)

        # Попытка получить причину и автора бана из Audit Log
        if guild.me.guild_permissions.view_audit_log:
            try:
                async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
                    if entry.target and entry.target.id == user.id:
                        embed.add_field(name="Модератор", value=f"{entry.user.mention} ({entry.user})", inline=True)
                        embed.add_field(name="Причина", value=entry.reason or "Не указана", inline=True)
                        break
            except Exception:
                pass

        await self.send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(
            title="🔓 Участник разблокирован (Разбан)",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Пользователь", value=f"{user} ({user.id})", inline=False)

        if guild.me.guild_permissions.view_audit_log:
            try:
                async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.unban):
                    if entry.target and entry.target.id == user.id:
                        embed.add_field(name="Модератор", value=f"{entry.user.mention} ({entry.user})", inline=True)
                        break
            except Exception:
                pass

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
                title="🔊 Подключение к голосовому каналу",
                color=discord.Color.teal(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=f"{member} ({member.id})", icon_url=member.display_avatar.url)
            embed.add_field(name="Канал", value=f"🔊 {after.channel.name} ({after.channel.mention})", inline=False)

        elif before.channel is not None and after.channel is None:
            # Вышел из голосового
            embed = discord.Embed(
                title="🔇 Отключение от голосового канала",
                color=discord.Color.light_grey(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=f"{member} ({member.id})", icon_url=member.display_avatar.url)
            embed.add_field(name="Был в канале", value=f"🔊 {before.channel.name}", inline=False)

        elif before.channel != after.channel:
            # Переместился между каналами
            embed = discord.Embed(
                title="🔀 Перемещение между голосовыми каналами",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=f"{member} ({member.id})", icon_url=member.display_avatar.url)
            embed.add_field(name="Из канала", value=f"🔊 {before.channel.name}", inline=True)
            embed.add_field(name="В канал", value=f"🔊 {after.channel.name} ({after.channel.mention})", inline=True)

        if embed:
            await self.send_log(guild, embed)

    # ==========================================
    # 5. КАНАЛЫ (СОЗДАНИЕ / УДАЛЕНИЕ / ИЗМЕНЕНИЕ)
    # ==========================================

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        embed = discord.Embed(
            title="📁 Канал создан",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Название", value=f"{channel.name} ({channel.mention})", inline=False)
        embed.add_field(name="Тип", value=self.format_channel_type(channel), inline=True)
        if channel.category:
            embed.add_field(name="Категория", value=channel.category.name, inline=True)

        # Определение автора создания через Audit Log
        if guild.me.guild_permissions.view_audit_log:
            await asyncio.sleep(0.6)
            try:
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.channel_create):
                    if entry.target and entry.target.id == channel.id:
                        embed.add_field(name="👤 Создал", value=f"{entry.user.mention} ({entry.user})", inline=False)
                        if entry.reason:
                            embed.add_field(name="Причина / Назначение", value=entry.reason, inline=False)
                        break
            except Exception:
                pass

        embed.set_footer(text=f"ID канала: {channel.id}")
        await self.send_log(guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        embed = discord.Embed(
            title="🗑️ Канал удален",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Название", value=f"#{channel.name}", inline=False)
        embed.add_field(name="Тип", value=self.format_channel_type(channel), inline=True)
        if channel.category:
            embed.add_field(name="Была категория", value=channel.category.name, inline=True)

        # Определение того, кто удалил канал через Audit Log
        if guild.me.guild_permissions.view_audit_log:
            await asyncio.sleep(0.6)
            try:
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.channel_delete):
                    if entry.target and entry.target.id == channel.id:
                        embed.add_field(name="👤 Удалил", value=f"{entry.user.mention} ({entry.user})", inline=False)
                        if entry.reason:
                            embed.add_field(name="Причина", value=entry.reason, inline=False)
                        break
            except Exception:
                pass

        embed.set_footer(text=f"ID канала: {channel.id}")
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
                title="⚙️ Канал обновлен",
                description="\n".join(changes),
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Канал", value=after.mention, inline=False)
            embed.add_field(name="Тип", value=self.format_channel_type(after), inline=True)

            if guild.me.guild_permissions.view_audit_log:
                await asyncio.sleep(0.6)
                try:
                    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.channel_update):
                        if entry.target and entry.target.id == after.id:
                            embed.add_field(name="👤 Изменил", value=f"{entry.user.mention} ({entry.user})", inline=False)
                            break
                except Exception:
                    pass

            embed.set_footer(text=f"ID канала: {after.id}")
            await self.send_log(guild, embed)

    # ==========================================
    # 6. РОЛИ (СОЗДАНИЕ / УДАЛЕНИЕ / ИЗМЕНЕНИЕ)
    # ==========================================

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        guild = role.guild
        embed = discord.Embed(
            title="🏷️ Роль создана",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Роль", value=f"{role.mention} ({role.name})", inline=False)

        if guild.me.guild_permissions.view_audit_log:
            await asyncio.sleep(0.6)
            try:
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.role_create):
                    if entry.target and entry.target.id == role.id:
                        embed.add_field(name="👤 Создал", value=f"{entry.user.mention} ({entry.user})", inline=False)
                        break
            except Exception:
                pass

        embed.set_footer(text=f"ID роли: {role.id}")
        await self.send_log(guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        guild = role.guild
        embed = discord.Embed(
            title="🗑️ Роль удалена",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Имя роли", value=role.name, inline=False)

        if guild.me.guild_permissions.view_audit_log:
            await asyncio.sleep(0.6)
            try:
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.role_delete):
                    if entry.target and entry.target.id == role.id:
                        embed.add_field(name="👤 Удалил", value=f"{entry.user.mention} ({entry.user})", inline=False)
                        break
            except Exception:
                pass

        embed.set_footer(text=f"ID роли: {role.id}")
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
                title="✏️ Роль обновлена",
                description="\n".join(changes),
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Роль", value=after.mention, inline=False)

            if guild.me.guild_permissions.view_audit_log:
                await asyncio.sleep(0.6)
                try:
                    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.role_update):
                        if entry.target and entry.target.id == after.id:
                            embed.add_field(name="👤 Изменил", value=f"{entry.user.mention} ({entry.user})", inline=False)
                            break
                except Exception:
                    pass

            embed.set_footer(text=f"ID роли: {after.id}")
            await self.send_log(guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerLogging(bot))
