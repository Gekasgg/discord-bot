import discord
from discord import app_commands, ui
from discord.ext import commands
from config import config_manager
from cogs.tickets import TicketLauncherView
try:
    from cogs.giveaways import giveaways_manager
except ImportError:
    giveaways_manager = None


class EditPanelModal(ui.Modal, title="Настройка текста панели тикетов"):
    def __init__(self, target_message: discord.Message):
        super().__init__()
        self.target_message = target_message

        current_title = "🎫 Поддержка и обратная связь"
        current_desc = (
            "Возникли вопросы, проблемы или предложения?\n"
            "Нажмите на зелёную кнопку ниже, чтобы создать приватное обращение.\n\n"
            "• Наши модераторы и поддержка ответят вам в ближайшее время.\n"
            "• Пожалуйста, подробно заполните тему и суть обращения при открытии."
        )
        current_footer = "Служба поддержки сервера"
        current_btn = "Создать тикет"

        if target_message.embeds:
            emb = target_message.embeds[0]
            if emb.title:
                current_title = emb.title
            if emb.description:
                current_desc = emb.description
            if emb.footer and emb.footer.text:
                current_footer = emb.footer.text

        for row in target_message.components:
            for item in getattr(row, "children", []):
                if getattr(item, "custom_id", "") == "ticket_launcher_create_btn" and getattr(item, "label", None):
                    current_btn = item.label

        self.panel_title = ui.TextInput(
            label="Заголовок панели",
            default=current_title[:200],
            required=True,
            max_length=256
        )
        self.add_item(self.panel_title)

        self.panel_desc = ui.TextInput(
            label="Текст описания (переносы строк работают)",
            style=discord.TextStyle.paragraph,
            default=current_desc[:3800],
            required=True,
            max_length=4000
        )
        self.add_item(self.panel_desc)

        self.panel_footer = ui.TextInput(
            label="Нижняя подпись (footer)",
            default=current_footer[:100],
            required=False,
            max_length=200
        )
        self.add_item(self.panel_footer)

        self.button_label = ui.TextInput(
            label="Текст на кнопке",
            default=current_btn[:50],
            required=False,
            max_length=80
        )
        self.add_item(self.button_label)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(
            title=self.panel_title.value,
            description=self.panel_desc.value,
            color=discord.Color.blue()
        )
        if self.panel_footer.value:
            icon_url = interaction.guild.icon.url if interaction.guild and interaction.guild.icon else None
            embed.set_footer(text=self.panel_footer.value, icon_url=icon_url)

        new_button_label = self.button_label.value.strip() or "Создать тикет"
        view = TicketLauncherView(button_label=new_button_label)

        try:
            await self.target_message.edit(embed=embed, view=view)
            await interaction.followup.send("✅ Текст панели тикетов успешно обновлен!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка при изменении панели: {e}", ephemeral=True)


class EditTicketFormModal(ui.Modal, title="Форма создания обращения"):
    """Модальное окно для настройки полей ввода при создании тикета."""

    def __init__(self, settings: dict):
        super().__init__()
        self.modal_title_input = ui.TextInput(
            label="Заголовок всплывающего окна (до 45)",
            default=(settings.get("ticket_modal_title") or "Создание нового обращения")[:45],
            required=True,
            max_length=45
        )
        self.add_item(self.modal_title_input)

        self.f1_label = ui.TextInput(
            label="Название 1-го поля (до 45)",
            default=(settings.get("ticket_field1_label") or "Тема обращения")[:45],
            required=True,
            max_length=45
        )
        self.add_item(self.f1_label)

        self.f1_ph = ui.TextInput(
            label="Подсказка внутри 1-го поля",
            default=(settings.get("ticket_field1_placeholder") or "Кратко укажите суть (например, вопрос, жалоба...)")[:100],
            required=False,
            max_length=100
        )
        self.add_item(self.f1_ph)

        self.f2_label = ui.TextInput(
            label="Название 2-го поля (до 45)",
            default=(settings.get("ticket_field2_label") or "Описание вопроса или проблемы")[:45],
            required=True,
            max_length=45
        )
        self.add_item(self.f2_label)

        self.f2_ph = ui.TextInput(
            label="Подсказка внутри 2-го поля",
            default=(settings.get("ticket_field2_placeholder") or "Опишите подробно, с чем вам требуется помощь...")[:100],
            required=False,
            max_length=100
        )
        self.add_item(self.f2_ph)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        config_manager.set_guild_value(guild_id, "ticket_modal_title", self.modal_title_input.value.strip())
        config_manager.set_guild_value(guild_id, "ticket_field1_label", self.f1_label.value.strip())
        config_manager.set_guild_value(guild_id, "ticket_field1_placeholder", self.f1_ph.value.strip())
        config_manager.set_guild_value(guild_id, "ticket_field2_label", self.f2_label.value.strip())
        config_manager.set_guild_value(guild_id, "ticket_field2_placeholder", self.f2_ph.value.strip())

        embed = discord.Embed(
            title="✅ Окно создания тикета обновлено!",
            description=(
                f"**Заголовок окна:** `{self.modal_title_input.value}`\n"
                f"**Поле 1:** `{self.f1_label.value}` (подсказка: *{self.f1_ph.value or 'нет'}*)\n"
                f"**Поле 2:** `{self.f2_label.value}` (подсказка: *{self.f2_ph.value or 'нет'}*)\n\n"
                "Теперь при нажатии на кнопку создания обращения пользователи будут видеть эти поля."
            ),
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class EditTicketWelcomeModal(ui.Modal, title="Приветствие внутри тикета"):
    """Модальное окно для настройки текста приветствия внутри созданного тикета."""

    def __init__(self, settings: dict):
        super().__init__()
        self.welcome_title = ui.TextInput(
            label="Заголовок тикета ({num} - номер)",
            default=(settings.get("ticket_welcome_title") or "📩 Тикет #{num:04d}")[:100],
            required=True,
            max_length=200
        )
        self.add_item(self.welcome_title)

        self.welcome_text = ui.TextInput(
            label="Текст приветствия ({user} - автор)",
            style=discord.TextStyle.paragraph,
            default=(settings.get("ticket_welcome_text") or (
                "Здравствуйте! Команда поддержки скоро ответит вам.\n"
                "Пожалуйста, опишите все детали и ожидайте ответа."
            ))[:1500],
            required=True,
            max_length=2000
        )
        self.add_item(self.welcome_text)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        config_manager.set_guild_value(guild_id, "ticket_welcome_title", self.welcome_title.value.strip())
        config_manager.set_guild_value(guild_id, "ticket_welcome_text", self.welcome_text.value.strip())

        embed = discord.Embed(
            title="✅ Приветствие внутри тикета обновлено!",
            description=(
                f"**Заголовок:** `{self.welcome_title.value}`\n\n"
                f"**Текст приветствия:**\n{self.welcome_text.value}\n\n"
                "Все новые создаваемые тикеты будут открываться с этим приветственным сообщением."
            ),
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class AdminCommands(commands.Cog):
    """Административные слэш-команды для настройки логов и тикетов."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="set-log-channel",
        description="Установить канал для логирования всех действий на сервере"
    )
    @app_commands.default_permissions(administrator=True)
    async def set_log_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        """Настройка канала аудита сервера."""
        config_manager.set_guild_value(interaction.guild_id, "log_channel_id", channel.id)

        embed = discord.Embed(
            title="✅ Канал логов установлен",
            description=f"Все системные события сервера теперь будут отправляться в канал {channel.mention}.",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text="Убедитесь, что у бота есть права на отправку сообщений в этот канал.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="setup-tickets",
        description="Настроить тикет-систему и отправить панель с кнопкой создания обращения"
    )
    @app_commands.describe(
        channel_for_panel="Канал, куда бот отправит сообщение с кнопкой",
        category="Категория каналов, в которой будут создаваться тикеты",
        support_role="Роль сотрудников поддержки / модераторов (опционально)",
        ticket_log_channel="Канал для логов и транскриптов закрытых тикетов (опционально)",
        panel_title="Свой заголовок панели (опционально)",
        panel_description="Свой текст описания (опционально, используйте \\n для переноса строк)",
        button_text="Своя надпись на кнопке (по умолчанию 'Создать тикет')",
        panel_footer="Нижняя подпись в панели (опционально)"
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_tickets(
        self,
        interaction: discord.Interaction,
        channel_for_panel: discord.TextChannel,
        category: discord.CategoryChannel,
        support_role: discord.Role | None = None,
        ticket_log_channel: discord.TextChannel | None = None,
        panel_title: str | None = None,
        panel_description: str | None = None,
        button_text: str | None = None,
        panel_footer: str | None = None
    ):
        """Развертывание панели тикетов."""
        guild_id = interaction.guild_id
        config_manager.set_guild_value(guild_id, "ticket_category_id", category.id)

        if support_role:
            config_manager.set_guild_value(guild_id, "support_role_id", support_role.id)
        if ticket_log_channel:
            config_manager.set_guild_value(guild_id, "ticket_log_channel_id", ticket_log_channel.id)

        title = panel_title or "🎫 Поддержка и обратная связь"
        desc = panel_description.replace("\\n", "\n") if panel_description else (
            "Возникли вопросы, проблемы или предложения?\n"
            "Нажмите на зелёную кнопку ниже, чтобы создать приватное обращение.\n\n"
            "• Наши модераторы и поддержка ответят вам в ближайшее время.\n"
            "• Пожалуйста, подробно заполните тему и суть обращения при открытии."
        )
        footer = panel_footer or "Служба поддержки сервера"
        btn_label = button_text or "Создать тикет"

        panel_embed = discord.Embed(
            title=title,
            description=desc,
            color=discord.Color.blue()
        )
        panel_embed.set_footer(text=footer, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)

        try:
            await channel_for_panel.send(embed=panel_embed, view=TicketLauncherView(button_label=btn_label))
        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ Ошибка: бот не может писать в канал {channel_for_panel.mention}. Проверьте права бота.",
                ephemeral=True
            )
            return

        response_embed = discord.Embed(
            title="🎉 Тикет-система успешно настроена!",
            color=discord.Color.green()
        )
        response_embed.add_field(name="Панель отправлена в", value=channel_for_panel.mention, inline=False)
        response_embed.add_field(name="Категория для новых тикетов", value=category.name, inline=True)
        response_embed.add_field(name="Роль поддержки", value=support_role.mention if support_role else "Не указана (доступна только админам)", inline=True)
        if ticket_log_channel:
            response_embed.add_field(name="Лог закрытых тикетов", value=ticket_log_channel.mention, inline=True)

        await interaction.response.send_message(embed=response_embed, ephemeral=True)

    @app_commands.command(
        name="edit-ticket-panel",
        description="Открыть форму и изменить текст уже отправленной панели тикетов"
    )
    @app_commands.describe(
        channel="Канал, где находится сообщение с панелью тикетов",
        message_id="ID сообщения панели (ПКМ по сообщению -> Копировать ID)"
    )
    @app_commands.default_permissions(administrator=True)
    async def edit_ticket_panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message_id: str
    ):
        """Интерактивное редактирование панели через всплывающее окно."""
        try:
            msg_id_int = int(message_id.strip())
            msg = await channel.fetch_message(msg_id_int)
        except (ValueError, discord.NotFound):
            await interaction.response.send_message("❌ Сообщение с таким ID не найдено в указанном канале.", ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.response.send_message("❌ У бота нет прав для просмотра сообщений в этом канале.", ephemeral=True)
            return

        if msg.author.id != self.bot.user.id:
            await interaction.response.send_message("❌ Это сообщение отправлено не этим ботом, его нельзя отредактировать.", ephemeral=True)
            return

        await interaction.response.send_modal(EditPanelModal(msg))

    @app_commands.command(
        name="edit-ticket-form",
        description="Настроить поля и вопросы во всплывающем окне создания тикета"
    )
    @app_commands.default_permissions(administrator=True)
    async def edit_ticket_form(self, interaction: discord.Interaction):
        """Интерактивная настройка полей формы создания тикета."""
        settings = config_manager.get_guild(interaction.guild_id)
        await interaction.response.send_modal(EditTicketFormModal(settings))

    @app_commands.command(
        name="edit-ticket-welcome",
        description="Настроить приветственный текст и заголовок внутри созданного тикета"
    )
    @app_commands.default_permissions(administrator=True)
    async def edit_ticket_welcome(self, interaction: discord.Interaction):
        """Интерактивная настройка приветствия внутри созданного тикета."""
        settings = config_manager.get_guild(interaction.guild_id)
        await interaction.response.send_modal(EditTicketWelcomeModal(settings))

    @app_commands.command(
        name="set-ticket-log-channel",
        description="Установить отдельный канал для логов тикетов и транскриптов"
    )
    @app_commands.default_permissions(administrator=True)
    async def set_ticket_log_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        """Установка отдельного канала для логов тикетов."""
        config_manager.set_guild_value(interaction.guild_id, "ticket_log_channel_id", channel.id)

        embed = discord.Embed(
            title="✅ Канал логов тикетов установлен",
            description=f"Транскрипты закрытых тикетов будут сохраняться в {channel.mention}.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="test-log",
        description="Проверить отправку логов в настроенный канал логов"
    )
    @app_commands.default_permissions(administrator=True)
    async def test_log(self, interaction: discord.Interaction):
        """Тестовая отправка лога для проверки канала и прав."""
        guild = interaction.guild
        settings = config_manager.get_guild(guild.id)
        cid = settings.get("log_channel_id")
        if not cid:
            await interaction.response.send_message(
                "❌ Канал логов не настроен! Используйте команду `/set-log-channel` чтобы назначить канал.",
                ephemeral=True
            )
            return

        channel = guild.get_channel(cid)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(cid)
            except Exception:
                channel = None

        if not channel:
            await interaction.response.send_message(
                f"❌ Настроенный канал логов (ID: `{cid}`) не найден на сервере. Возможно, он был удален.",
                ephemeral=True
            )
            return

        perms = channel.permissions_for(guild.me)
        if not perms.send_messages or not perms.embed_links:
            await interaction.response.send_message(
                f"⚠️ У бота нет необходимых прав в канале {channel.mention}:\n"
                f"• Отправка сообщений (Send Messages): {'✅' if perms.send_messages else '❌'}\n"
                f"• Прикрепление ссылок/эмбедов (Embed Links): {'✅' if perms.embed_links else '❌'}",
                ephemeral=True
            )
            return

        test_embed = discord.Embed(
            title="🧪 Проверка системы логирования",
            description=(
                f"✅ **Канал логов работает исправно!**\n\n"
                f"• **Канал:** {channel.mention}\n"
                f"• **Сервер:** {guild.name}\n"
                f"• **Инициатор проверки:** {interaction.user.mention}\n"
                f"• **Намерения участников (Server Members Intent):** {'✅ Включены' if self.bot.intents.members else '❌ Выключены'}\n\n"
                f"*Все системные события (вход/выход участников, роли, сообщения, войсы) отправляются в этот канал.*"
            ),
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )
        test_embed.set_footer(text="Тестовый лог системы аудита")

        try:
            await channel.send(embed=test_embed)
            await interaction.response.send_message(
                f"✅ Тестовый лог успешно отправлен в канал {channel.mention}!",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Ошибка при отправке тестового лога в канал {channel.mention}: {e}",
                ephemeral=True
            )

    @app_commands.command(
        name="set-autorole",
        description="Настроить роль, которая будет автоматически выдаваться новым участникам при входе"
    )
    @app_commands.describe(
        role="Роль для автоматической выдачи (оставьте пустым, чтобы отключить автовыдачу)"
    )
    @app_commands.default_permissions(administrator=True)
    async def set_autorole(
        self,
        interaction: discord.Interaction,
        role: discord.Role | None = None
    ):
        """Настройка или отключение авто-роли при входе."""
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        if role is None:
            config_manager.set_guild_value(guild.id, "auto_role_id", None)
            embed = discord.Embed(
                title="🚫 Автовыдача роли отключена",
                description="Новым участникам больше не будет автоматически выдаваться роль при входе.",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            await interaction.response.send_message(embed=embed)
            return

        if role.is_default():
            await interaction.response.send_message("❌ Нельзя назначить роль `@everyone` в качестве авто-роли.", ephemeral=True)
            return

        if role.managed:
            await interaction.response.send_message("❌ Эта роль управляется интеграцией или ботом и не может выдаваться вручную.", ephemeral=True)
            return

        warning_text = ""
        if guild.me.top_role <= role:
            warning_text = (
                f"\n\n⚠️ **Обратите внимание:** Роль {role.mention} находится на том же уровне или выше высшей роли бота (`{guild.me.top_role.name}`).\n"
                "Чтобы бот мог успешно выдавать её новым участникам, поднимите роль бота выше этой роли в **Настройки сервера ➔ Роли**."
            )

        config_manager.set_guild_value(guild.id, "auto_role_id", role.id)

        embed = discord.Embed(
            title="✅ Автовыдача роли настроена",
            description=f"Каждый новый участник при заходе на сервер автоматически получит роль {role.mention}.{warning_text}",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text="Для отключения используйте /set-autorole без указания роли.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="clear",
        description="Быстрая очистка чата от сообщений с поддержкой фильтров (боты, пользователь, текст)"
    )
    @app_commands.describe(
        amount="Количество последних сообщений для проверки и удаления (от 1 до 100)",
        user="Удалять сообщения только от этого пользователя (опционально)",
        only_bots="Удалять сообщения только от ботов и вебхуков (быстрая чистка спама)",
        contains="Удалять только сообщения, содержащие определенный текст (опционально)"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def cmd_clear(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100] = 10,
        user: discord.Member | None = None,
        only_bots: bool = False,
        contains: str | None = None
    ):
        """Быстрая очистка сообщений в текущем канале."""
        guild = interaction.guild
        channel = interaction.channel
        if not guild or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("❌ Команда доступна только в текстовых каналах сервера.", ephemeral=True)
            return

        # Проверка прав бота в канале
        bot_member = guild.me
        if not channel.permissions_for(bot_member).manage_messages:
            await interaction.response.send_message(
                f"❌ У бота нет права **«Управлять сообщениями» (Manage Messages)** в канале {channel.mention}!",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        def check_msg(m: discord.Message) -> bool:
            if user and m.author.id != user.id:
                return False
            if only_bots and not (m.author.bot or m.webhook_id is not None):
                return False
            if contains and contains.lower() not in (m.content or "").lower():
                return False
            return True

        try:
            # bulk=True автоматически использует быстрое удаление пачкой
            deleted = await channel.purge(limit=amount, check=check_msg, bulk=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Ошибка при удалении сообщений: {e}", ephemeral=True)
            return

        embed = discord.Embed(
            title="🧹 Чат успешно очищен",
            description=f"В канале {channel.mention} удалено **{len(deleted)}** сообщений.",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        if user:
            embed.add_field(name="Фильтр по автору", value=user.mention, inline=True)
        if only_bots:
            embed.add_field(name="Фильтр", value="Только боты и вебхуки", inline=True)
        if contains:
            embed.add_field(name="Фильтр по тексту", value=f"`{contains}`", inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Оповещение в канал логов аудита при наличии
        settings = config_manager.get_guild(guild.id)
        log_cid = settings.get("log_channel_id")
        if log_cid and log_cid != channel.id:
            log_ch = guild.get_channel(log_cid)
            if isinstance(log_ch, discord.TextChannel) and log_ch.permissions_for(bot_member).send_messages:
                audit_embed = discord.Embed(
                    title="🧹 Массовая очистка сообщений (/clear)",
                    description=(
                        f"Модератор {interaction.user.mention} очистил сообщения в канале {channel.mention}.\n"
                        f"Удалено сообщений: **{len(deleted)}**"
                    ),
                    color=discord.Color.orange(),
                    timestamp=discord.utils.utcnow()
                )
                if user:
                    audit_embed.add_field(name="Фильтр по автору", value=user.mention, inline=True)
                if only_bots:
                    audit_embed.add_field(name="Фильтр", value="Только боты/вебхуки", inline=True)
                try:
                    await log_ch.send(embed=audit_embed)
                except Exception:
                    pass

    @app_commands.command(
        name="server-config",
        description="Полная диагностика всех настроек сервера (проверка целостности ролей, каналов и безопасности)"
    )
    @app_commands.default_permissions(administrator=True)
    async def cmd_server_config(self, interaction: discord.Interaction):
        """Полная проверка всех настроек сервера с выявлением сбоев."""
        await self._render_full_server_config(interaction)

    @app_commands.command(
        name="bot-status",
        description="Проверить текущие настройки бота и целостность конфигурации на этом сервере"
    )
    @app_commands.default_permissions(administrator=True)
    async def cmd_status(self, interaction: discord.Interaction):
        """Статус и настройки бота (полный аудит)."""
        await self._render_full_server_config(interaction)

    async def _render_full_server_config(self, interaction: discord.Interaction):
        """Генерирует исчерпывающий отчёт о состоянии сервера и настроек бота."""
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
            return

        settings = config_manager.get_guild(guild.id)
        bot_member = guild.me
        issues_count = 0

        embed = discord.Embed(
            title=f"📋 Полная конфигурация сервера — {guild.name}",
            description="Ниже отображен детальный статус всех систем бота, ролей и проверка на сбои:\n",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow()
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        # 1. АУДИТ И ЛОГИРОВАНИЕ
        log_cid = settings.get("log_channel_id")
        if log_cid:
            log_ch = guild.get_channel(log_cid)
            if log_ch:
                perms = log_ch.permissions_for(bot_member)
                if perms.send_messages and perms.embed_links:
                    log_status = f"✅ Активен: {log_ch.mention}"
                else:
                    issues_count += 1
                    log_status = f"⚠️ {log_ch.mention} (У бота нет прав `Send Messages` / `Embed Links`!)"
            else:
                issues_count += 1
                log_status = f"❌ Канал удален из Discord! (ID: `{log_cid}`) — настройте `/set-log-channel`"
        else:
            log_status = "⚪ Не настроен (`/set-log-channel`)"
        embed.add_field(name="📜 Канал аудита логов", value=log_status, inline=False)

        # 2. АВТОВЫДАЧА РОЛИ (AUTOROLE)
        auto_rid = settings.get("auto_role_id")
        if auto_rid:
            auto_role = guild.get_role(auto_rid)
            if auto_role:
                if bot_member.top_role > auto_role:
                    auto_status = f"✅ Активна: {auto_role.mention} *(выдается новым участникам)*"
                else:
                    issues_count += 1
                    auto_status = f"⚠️ {auto_role.mention} — **Роль бота ниже этой роли!** Бот не сможет её выдать. Поднимите роль бота выше в настройках ролей."
            else:
                issues_count += 1
                auto_status = f"❌ Роль была удалена из настроек Discord! (ID: `{auto_rid}`) — перенастройте `/set-autorole`"
        else:
            auto_status = "⚪ Отключена (`/set-autorole`)"
        embed.add_field(name="🎭 Автовыдача роли новичкам", value=auto_status, inline=False)

        # 3. СИСТЕМА УРОВНЕЙ И РАНГОВ
        levels_enabled = settings.get("levels_enabled", True)
        if levels_enabled:
            lvl_ch_id = settings.get("level_up_channel_id")
            if lvl_ch_id:
                lvl_ch = guild.get_channel(lvl_ch_id)
                lvl_ch_str = lvl_ch.mention if lvl_ch else f"❌ Удален (ID: `{lvl_ch_id}`)"
            else:
                lvl_ch_str = "Текущий канал последнего сообщения"

            replace_mode = settings.get("level_roles_replace", True)
            mode_label = "🔄 Ранги (замена старых ролей)" if replace_mode else "📚 Накопление всех ролей"

            level_roles = settings.get("level_roles", {})
            lvl_roles_lines = []
            if level_roles:
                sorted_tiers = sorted([(int(l), r) for l, r in level_roles.items() if str(l).isdigit()], key=lambda x: x[0])
                for idx, (lvl, rid) in enumerate(sorted_tiers):
                    role = guild.get_role(rid)
                    if replace_mode:
                        if idx + 1 < len(sorted_tiers):
                            next_lvl = sorted_tiers[idx + 1][0]
                            rng_txt = f"Уровни {lvl}–{next_lvl - 1}"
                        else:
                            rng_txt = f"Уровень {lvl}+"
                    else:
                        rng_txt = f"Уровень {lvl}"

                    if role:
                        if bot_member.top_role > role:
                            lvl_roles_lines.append(f"  • ⭐ **{rng_txt}**: {role.mention} ✅")
                        else:
                            issues_count += 1
                            lvl_roles_lines.append(f"  • ⭐ **{rng_txt}**: {role.mention} ⚠️ *(роль бота ниже!)*")
                    else:
                        issues_count += 1
                        lvl_roles_lines.append(f"  • ⭐ **{rng_txt}**: ❌ `Удалена из Discord (ID: {rid})`")
                roles_block = "\n".join(lvl_roles_lines)
            else:
                roles_block = "  *Роли за уровни еще не назначены (`/set-level-role`)*"

            levels_text = (
                f"✅ **Включена** • Режим: **{mode_label}**\n"
                f"📍 Оповещения: {lvl_ch_str}\n"
                f"🎖️ **Настроенные ранги:**\n{roles_block}"
            )
        else:
            levels_text = "❌ Отключена"
        embed.add_field(name="⭐ Система уровней и рангов", value=levels_text, inline=False)

        # 4. РОЗЫГРЫШИ (GIVEAWAYS)
        gw_rid = settings.get("giveaway_role_id")
        gw_role = guild.get_role(gw_rid) if gw_rid else None
        if gw_rid and not gw_role:
            issues_count += 1
            gw_role_str = f"❌ Роль удалена из Discord! (ID: `{gw_rid}`)"
        elif gw_role:
            gw_role_str = f"✅ {gw_role.mention}"
        else:
            gw_role_str = "Только администраторы"

        gw_users = settings.get("giveaway_users", [])
        gw_users_str = ", ".join(f"<@{uid}>" for uid in gw_users) if gw_users else "Нет"
        active_gw_count = len(giveaways_manager.get_guild_giveaways(guild.id, active_only=True)) if giveaways_manager else 0

        gw_text = (
            f"👑 Ведущие розыгрышей: {gw_role_str}\n"
            f"👤 Персональный доступ: {gw_users_str}\n"
            f"🎁 Активных розыгрышей сейчас: **{active_gw_count}** (`/glist`)"
        )
        embed.add_field(name="🎁 Управление розыгрышами", value=gw_text, inline=False)

        # 5. ТИКЕТЫ И ДИНАМИЧЕСКИЕ ВОЙСЫ
        ticket_cat_id = settings.get("ticket_category_id")
        ticket_cat = guild.get_channel(ticket_cat_id) if ticket_cat_id else None
        t_cat_str = ticket_cat.name if ticket_cat else ("❌ Удалена" if ticket_cat_id else "⚪ Не настроена")

        t_role_id = settings.get("support_role_id")
        t_role = guild.get_role(t_role_id) if t_role_id else None
        t_role_str = t_role.mention if t_role else ("❌ Удалена" if t_role_id else "Администраторы")

        t_log_id = settings.get("ticket_log_channel_id")
        t_log = guild.get_channel(t_log_id) if t_log_id else None
        t_log_str = t_log.mention if t_log else "Канал аудита"

        voice_hub_id = settings.get("voice_hub_channel_id")
        voice_hub = guild.get_channel(voice_hub_id) if voice_hub_id else None
        v_hub_str = voice_hub.mention if voice_hub else ("❌ Удален" if voice_hub_id else "⚪ Не настроен")

        systems_text = (
            f"🎫 **Тикеты:** Категория: `{t_cat_str}` | Поддержка: {t_role_str} | Логи: {t_log_str} | Создано: **{settings.get('ticket_counter', 0)}**\n"
            f"🔊 **Войсы:** Хаб «Создать канал»: {v_hub_str}"
        )
        embed.add_field(name="🛠️ Тикеты и Голосовые каналы", value=systems_text, inline=False)

        # 6. АУДИТ БЕЗОПАСНОСТИ СЕРВЕРА (@everyone) И ДОСТУПА К КОМАНДАМ
        sec_warnings = []
        ev_perms = guild.default_role.permissions
        if not ev_perms.use_application_commands:
            issues_count += 1
            sec_warnings.append("⚠️ **У роли @everyone отключено 'Использовать команды приложений'!** Обычные участники не смогут вызывать `/rank` через `/`. (Используйте `!sync` для авто-исправления)")
        if ev_perms.manage_webhooks:
            issues_count += 1
            sec_warnings.append("🚨 **У роли @everyone включено право 'Управлять вебхуками'!** (Любой новичок может создать спам-вебхук!)")
        if getattr(ev_perms, "use_external_apps", False):
            issues_count += 1
            sec_warnings.append("🚨 **У роли @everyone включено право 'Использовать внешние приложения'!** (Риск спама через User-Apps)")
        if ev_perms.mention_everyone:
            issues_count += 1
            sec_warnings.append("⚠️ **У роли @everyone включено 'Упоминание @everyone/@here'!** (Риск массового пинга)")
        if ev_perms.administrator:
            issues_count += 1
            sec_warnings.append("🚨 **КРИТИЧЕСКИ: У роли @everyone включены права Администратора!**")

        if sec_warnings:
            sec_text = "\n".join(sec_warnings) + "\n\n💡 *Настройте эти права в Настройки сервера ➔ Роли ➔ @everyone ➔ Права.*"
            embed.add_field(name="🛡️ Проверка безопасности и доступа (Внимание!)", value=sec_text, inline=False)
        else:
            embed.add_field(
                name="🛡️ Проверка безопасности и доступа",
                value="✅ **Все ключевые уязвимости закрыты, а слэш-команды (`/rank`, `/ранг`) открыты для всех участников.**",
                inline=False
            )

        # Итоги проверки
        ping_ms = round(self.bot.latency * 1000)
        if issues_count == 0:
            status_summary = f"🟢 **Все системы работают штатно, сбоев не обнаружено!** (Пинг: `{ping_ms} мс`)"
        else:
            status_summary = f"🟡 **Обнаружено предупреждений / несоответствий: {issues_count}** (см. ⚠️ и ❌ выше) | Пинг: `{ping_ms} мс`"

        embed.set_footer(text=f"{status_summary} • antugravity bot")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="help",
        description="Справка по командам и возможностям бота"
    )
    async def cmd_help(self, interaction: discord.Interaction):
        """Информационная справка."""
        embed = discord.Embed(
            title="📖 Справка по боту",
            description="Бот оснащен аудитом сервера, тикет-системой, динамическими войсами, автовыдачей ролей, системой уровней и розыгрышами.",
            color=discord.Color.blurple()
        )
        embed.add_field(
            name="🎁 Розыгрыши (Giveaways)",
            value=(
                "`/gstart` — запустить новый розыгрыш (таймер, победители, роль, уровень, текст в ЛС)\n"
                "`/gsetdm <id> <текст>` — настроить/изменить секретный текст или промокод для ЛС победителя\n"
                "`/gend <id>` — досрочно завершить розыгрыш и выбрать победителей\n"
                "`/greroll <id>` — перевыбрать случайных победителей\n"
                "`/gcancel <id>` — отменить активный розыгрыш\n"
                "`/glist` — список всех активных розыгрышей на сервере\n"
                "`/set-giveaway-role [роль]` — назначить роль ведущего розыгрышей\n"
                "`/add-giveaway-manager <user>` — персональный доступ к розыгрышам\n"
                "`/remove-giveaway-manager <user>` — отозвать доступ к розыгрышам\n"
                "`/giveaway-access` — посмотреть, у кого есть права на розыгрыши"
            ),
            inline=False
        )
        embed.add_field(
            name="⭐ Система уровней и активности (Leveling)",
            value=(
                "`/rank [пользователь]` — карточка вашего уровня, опыта и места в топе\n"
                "`/leaderboard` — таблица лидеров сервера по активности и уровням\n"
                "`/set-level-channel [канал]` — канал для поздравлений с новыми уровнями\n"
                "`/set-level-role <уровень> <роль>` — назначить роль за достижение уровня\n"
                "`/remove-level-role <уровень>` — удалить награду ролью\n"
                "`/level-roles` — список настроенных ролей за уровни\n"
                "`/set-level-roles-mode <режим>` — режим ролей: заменять старую роль на новую (ранги) или накапливать\n"
                "`/add-xp` | `/remove-xp` | `/reset-levels` — управление опытом"
            ),
            inline=False
        )
        embed.add_field(
            name="🎭 Автовыдача ролей (Autorole)",
            value=(
                "`/set-autorole [роль]` — настроить автовыдачу роли новым участникам при входе (или отключить, если не указать роль)"
            ),
            inline=False
        )
        embed.add_field(
            name="🔊 Динамические голосовые каналы",
            value=(
                "`/setup-voice` — создать категорию и хаб «➕ Создать канал»\n"
                "`/set-voice-hub` — назначить существующий канал хабом\n"
                "*При заходе в хаб создается отдельный канал с панелью управления в чате!*"
            ),
            inline=False
        )
        embed.add_field(
            name="🛠️ Настройка тикетов",
            value=(
                "`/setup-tickets` — настроить категорию и отправить панель с кнопкой\n"
                "`/edit-ticket-panel` — изменить текст сообщения с кнопкой\n"
                "`/edit-ticket-form` — изменить поля окна создания тикета (тема, описание)\n"
                "`/edit-ticket-welcome` — изменить приветственное сообщение внутри тикета\n"
                "`/set-ticket-log-channel` — канал для сохранения транскриптов тикетов"
            ),
            inline=False
        )
        embed.add_field(
            name="🧹 Модерация и быстрая чистка чата",
            value=(
                "`/clear [amount] [user] [only_bots] [contains]` — быстрая очистка чата от 1 до 100 сообщений (с фильтром ботов/спама)"
            ),
            inline=False
        )
        embed.add_field(
            name="📜 Логи сервера и аудит",
            value=(
                "`/set-log-channel` — установить канал аудита сервера\n"
                "`/test-log` — проверить отправку логов в канал\n"
                "`/server-config` (или `/bot-status`) — **полная диагностика всех настроек сервера, ролей, каналов и уязвимостей**\n"
                "`!sync` — принудительно обновить слэш-команды в чате"
            ),
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCommands(bot))
