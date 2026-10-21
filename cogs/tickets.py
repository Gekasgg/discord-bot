import io
import discord
from discord.ext import commands
from discord import ui
import datetime
from config import config_manager


class TicketModal(ui.Modal):
    def __init__(self, guild_settings: dict | None = None):
        settings = guild_settings or {}
        modal_title = settings.get("ticket_modal_title") or "Создание нового обращения"
        super().__init__(title=modal_title[:45])

        field1_label = settings.get("ticket_field1_label") or "Тема обращения"
        field1_ph = settings.get("ticket_field1_placeholder") or "Кратко укажите суть (например, вопрос, жалоба...)"

        field2_label = settings.get("ticket_field2_label") or "Описание вопроса или проблемы"
        field2_ph = settings.get("ticket_field2_placeholder") or "Опишите подробно, с чем вам требуется помощь..."

        self.topic = ui.TextInput(
            label=field1_label[:45],
            placeholder=field1_ph[:100],
            required=True,
            max_length=100
        )
        self.add_item(self.topic)

        self.details = ui.TextInput(
            label=field2_label[:45],
            placeholder=field2_ph[:100],
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1500
        )
        self.add_item(self.details)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Ошибка: действие возможно только на сервере.", ephemeral=True)
            return

        settings = config_manager.get_guild(guild.id)

        # Проверка, нет ли уже открытого тикета у пользователя
        active = settings.get("active_tickets", {})
        for cid_str, info in active.items():
            if info.get("author_id") == interaction.user.id:
                existing_ch = guild.get_channel(int(cid_str))
                if existing_ch:
                    await interaction.followup.send(
                        f"⚠️ У вас уже есть открытый тикет: {existing_ch.mention}. Пожалуйста, используйте его.",
                        ephemeral=True
                    )
                    return

        # Получение категории
        category = None
        cat_id = settings.get("ticket_category_id")
        if cat_id:
            category = guild.get_channel(cat_id)
            if not isinstance(category, discord.CategoryChannel):
                category = None

        # Определение роли поддержки
        support_role = None
        role_id = settings.get("support_role_id")
        if role_id:
            support_role = guild.get_role(role_id)

        # Настройка прав доступа
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )
        }

        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )

        # Номер тикета
        num = config_manager.increment_ticket_counter(guild.id)
        ticket_name = f"тикет-{num:04d}"

        try:
            channel = await guild.create_text_channel(
                name=ticket_name,
                category=category,
                overwrites=overwrites,
                topic=f"Тикет #{num} | {interaction.user} | {self.topic.value[:50]}"
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ У бота нет прав на создание текстового канала (`Manage Channels`). Проверьте права бота.",
                ephemeral=True
            )
            return

        config_manager.register_ticket(
            guild_id=guild.id,
            channel_id=channel.id,
            author_id=interaction.user.id,
            created_at=discord.utils.utcnow().isoformat()
        )

        # Кастомизируемый заголовок и текст внутри тикета
        welcome_title_tpl = settings.get("ticket_welcome_title") or "📩 Тикет #{num:04d}"
        try:
            welcome_title = welcome_title_tpl.format(num=num)
        except Exception:
            welcome_title = f"📩 Тикет #{num:04d}"

        welcome_text_tpl = settings.get("ticket_welcome_text") or (
            "Здравствуйте! Команда поддержки скоро ответит вам.\n"
            "Пожалуйста, опишите все детали и ожидайте ответа."
        )
        try:
            welcome_text = welcome_text_tpl.format(user=interaction.user.mention, num=num)
        except Exception:
            welcome_text = welcome_text_tpl

        # Эмбед в созданный канал
        embed = discord.Embed(
            title=welcome_title,
            description=welcome_text,
            color=discord.Color.brand_green(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
        embed.add_field(name="Автор", value=interaction.user.mention, inline=True)
        embed.add_field(name=self.topic.label, value=self.topic.value, inline=False)
        embed.add_field(name=self.details.label, value=self.details.value, inline=False)
        embed.set_footer(text="Используйте кнопки ниже для управления тикетом")

        mention_text = f"{interaction.user.mention}"
        if support_role:
            mention_text += f" | {support_role.mention}"

        await channel.send(content=mention_text, embed=embed, view=TicketControlView())

        await interaction.followup.send(
            f"✅ Ваш тикет успешно создан: {channel.mention}",
            ephemeral=True
        )


class TicketCloseConfirmView(ui.View):
    """Подтверждение закрытия тикета."""

    def __init__(self, author: discord.Member | discord.User):
        super().__init__(timeout=60)
        self.author = author

    @ui.button(label="Да, закрыть и удалить", style=discord.ButtonStyle.danger, emoji="🔒")
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        channel = interaction.channel
        guild = interaction.guild

        if not isinstance(channel, discord.TextChannel) or not guild:
            return

        # Генерируем транскрипт
        transcript_text = f"=== Транскрипт тикета: {channel.name} ===\n"
        transcript_text += f"Сервер: {guild.name} ({guild.id})\n"
        transcript_text += f"Дата закрытия: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        transcript_text += f"Закрыл: {interaction.user} ({interaction.user.id})\n"
        transcript_text += "========================================\n\n"

        messages = [msg async for msg in channel.history(limit=500, oldest_first=True)]
        for msg in messages:
            ts = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
            author_str = f"{msg.author} ({msg.author.id})"
            content = msg.content
            if msg.attachments:
                att_list = " [Вложения: " + ", ".join([a.url for a in msg.attachments]) + "]"
                content += att_list
            transcript_text += f"[{ts}] {author_str}: {content}\n"

        file_bytes = io.BytesIO(transcript_text.encode("utf-8"))
        transcript_file = discord.File(file_bytes, filename=f"transcript-{channel.name}.txt")

        # Отправка транскрипта в лог тикетов / лог сервер
        settings = config_manager.get_guild(guild.id)
        log_cid = settings.get("ticket_log_channel_id") or settings.get("log_channel_id")
        if log_cid:
            log_channel = guild.get_channel(log_cid)
            if isinstance(log_channel, discord.TextChannel):
                log_embed = discord.Embed(
                    title=f"📁 Тикет закрыт: {channel.name}",
                    description=f"Закрыл: {interaction.user.mention} ({interaction.user.id})",
                    color=discord.Color.dark_grey(),
                    timestamp=discord.utils.utcnow()
                )
                try:
                    await log_channel.send(embed=log_embed, file=discord.File(io.BytesIO(transcript_text.encode("utf-8")), filename=f"transcript-{channel.name}.txt"))
                except Exception as e:
                    print(f"[Ticket Error] Не удалось отправить транскрипт в лог: {e}")

        # Попытка отправить транскрипт создателю в ЛС
        ticket_info = config_manager.get_ticket_info(guild.id, channel.id)
        if ticket_info:
            author_id = ticket_info.get("author_id")
            if author_id:
                member = guild.get_member(author_id)
                if member:
                    try:
                        dm_embed = discord.Embed(
                            title=f"Ваш тикет `{channel.name}` на сервере {guild.name} был закрыт",
                            description="Транскрипт переписки прикреплен к этому сообщению.",
                            color=discord.Color.blue(),
                            timestamp=discord.utils.utcnow()
                        )
                        dm_file = discord.File(io.BytesIO(transcript_text.encode("utf-8")), filename=f"transcript-{channel.name}.txt")
                        await member.send(embed=dm_embed, file=dm_file)
                    except Exception:
                        pass  # ЛС может быть закрыто

        config_manager.remove_ticket(guild.id, channel.id)

        embed_closing = discord.Embed(
            description="⌛ Канал будет удален через 5 секунд...",
            color=discord.Color.red()
        )
        await channel.send(embed=embed_closing)

        import asyncio
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Тикет закрыт пользователем {interaction.user}")
        except Exception as e:
            print(f"[Ticket Error] Не удалось удалить канал {channel.name}: {e}")

    @ui.button(label="Отмена", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="❌ Закрытие тикета отменено.", view=None)


class TicketControlView(ui.View):
    """Постоянная панель управления внутри созданного тикета."""

    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Закрыть", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket_close_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        confirm_view = TicketCloseConfirmView(interaction.user)
        await interaction.response.send_message(
            "❓ Вы уверены, что хотите закрыть этот тикет? Будет сохранен транскрипт и канал удалится.",
            view=confirm_view,
            ephemeral=False
        )

    @ui.button(label="Транскрипт", style=discord.ButtonStyle.secondary, emoji="📑", custom_id="ticket_transcript_btn")
    async def get_transcript(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        channel = interaction.channel
        guild = interaction.guild
        if not isinstance(channel, discord.TextChannel) or not guild:
            return

        text = f"=== Транскрипт тикета: {channel.name} ===\n"
        messages = [msg async for msg in channel.history(limit=500, oldest_first=True)]
        for msg in messages:
            ts = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
            text += f"[{ts}] {msg.author}: {msg.content}\n"

        file_bytes = io.BytesIO(text.encode("utf-8"))
        file = discord.File(file_bytes, filename=f"transcript-{channel.name}.txt")

        await interaction.followup.send("📄 Вот текущий транскрипт переписки:", file=file, ephemeral=True)

    @ui.button(label="Принять тикет", style=discord.ButtonStyle.primary, emoji="🙋‍♂️", custom_id="ticket_claim_btn")
    async def claim_ticket(self, interaction: discord.Interaction, button: ui.Button):
        guild = interaction.guild
        channel = interaction.channel
        if not guild or not channel:
            return

        settings = config_manager.get_guild(guild.id)
        role_id = settings.get("support_role_id")
        is_staff = interaction.user.guild_permissions.administrator
        if role_id and interaction.guild.get_role(role_id) in interaction.user.roles:
            is_staff = True

        if not is_staff:
            await interaction.response.send_message("❌ Только сотрудники поддержки или администраторы могут принять тикет.", ephemeral=True)
            return

        config_manager.claim_ticket(guild.id, channel.id, interaction.user.id)
        button.disabled = True
        button.label = f"Принят: {interaction.user.display_name}"
        await interaction.response.edit_message(view=self)

        embed = discord.Embed(
            description=f"🙋‍♂️ Модератор {interaction.user.mention} взял обращение в работу.",
            color=discord.Color.green()
        )
        await channel.send(embed=embed)


class TicketLauncherView(ui.View):
    """Постоянная кнопка в публичном канале для создания тикетов."""

    def __init__(self, button_label: str = "Создать тикет"):
        super().__init__(timeout=None)
        if button_label:
            for child in self.children:
                if isinstance(child, ui.Button) and child.custom_id == "ticket_launcher_create_btn":
                    child.label = button_label
                    break

    @ui.button(
        label="Создать тикет",
        style=discord.ButtonStyle.success,
        emoji="📩",
        custom_id="ticket_launcher_create_btn"
    )
    async def create_ticket(self, interaction: discord.Interaction, button: ui.Button):
        settings = config_manager.get_guild(interaction.guild_id) if interaction.guild_id else {}
        await interaction.response.send_modal(TicketModal(settings))


class TicketsCog(commands.Cog):
    """Ког управления тикет-системой."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))
