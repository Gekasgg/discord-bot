import discord
from discord import app_commands, ui
from discord.ext import commands
from config import config_manager


class VoiceRenameModal(ui.Modal, title="Сменить название канала"):
    channel_name = ui.TextInput(
        label="Новое название канала",
        placeholder="Например: Комната отдыха, Игры...",
        required=True,
        max_length=100
    )

    def __init__(self, channel: discord.VoiceChannel):
        super().__init__()
        self.channel = channel
        self.channel_name.default = channel.name

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        new_name = self.channel_name.value.strip()
        try:
            await self.channel.edit(name=new_name)
            await interaction.followup.send(f"✅ Название канала изменено на **{new_name}**.", ephemeral=True)
        except discord.HTTPException as e:
            if e.code == 50035:
                await interaction.followup.send("⚠️ Слишком частая смена названия (ограничение Discord). Попробуйте чуть позже.", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Ошибка смены названия: {e}", ephemeral=True)


class VoiceLimitModal(ui.Modal, title="Лимит участников"):
    limit_input = ui.TextInput(
        label="Количество мест (0 - без лимита)",
        placeholder="От 0 до 99",
        required=True,
        max_length=2
    )

    def __init__(self, channel: discord.VoiceChannel):
        super().__init__()
        self.channel = channel
        self.limit_input.default = str(channel.user_limit)

    async def on_submit(self, interaction: discord.Interaction):
        val = self.limit_input.value.strip()
        if not val.isdigit() or not (0 <= int(val) <= 99):
            await interaction.response.send_message("❌ Введите число от 0 до 99.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        limit = int(val)
        try:
            await self.channel.edit(user_limit=limit)
            if limit == 0:
                await interaction.followup.send("✅ Лимит участников снят (неограниченно).", ephemeral=True)
            else:
                await interaction.followup.send(f"✅ Лимит участников установлен: **{limit}** чел.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка изменения лимита: {e}", ephemeral=True)


class VoiceKickSelectView(ui.View):
    def __init__(self, channel: discord.VoiceChannel, owner: discord.Member):
        super().__init__(timeout=60)
        self.channel = channel
        self.owner = owner

        # Меню выбора пользователей из тех, кто сейчас в канале
        options = [
            discord.SelectOption(label=m.display_name[:25], value=str(m.id), description=f"ID: {m.id}")
            for m in channel.members if m.id != owner.id
        ]

        if not options:
            self.user_select = None
        else:
            self.user_select = ui.Select(placeholder="Выберите участника для исключения...", options=options[:25])
            self.user_select.callback = self.kick_callback
            self.add_item(self.user_select)

    async def kick_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = int(self.user_select.values[0])
        member = self.channel.guild.get_member(user_id)
        if not member:
            await interaction.followup.send("❌ Участник не найден.", ephemeral=True)
            return

        try:
            # Отключаем из канала
            await member.move_to(None, reason=f"Исключен создателем канала {interaction.user}")
            # Запрещаем подключаться обратно
            await self.channel.set_permissions(member, connect=False)
            await interaction.followup.send(f"🚫 Участник {member.mention} исключен и заблокирован в этом канале.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)


class VoiceTransferSelectView(ui.View):
    def __init__(self, channel: discord.VoiceChannel, owner: discord.Member):
        super().__init__(timeout=60)
        self.channel = channel
        self.owner = owner

        options = [
            discord.SelectOption(label=m.display_name[:25], value=str(m.id), description=f"ID: {m.id}")
            for m in channel.members if m.id != owner.id
        ]

        if not options:
            self.user_select = None
        else:
            self.user_select = ui.Select(placeholder="Выберите нового владельца...", options=options[:25])
            self.user_select.callback = self.transfer_callback
            self.add_item(self.user_select)

    async def transfer_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        user_id = int(self.user_select.values[0])
        member = self.channel.guild.get_member(user_id)
        if not member:
            await interaction.followup.send("❌ Участник не найден.", ephemeral=True)
            return

        config_manager.set_temp_voice_owner(self.channel.guild.id, self.channel.id, member.id)
        await interaction.followup.send(f"👑 Права владельца канала переданы {member.mention}!", ephemeral=False)


class VoiceControlView(ui.View):
    """Интерактивная панель управления голосовым каналом в чате войса."""

    def __init__(self):
        super().__init__(timeout=None)

    def get_channel(self, interaction: discord.Interaction) -> discord.VoiceChannel | None:
        if isinstance(interaction.channel, discord.VoiceChannel):
            return interaction.channel
        if interaction.user.voice and isinstance(interaction.user.voice.channel, discord.VoiceChannel):
            return interaction.user.voice.channel
        return None

    def is_authorized(self, interaction: discord.Interaction, channel: discord.VoiceChannel) -> bool:
        """Проверяет, является ли пользователь владельцем канала или администратором."""
        guild = interaction.guild
        if not guild or not channel:
            return False

        # 1. Если администратор сервера — разрешено всегда
        if interaction.user.guild_permissions.administrator:
            return True

        # 2. Проверяем сохраненного владельца в базе
        info = config_manager.get_temp_voice_info(guild.id, channel.id)
        if info and info.get("owner_id") == interaction.user.id:
            return True

        # 3. Fallback: проверяем персональные права в самом канале
        # Создателю канала при создании выдаются права move_members=True и manage_channels=True
        user_perms = channel.permissions_for(interaction.user)
        if user_perms.move_members or user_perms.manage_channels:
            config_manager.register_temp_voice(
                guild.id, channel.id, interaction.user.id, discord.utils.utcnow().isoformat()
            )
            return True

        # 4. Fallback 2: если имя канала содержит имя пользователя
        clean_ch_name = channel.name.lower()
        if interaction.user.name.lower() in clean_ch_name or interaction.user.display_name.lower() in clean_ch_name:
            config_manager.register_temp_voice(
                guild.id, channel.id, interaction.user.id, discord.utils.utcnow().isoformat()
            )
            return True

        return False

    @ui.button(label="Название", style=discord.ButtonStyle.secondary, emoji="✏️", custom_id="vc_rename_btn", row=0)
    async def rename_btn(self, interaction: discord.Interaction, button: ui.Button):
        channel = self.get_channel(interaction)
        if not channel or not self.is_authorized(interaction, channel):
            await interaction.response.send_message("❌ Только владелец этого канала может управлять им.", ephemeral=True)
            return
        await interaction.response.send_modal(VoiceRenameModal(channel))

    @ui.button(label="Лимит", style=discord.ButtonStyle.secondary, emoji="👥", custom_id="vc_limit_btn", row=0)
    async def limit_btn(self, interaction: discord.Interaction, button: ui.Button):
        channel = self.get_channel(interaction)
        if not channel or not self.is_authorized(interaction, channel):
            await interaction.response.send_message("❌ Только владелец этого канала может управлять им.", ephemeral=True)
            return
        await interaction.response.send_modal(VoiceLimitModal(channel))

    @ui.button(label="Закрыть/Открыть", style=discord.ButtonStyle.secondary, emoji="🔒", custom_id="vc_lock_btn", row=0)
    async def lock_btn(self, interaction: discord.Interaction, button: ui.Button):
        channel = self.get_channel(interaction)
        if not channel or not self.is_authorized(interaction, channel):
            await interaction.response.send_message("❌ Только владелец этого канала может управлять им.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        current_perms = channel.overwrites_for(guild.default_role)

        if current_perms.connect is False:
            current_perms.connect = None
            await channel.set_permissions(guild.default_role, overwrite=current_perms)
            await interaction.followup.send("🔓 Доступ открыт: теперь любой участник может подключиться.", ephemeral=True)
        else:
            current_perms.connect = False
            await channel.set_permissions(guild.default_role, overwrite=current_perms)
            await interaction.followup.send("🔒 Доступ закрыт: новые участники не смогут войти.", ephemeral=True)

    @ui.button(label="Скрыть/Показать", style=discord.ButtonStyle.secondary, emoji="👁️", custom_id="vc_hide_btn", row=0)
    async def hide_btn(self, interaction: discord.Interaction, button: ui.Button):
        channel = self.get_channel(interaction)
        if not channel or not self.is_authorized(interaction, channel):
            await interaction.response.send_message("❌ Только владелец этого канала может управлять им.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        current_perms = channel.overwrites_for(guild.default_role)

        if current_perms.view_channel is False:
            current_perms.view_channel = None
            await channel.set_permissions(guild.default_role, overwrite=current_perms)
            await interaction.followup.send("👁️ Канал теперь виден в списке каналов сервера.", ephemeral=True)
        else:
            current_perms.view_channel = False
            await channel.set_permissions(guild.default_role, overwrite=current_perms)
            await interaction.followup.send("🙈 Канал скрыт из общего списка каналов.", ephemeral=True)

    @ui.button(label="Выгнать", style=discord.ButtonStyle.danger, emoji="🚫", custom_id="vc_kick_btn", row=1)
    async def kick_btn(self, interaction: discord.Interaction, button: ui.Button):
        channel = self.get_channel(interaction)
        if not channel or not self.is_authorized(interaction, channel):
            await interaction.response.send_message("❌ Только владелец этого канала может управлять им.", ephemeral=True)
            return

        view = VoiceKickSelectView(channel, interaction.user)
        if not view.user_select:
            await interaction.response.send_message("⚠️ В канале сейчас нет других участников для исключения.", ephemeral=True)
            return
        await interaction.response.send_message("Выберите участника, которого хотите исключить:", view=view, ephemeral=True)

    @ui.button(label="Передать права", style=discord.ButtonStyle.primary, emoji="👑", custom_id="vc_transfer_btn", row=1)
    async def transfer_btn(self, interaction: discord.Interaction, button: ui.Button):
        channel = self.get_channel(interaction)
        if not channel or not self.is_authorized(interaction, channel):
            await interaction.response.send_message("❌ Только владелец этого канала может управлять им.", ephemeral=True)
            return

        view = VoiceTransferSelectView(channel, interaction.user)
        if not view.user_select:
            await interaction.response.send_message("⚠️ В канале нет других участников, чтобы передать права.", ephemeral=True)
            return
        await interaction.response.send_message("Выберите нового владельца канала:", view=view, ephemeral=True)

    @ui.button(label="Удалить канал", style=discord.ButtonStyle.danger, emoji="🗑️", custom_id="vc_delete_btn", row=1)
    async def delete_btn(self, interaction: discord.Interaction, button: ui.Button):
        channel = self.get_channel(interaction)
        if not channel or not self.is_authorized(interaction, channel):
            await interaction.response.send_message("❌ Только владелец этого канала может удалить его.", ephemeral=True)
            return

        await interaction.response.send_message("⌛ Удаление канала...", ephemeral=True)
        config_manager.remove_temp_voice(interaction.guild_id, channel.id)
        try:
            await channel.delete(reason=f"Удален владельцем {interaction.user}")
        except Exception:
            pass


class VoiceCog(commands.Cog):
    """Ког автоматического создания приватных комнат (Join to Create)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        guild = member.guild
        settings = config_manager.get_guild(guild.id)
        hub_channel_id = settings.get("voice_hub_channel_id")

        # 1. ПОЛЬЗОВАТЕЛЬ ЗАШЁЛ В ХАБ "СОЗДАТЬ ВОЙС"
        if after.channel and hub_channel_id and after.channel.id == hub_channel_id:
            category_id = settings.get("voice_category_id")
            category = guild.get_channel(category_id) if category_id else after.channel.category

            channel_name = f"🔊 {member.display_name}"
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                member: discord.PermissionOverwrite(
                    connect=True,
                    speak=True,
                    view_channel=True,
                    move_members=True,
                    manage_channels=True
                ),
                guild.me: discord.PermissionOverwrite(
                    connect=True,
                    speak=True,
                    view_channel=True,
                    manage_channels=True,
                    move_members=True
                )
            }

            try:
                # Создаем временный голосовой канал
                new_channel = await guild.create_voice_channel(
                    name=channel_name,
                    category=category,
                    overwrites=overwrites,
                    user_limit=0,
                    reason=f"Создание временного голосового канала для {member}"
                )
            except discord.Forbidden:
                print(f"[Voice Error] Нет прав на создание голосового канала на сервере {guild.name}")
                return

            # Регистрируем созданный канал
            config_manager.register_temp_voice(
                guild_id=guild.id,
                channel_id=new_channel.id,
                owner_id=member.id,
                created_at=discord.utils.utcnow().isoformat()
            )

            # Перемещаем пользователя в его новый канал
            try:
                await member.move_to(new_channel)
            except Exception as e:
                print(f"[Voice Error] Не удалось переместить участника в канал: {e}")

            # Отправляем сообщение с панелью управления в текстовый чат голосового канала
            embed = discord.Embed(
                title="🔊 Управление голосовой комнатой",
                description=(
                    f"Добро пожаловать в ваш личный голосовой канал, {member.mention}!\n\n"
                    "Используйте кнопки ниже для быстрой настройки:\n"
                    "• ✏️ **Название** — изменить имя комнаты\n"
                    "• 👥 **Лимит** — установить ограничение участников\n"
                    "• 🔒 **Закрыть/Открыть** — закрыть вход для других\n"
                    "• 👁️ **Скрыть/Показать** — скрыть канал из списка\n"
                    "• 🚫 **Выгнать** — исключить участника из канала\n"
                    "• 👑 **Передать** — передать права создателя\n"
                    "• 🗑️ **Удалить** — закрыть комнату сейчас\n\n"
                    "*Когда все участники выйдут из комнаты, она удалится автоматически.*"
                ),
                color=discord.Color.teal()
            )
            embed.set_author(name=str(member), icon_url=member.display_avatar.url)
            embed.set_footer(text="Панель создателя комнаты")

            try:
                await new_channel.send(content=member.mention, embed=embed, view=VoiceControlView())
            except Exception as e:
                print(f"[Voice Error] Не удалось отправить панель в чат войса: {e}")

        # 2. ПОЛЬЗОВАТЕЛЬ ВЫШЕЛ ИЗ ВРЕМЕННОГО КАНАЛА
        if before.channel and before.channel != after.channel:
            temp_info = config_manager.get_temp_voice_info(guild.id, before.channel.id)
            if temp_info:
                # Если в канале больше никого нет — удаляем его
                if len(before.channel.members) == 0:
                    config_manager.remove_temp_voice(guild.id, before.channel.id)
                    try:
                        await before.channel.delete(reason="Временный голосовой канал опустел")
                    except Exception as e:
                        print(f"[Voice Error] Не удалось удалить пустой канал: {e}")
                else:
                    # Если канал не пуст, но вышел владелец — передаём владение следующему участнику
                    if temp_info.get("owner_id") == member.id:
                        new_owner = before.channel.members[0]
                        config_manager.set_temp_voice_owner(guild.id, before.channel.id, new_owner.id)
                        embed_transfer = discord.Embed(
                            description=f"👑 Создатель покинул канал. Новым владельцем комнаты стал {new_owner.mention}!",
                            color=discord.Color.gold()
                        )
                        try:
                            await before.channel.send(embed=embed_transfer)
                        except Exception:
                            pass

    @app_commands.command(
        name="setup-voice",
        description="Создать систему авто-создания комнат (хаб 'Создать войс' и категорию)"
    )
    @app_commands.describe(
        category="Категория, в которой будут создаваться временные каналы",
        hub_name="Название канала для создания (по умолчанию '➕ Создать канал')"
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_voice(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        hub_name: str | None = None
    ):
        """Создание хаб-канала и привязка категории."""
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        name = hub_name or "➕ Создать канал"

        # Создаем голосовой хаб-канал внутри категории
        try:
            hub_channel = await guild.create_voice_channel(
                name=name,
                category=category,
                reason="Создание хаба для динамических голосовых каналов"
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ У бота нет прав для создания голосового канала (`Manage Channels`).", ephemeral=True)
            return

        config_manager.set_guild_value(guild.id, "voice_hub_channel_id", hub_channel.id)
        config_manager.set_guild_value(guild.id, "voice_category_id", category.id)

        embed = discord.Embed(
            title="🔊 Система голосовых каналов настроена!",
            description=(
                f"Создан управляющий канал: {hub_channel.mention}\n"
                f"Категория для новых комнат: **{category.name}**\n\n"
                "**Как это работает:**\n"
                "1. Участник заходит в канал `➕ Создать канал`.\n"
                "2. Бот автоматически создаёт для него персональную комнату и перемещает его туда.\n"
                "3. В чате комнаты появляется интерактивная панель с кнопками настройки.\n"
                "4. Когда все покинут комнату, она удалится автоматически."
            ),
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="set-voice-hub",
        description="Сделать уже существующий голосовой канал хабом для создания комнат"
    )
    @app_commands.describe(
        channel="Голосовой канал, при входе в который будут создаваться комнаты",
        category="Категория для новых каналов (опционально, по умолчанию категория хаба)"
    )
    @app_commands.default_permissions(administrator=True)
    async def set_voice_hub(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
        category: discord.CategoryChannel | None = None
    ):
        """Привязка существующего канала в качестве хаба."""
        guild = interaction.guild
        cat_id = category.id if category else (channel.category.id if channel.category else None)

        config_manager.set_guild_value(guild.id, "voice_hub_channel_id", channel.id)
        if cat_id:
            config_manager.set_guild_value(guild.id, "voice_category_id", cat_id)

        embed = discord.Embed(
            title="✅ Хаб голосовых каналов установлен",
            description=f"Канал {channel.mention} теперь работает как генератор комнат.\nПри входе в него бот создаст отдельный канал для участника.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceCog(bot))
