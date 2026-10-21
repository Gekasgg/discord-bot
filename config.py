import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"

logger = logging.getLogger("bot.config")

# Структура настроек по умолчанию для каждого сервера
DEFAULT_GUILD_SETTINGS = {
    "log_channel_id": None,
    "ticket_category_id": None,
    "ticket_log_channel_id": None,
    "support_role_id": None,
    "ticket_counter": 0,
    "active_tickets": {},  # channel_id: {"author_id": ..., "created_at": ..., "claimed_by": ...}
    # Настройки формы создания обращения (5 строк)
    "ticket_modal_title": "Создание нового обращения",
    "ticket_field1_label": "1. Ваш никнейм",
    "ticket_field1_placeholder": "Укажите ваш игровой или серверный никнейм",
    "ticket_field2_label": "2. Ваш ID / SteamID",
    "ticket_field2_placeholder": "Ваш SteamID или ID аккаунта (если применимо)",
    "ticket_field3_label": "3. Тема обращения",
    "ticket_field3_placeholder": "Вопрос, жалоба, донат, баг...",
    "ticket_field4_label": "4. Описание проблемы",
    "ticket_field4_placeholder": "Опишите подробно все детали вопроса или проблемы...",
    "ticket_field5_label": "5. Доказательства / Ссылки",
    "ticket_field5_placeholder": "Ссылки на скриншоты или видео (необязательно)",
    # Настройки приветствия внутри тикета
    "ticket_welcome_title": "📩 Тикет #{num:04d}",
    "ticket_welcome_text": "Здравствуйте! Команда поддержки скоро ответит вам.\nПожалуйста, опишите все детали и ожидайте ответа.",
    # Настройки динамических голосовых каналов (Join to Create)
    "voice_hub_channel_id": None,
    "voice_category_id": None,
    "temp_voice_channels": {}  # channel_id: {"owner_id": ..., "created_at": ...}
}


class ConfigManager:
    """Менеджер конфигурации и настроек гильдий."""

    def __init__(self, file_path: Path = SETTINGS_FILE):
        self.file_path = file_path
        self._cache = self._load()

    def _load(self) -> dict:
        if not self.file_path.exists():
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки настроек из {self.file_path}: {e}")
            return {}

    def save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек: {e}")

    def get_guild(self, guild_id: int) -> dict:
        gid = str(guild_id)
        if gid not in self._cache:
            self._cache[gid] = DEFAULT_GUILD_SETTINGS.copy()
            self._cache[gid]["active_tickets"] = {}
            self.save()
        else:
            updated = False
            for k, v in DEFAULT_GUILD_SETTINGS.items():
                if k not in self._cache[gid]:
                    self._cache[gid][k] = v
                    updated = True
            if updated:
                self.save()
        return self._cache[gid]

    def set_guild_value(self, guild_id: int, key: str, value):
        guild_data = self.get_guild(guild_id)
        guild_data[key] = value
        self.save()

    def increment_ticket_counter(self, guild_id: int) -> int:
        guild_data = self.get_guild(guild_id)
        guild_data["ticket_counter"] = guild_data.get("ticket_counter", 0) + 1
        self.save()
        return guild_data["ticket_counter"]

    def register_ticket(self, guild_id: int, channel_id: int, author_id: int, created_at: str):
        guild_data = self.get_guild(guild_id)
        if "active_tickets" not in guild_data:
            guild_data["active_tickets"] = {}
        guild_data["active_tickets"][str(channel_id)] = {
            "author_id": author_id,
            "created_at": created_at,
            "claimed_by": None
        }
        self.save()

    def get_ticket_info(self, guild_id: int, channel_id: int) -> dict | None:
        guild_data = self.get_guild(guild_id)
        return guild_data.get("active_tickets", {}).get(str(channel_id))

    def claim_ticket(self, guild_id: int, channel_id: int, user_id: int):
        guild_data = self.get_guild(guild_id)
        cid = str(channel_id)
        if "active_tickets" in guild_data and cid in guild_data["active_tickets"]:
            guild_data["active_tickets"][cid]["claimed_by"] = user_id
            self.save()

    def remove_ticket(self, guild_id: int, channel_id: int):
        guild_data = self.get_guild(guild_id)
        cid = str(channel_id)
        if "active_tickets" in guild_data and cid in guild_data["active_tickets"]:
            del guild_data["active_tickets"][cid]
            self.save()

    def register_temp_voice(self, guild_id: int, channel_id: int, owner_id: int, created_at: str):
        guild_data = self.get_guild(guild_id)
        if "temp_voice_channels" not in guild_data:
            guild_data["temp_voice_channels"] = {}
        guild_data["temp_voice_channels"][str(channel_id)] = {
            "owner_id": owner_id,
            "created_at": created_at
        }
        self.save()

    def get_temp_voice_info(self, guild_id: int, channel_id: int) -> dict | None:
        guild_data = self.get_guild(guild_id)
        return guild_data.get("temp_voice_channels", {}).get(str(channel_id))

    def set_temp_voice_owner(self, guild_id: int, channel_id: int, new_owner_id: int):
        guild_data = self.get_guild(guild_id)
        cid = str(channel_id)
        if "temp_voice_channels" in guild_data and cid in guild_data["temp_voice_channels"]:
            guild_data["temp_voice_channels"][cid]["owner_id"] = new_owner_id
            self.save()

    def remove_temp_voice(self, guild_id: int, channel_id: int):
        guild_data = self.get_guild(guild_id)
        cid = str(channel_id)
        if "temp_voice_channels" in guild_data and cid in guild_data["temp_voice_channels"]:
            del guild_data["temp_voice_channels"][cid]
            self.save()


config_manager = ConfigManager()
