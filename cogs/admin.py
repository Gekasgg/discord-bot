import discord
from discord import app_commands, ui
from discord.ext import commands
from config import config_manager
from cogs.tickets import TicketLauncherView


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


class EditTicketFormModal(ui.Modal, title="Форма обращения (5 строк)"):
    """Модальное окно для настройки названий 5 строк при создании тикета."""

    def __init__(self, settings: dict):
        super().__init__()
        self.f1_label = ui.TextInput(
            label="Строка 1 (до 45 симв.)",
            default=(settings.get("ticket_field1_label") or "1. Ваш никнейм")[:45],
            required=True,
            max_length=45
        )
        self.add_item(self.f1_label)

        self.f2_label = ui.TextInput(
            label="Строка 2 (до 45 симв.)",
            default=(settings.get("ticket_field2_label") or "2. Ваш ID / SteamID")[:45],
            required=True,
            max_length=45
        )
        self.add_item(self.f2_label)

        self.f3_label = ui.TextInput(
            label="Строка 3 (до 45 симв.)",
            default=(settings.get("ticket_field3_label") or "3. Тема обращения")[:45],
            required=True,
            max_length=45
        )
        self.add_item(self.f3_label)

        self.f4_label = ui.TextInput(
            label="Строка 4 (до 45 симв.)",
            default=(settings.get("ticket_field4_label") or "4. Описание проблемы")[:45],
            required=True,
            max_length=45
        )
        self.add_item(self.f4_label)

        self.f5_label = ui.TextInput(
            label="Строка 5 (до 45 симв.)",
            default=(settings.get("ticket_field5_label") or "5. Доказательства / Ссылки")[:45],
            required=True,
            max_length=45
        )
        self.add_item(self.f5_label)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        config_manager.set_guild_value(guild_id, "ticket_field1_label", self.f1_label.value.strip())
        config_manager.set_guild_value(guild_id, "ticket_field2_label", self.f2_label.value.strip())
        config_manager.set_guild_value(guild_id, "ticket_field3_label", self.f3_label.value.strip())
        config_manager.set_guild_value(guild_id, "ticket_field4_label", self.f4_label.value.strip())
        config_manager.set_guild_value(guild_id, "ticket_field5_label", self.f5_label.value.strip())

        embed = discord.Embed(
            title="✅ Названия 5 строк тикета обновлены!",
            description=(
                f"1️⃣ **Строка 1:** `{self.f1_label.value}`\n"
                f"2️⃣ **Строка 2:** `{self.f2_label.value}`\n"
                f"3️⃣ **Строка 3:** `{self.f3_label.value}`\n"
                f"4️⃣ **Строка 4:** `{self.f4_label.value}`\n"
                f"5️⃣ **Строка 5:** `{self.f5_label.value}`\n\n"
                "Теперь при нажатии на кнопку создания обращения пользователи увидят ровно эти 5 строк."
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
        name="bot-status",
        description="Проверить текущие настройки бота на этом сервере"
    )
    @app_commands.default_permissions(administrator=True)
    async def cmd_status(self, interaction: discord.Interaction):
        """Статус и настройки бота."""
        guild = interaction.guild
        settings = config_manager.get_guild(guild.id)

        log_ch = guild.get_channel(settings.get("log_channel_id")) if settings.get("log_channel_id") else None
        ticket_cat = guild.get_channel(settings.get("ticket_category_id")) if settings.get("ticket_category_id") else None
        ticket_log = guild.get_channel(settings.get("ticket_log_channel_id")) if settings.get("ticket_log_channel_id") else None
        role = guild.get_role(settings.get("support_role_id")) if settings.get("support_role_id") else None

        voice_hub = guild.get_channel(settings.get("voice_hub_channel_id")) if settings.get("voice_hub_channel_id") else None

        embed = discord.Embed(
            title=f"📊 Настройки бота для {guild.name}",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Канал логов аудита", value=log_ch.mention if log_ch else "❌ Не настроен (/set-log-channel)", inline=False)
        embed.add_field(name="Категория тикетов", value=ticket_cat.name if ticket_cat else "❌ Не настроена (/setup-tickets)", inline=True)
        embed.add_field(name="Роль поддержки", value=role.mention if role else "Не указана", inline=True)
        embed.add_field(name="Канал логов тикетов", value=ticket_log.mention if ticket_log else "По умолчанию (канал логов)", inline=True)
        embed.add_field(name="Хаб создания войсов", value=voice_hub.mention if voice_hub else "❌ Не настроен (/setup-voice)", inline=True)
        embed.add_field(name="Всего создано тикетов", value=str(settings.get("ticket_counter", 0)), inline=True)
        embed.add_field(name="Пинг бота", value=f"{round(self.bot.latency * 1000)} мс", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="help",
        description="Справка по командам и возможностям бота"
    )
    async def cmd_help(self, interaction: discord.Interaction):
        """Информационная справка."""
        embed = discord.Embed(
            title="📖 Справка по боту",
            description="Бот оснащен автоматическим аудитом сервера, тикет-системой и динамическими голосовыми каналами.",
            color=discord.Color.blurple()
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
            name="📜 Логи сервера и аудит",
            value=(
                "`/set-log-channel` — установить канал аудита сервера\n"
                "`/bot-status` — посмотреть текущую конфигурацию сервера\n"
                "`!sync` — принудительно обновить слэш-команды в чате"
            ),
            inline=False
        )
        embed.add_field(
            name="🎫 Возможности тикет-системы",
            value=(
                "• Полностью настраиваемые окно создания и приветствие\n"
                "• Приватный доступ только автору и роли поддержки\n"
                "• Сохранение полного транскрипта переписки (`.txt`) при закрытии\n"
                "• Кнопка «Принять тикет» для модераторов"
            ),
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCommands(bot))
