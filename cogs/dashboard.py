import asyncio
import datetime
import json
import logging
import math
import os
import platform
import re
import secrets
import stat
import urllib.request
from pathlib import Path

from aiohttp import web
import discord
from discord import app_commands, ui
from discord.ext import commands

from config import DATA_DIR, config_manager
from cogs.tickets import TicketLauncherView
from cogs.levels import levels_manager
from cogs.giveaways import giveaways_manager, parse_duration, GiveawayJoinView, build_giveaway_embed

logger = logging.getLogger("bot.dashboard")

SECRET_FILE = DATA_DIR / "dashboard_token.txt"


def get_or_create_secret() -> str:
    """Возвращает постоянный буквенно-цифровой ключ доступа к веб-панели."""
    env_secret = os.getenv("DASHBOARD_SECRET", "").strip()
    if env_secret:
        return env_secret
    if SECRET_FILE.exists():
        try:
            val = SECRET_FILE.read_text(encoding="utf-8").strip()
            if len(val) >= 12 and val.isalnum():
                return val
        except Exception:
            pass
    new_secret = secrets.token_hex(12)
    try:
        SECRET_FILE.write_text(new_secret, encoding="utf-8")
    except Exception:
        pass
    return new_secret


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Панель управления Discord Ботом</title>
<style>
  :root {
    --bg-main: #0b0f19;
    --bg-card: #151c2c;
    --bg-input: #1e293b;
    --border: #2e3c56;
    --accent: #5865F2;
    --accent-hover: #4752C4;
    --success: #22c55e;
    --warning: #f59e0b;
    --danger: #ef4444;
    --text: #f8fafc;
    --text-muted: #94a3b8;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Inter, sans-serif;
    background: var(--bg-main);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }
  header {
    background: rgba(21, 28, 44, 0.95);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
    padding: 16px 28px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: sticky;
    top: 0;
    z-index: 50;
    flex-wrap: wrap;
    gap: 12px;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 1.25rem;
    font-weight: 700;
  }
  .brand-badge {
    background: var(--success);
    color: #fff;
    padding: 4px 10px;
    border-radius: 8px;
    font-size: 0.8rem;
  }
  .guild-selector {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  select, input, textarea {
    background: var(--bg-input);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 0.95rem;
    outline: none;
    width: 100%;
    transition: border-color 0.2s;
  }
  select:focus, input:focus, textarea:focus {
    border-color: var(--accent);
  }
  .layout {
    display: flex;
    flex: 1;
    max-width: 1400px;
    width: 100%;
    margin: 0 auto;
    padding: 24px;
    gap: 24px;
  }
  .sidebar {
    width: 260px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .tab-btn {
    background: transparent;
    color: var(--text-muted);
    border: 1px solid transparent;
    text-align: left;
    padding: 12px 16px;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .tab-btn:hover {
    background: var(--bg-card);
    color: var(--text);
  }
  .tab-btn.active {
    background: var(--accent);
    color: #fff;
    box-shadow: 0 4px 14px rgba(88, 101, 242, 0.35);
  }
  .content {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 20px;
  }
  .tab-pane { display: none; flex-direction: column; gap: 20px; }
  .tab-pane.active { display: flex; }
  .card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 22px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.2);
  }
  .card h2 {
    font-size: 1.15rem;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .card p.desc {
    color: var(--text-muted);
    font-size: 0.9rem;
    margin-bottom: 18px;
  }
  .grid-2 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 16px;
  }
  .grid-3 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 14px;
  }
  .grid-4 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 14px;
  }
  .stat-box {
    background: var(--bg-input);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
  }
  .stat-box .label { color: var(--text-muted); font-size: 0.85rem; }
  .stat-box .val { font-size: 1.45rem; font-weight: 700; margin-top: 4px; }
  .summary-item {
    background: var(--bg-input);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 12px 14px;
  }
  .summary-item .s-title {
    color: var(--text-muted);
    font-size: 0.8rem;
    margin-bottom: 4px;
  }
  .summary-item .s-val {
    font-size: 0.96rem;
    font-weight: 600;
    color: #fff;
  }
  .form-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 14px;
  }
  .form-group label {
    font-size: 0.9rem;
    font-weight: 600;
    color: #cbd5e1;
  }
  .btn {
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 8px;
    padding: 10px 18px;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.2s, transform 0.1s;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }
  .btn:hover { background: var(--accent-hover); }
  .btn:active { transform: scale(0.98); }
  .btn-success { background: var(--success); }
  .btn-success:hover { background: #16a34a; }
  .btn-danger { background: var(--danger); }
  .btn-danger:hover { background: #dc2626; }
  .btn-warning { background: var(--warning); color: #000; }
  .table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 10px;
  }
  .table th, .table td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    text-align: left;
    font-size: 0.92rem;
  }
  .table th { color: var(--text-muted); font-weight: 600; }
  .badge {
    padding: 5px 10px;
    border-radius: 6px;
    font-size: 0.82rem;
    font-weight: 600;
    display: inline-block;
    margin-right: 6px;
    margin-bottom: 6px;
  }
  .badge-ok { background: rgba(34, 197, 94, 0.2); color: #4ade80; }
  .badge-warn { background: rgba(245, 158, 11, 0.2); color: #fbbf24; }
  #toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: #1e293b;
    border-left: 4px solid var(--success);
    color: #fff;
    padding: 14px 20px;
    border-radius: 10px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.45);
    display: none;
    z-index: 999;
    font-weight: 600;
  }
  @media (max-width: 860px) {
    .layout { flex-direction: column; padding: 14px; }
    .sidebar { width: 100%; flex-direction: row; overflow-x: auto; }
    .tab-btn { white-space: nowrap; }
  }
</style>
</head>
<body>

<header>
  <div class="brand">
    <span>🤖 Панель Управления Сервером</span>
    <span class="brand-badge" id="bot-name-badge">Подключен</span>
  </div>
  <div class="guild-selector">
    <span style="color:var(--text-muted);font-size:0.9rem;">Сервер:</span>
    <select id="guild-select" onchange="loadGuildData()" style="min-width:220px;"></select>
    <button class="btn" onclick="loadGuildData(true)">🔄 Обновить данные</button>
  </div>
</header>

<div class="layout">
  <nav class="sidebar">
    <button class="tab-btn active" onclick="switchTab('tab-general', this)">🏠 Обзор и Логи</button>
    <button class="tab-btn" onclick="switchTab('tab-levels', this)">⭐ Уровни и Ранги</button>
    <button class="tab-btn" onclick="switchTab('tab-tickets', this)">🎫 Тикет-система</button>
    <button class="tab-btn" onclick="switchTab('tab-voice', this)">🔊 Голосовые каналы</button>
    <button class="tab-btn" onclick="switchTab('tab-giveaways', this)">🎁 Розыгрыши</button>
    <button class="tab-btn" onclick="switchTab('tab-moderation', this)">🧹 Чистка и Защита</button>
  </nav>

  <main class="content">
    <!-- ВКЛАДКА 1: ОБЗОР И ЛОГИ -->
    <div id="tab-general" class="tab-pane active">
      <div class="grid-4">
        <div class="stat-box"><div class="label">Участников на сервере</div><div class="val" id="st-members">-</div></div>
        <div class="stat-box"><div class="label">Текстовых каналов</div><div class="val" id="st-channels">-</div></div>
        <div class="stat-box"><div class="label">Ролей на сервере</div><div class="val" id="st-roles">-</div></div>
        <div class="stat-box"><div class="label">Пинг бота</div><div class="val" id="st-ping">-</div></div>
      </div>

      <div class="card">
        <h2>📋 Текущая сводка настроек вашего сервера</h2>
        <p class="desc">Актуальные привязки каналов и ролей, которые сейчас установлены на сервере:</p>
        <div class="grid-3" id="live-summary-grid"></div>
      </div>

      <div class="card">
        <h2>📜 Логирование (Аудит сервера) и Автороль</h2>
        <p class="desc">Выберите канал, куда бот будет присылать карточки логов (роли, никнеймы, вход/выход, сообщения), и роль для новых участников.</p>
        <div class="grid-2">
          <div class="form-group">
            <label>Канал для логов аудита:</label>
            <select id="cfg-log-channel"></select>
          </div>
          <div class="form-group">
            <label>Автороль при входе на сервер (Autorole):</label>
            <select id="cfg-auto-role"></select>
          </div>
        </div>
        <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:8px;">
          <button class="btn btn-success" onclick="saveGeneral()">💾 Сохранить настройки</button>
          <button class="btn" onclick="sendTestLog()">🧪 Отправить тестовый лог в Discord</button>
        </div>
      </div>

      <div class="card">
        <h2>🛡️ Безопасность и Доступ участников к командам (/rank)</h2>
        <p class="desc">Проверка прав роли @everyone и текстовых каналов. Если участники не могут вызывать /rank или /ранг — нажмите кнопку ниже.</p>
        <div id="security-status-box" style="margin-bottom:16px;"></div>
        <button class="btn btn-warning" onclick="fixPermissions()">🔧 Починить доступ к /rank для всех участников и защитить @everyone</button>
      </div>
    </div>

    <!-- ВКЛАДКА 2: УРОВНИ И РАНГИ -->
    <div id="tab-levels" class="tab-pane">
      <div class="card">
        <h2>⚙️ Настройки системы уровней и режима рангов</h2>
        <p class="desc">Настройте, как выдаются роли за уровни: с заменой предыдущей роли (например, 10–20 одна, 20–30 другая) или с накоплением всех ролей.</p>
        <div class="grid-2">
          <div class="form-group">
            <label>Статус системы уровней:</label>
            <select id="cfg-levels-enabled">
              <option value="true">✅ Включена (опыт за чат и войс)</option>
              <option value="false">❌ Отключена</option>
            </select>
          </div>
          <div class="form-group">
            <label>Канал оповещений о повышении уровня:</label>
            <select id="cfg-level-channel"></select>
          </div>
          <div class="form-group" style="grid-column: 1 / -1;">
            <label>Режим выдачи ролей за уровни:</label>
            <select id="cfg-level-replace">
              <option value="true">🔄 Режим рангов: Заменять старую роль на новую (с 10 по 20 одна, с 20 по 30 другая, старая снимается)</option>
              <option value="false">📚 Накопительный режим: Оставлять у участника все полученные роли</option>
            </select>
          </div>
        </div>
        <button class="btn btn-success" onclick="saveLevelsConfig()">💾 Сохранить настройки уровней</button>
      </div>

      <div class="card">
        <h2>🎖️ Роли за уровни (Диапазоны рангов)</h2>
        <p class="desc">Добавьте уровни и роли. В режиме рангов бот сам рассчитает диапазоны (например: 10 ур. ➔ Роль 1, 20 ур. ➔ Роль 2) и снимет предыдущую роль.</p>
        <div class="grid-2" style="align-items:end;">
          <div class="form-group">
            <label>Уровень (число от 1):</label>
            <input type="number" id="new-lvl-num" min="1" placeholder="Например: 10">
          </div>
          <div class="form-group">
            <label>Выдаваемая роль:</label>
            <select id="new-lvl-role"></select>
          </div>
        </div>
        <button class="btn" onclick="addLevelRole()">➕ Назначить роль за уровень</button>

        <table class="table" id="level-roles-table" style="margin-top:18px;">
          <thead><tr><th>Диапазон / Уровень</th><th>Роль на сервере</th><th>Действие</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>

      <div class="card">
        <h2>🏆 Управление опытом участников (Топ-20)</h2>
        <p class="desc">Вы можете вручную добавить или списать опыт (XP) любому участнику сервера, и бот автоматически пересчитает его ранг и роли.</p>
        <div class="grid-2">
          <div class="form-group">
            <label>Участник сервера:</label>
            <select id="xp-member-select"></select>
          </div>
          <div class="form-group">
            <label>Количество опыта (XP):</label>
            <input type="number" id="xp-amount-input" value="500" min="1">
          </div>
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px;">
          <button class="btn btn-success" onclick="modifyXp('add')">➕ Добавить XP</button>
          <button class="btn btn-warning" onclick="modifyXp('remove')">➖ Списать XP</button>
          <button class="btn btn-danger" onclick="modifyXp('reset')">🗑️ Сбросить уровень участника</button>
        </div>

        <table class="table" id="leaderboard-table">
          <thead><tr><th>#</th><th>Участник</th><th>Уровень</th><th>Опыт (XP)</th><th>Сообщений</th><th>В войсе</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
    </div>

    <!-- ВКЛАДКА 3: ТИКЕТ-СИСТЕМА -->
    <div id="tab-tickets" class="tab-pane">
      <div class="card">
        <h2>🎫 Основные настройки тикетов и формы обращения</h2>
        <p class="desc">Настройте категорию, роль поддержки, канал транскриптов и тексты всплывающего окна при открытии тикета.</p>
        <div class="grid-2">
          <div class="form-group">
            <label>Категория для создания новых тикетов:</label>
            <select id="cfg-ticket-cat"></select>
          </div>
          <div class="form-group">
            <label>Роль поддержки (модераторов тикетов):</label>
            <select id="cfg-ticket-role"></select>
          </div>
          <div class="form-group">
            <label>Канал для логов и транскриптов тикетов:</label>
            <select id="cfg-ticket-log"></select>
          </div>
          <div class="form-group">
            <label>Заголовок всплывающего окна (до 45 симв.):</label>
            <input type="text" id="cfg-t-modal-title" maxlength="45">
          </div>
          <div class="form-group">
            <label>Название 1-го поля формы:</label>
            <input type="text" id="cfg-t-f1-label" maxlength="45">
          </div>
          <div class="form-group">
            <label>Подсказка внутри 1-го поля:</label>
            <input type="text" id="cfg-t-f1-ph" maxlength="100">
          </div>
          <div class="form-group">
            <label>Название 2-го поля формы:</label>
            <input type="text" id="cfg-t-f2-label" maxlength="45">
          </div>
          <div class="form-group">
            <label>Подсказка внутри 2-го поля:</label>
            <input type="text" id="cfg-t-f2-ph" maxlength="100">
          </div>
          <div class="form-group">
            <label>Заголовок внутри открытого тикета ({num} — номер):</label>
            <input type="text" id="cfg-t-w-title" maxlength="100">
          </div>
          <div class="form-group" style="grid-column: 1 / -1;">
            <label>Текст приветствия внутри открытого тикета:</label>
            <textarea id="cfg-t-w-text" rows="3"></textarea>
          </div>
        </div>
        <button class="btn btn-success" onclick="saveTicketsConfig()">💾 Сохранить настройки тикетов</button>
      </div>

      <div class="card">
        <h2>📨 Отправить новую панель с кнопкой «Создать тикет» в канал</h2>
        <p class="desc">Бот опубликует в выбранном текстовом канале красивую карточку с кнопкой для открытия тикетов.</p>
        <div class="grid-2">
          <div class="form-group">
            <label>В какой канал отправить панель:</label>
            <select id="send-ticket-channel"></select>
          </div>
          <div class="form-group">
            <label>Надпись на зеленой кнопке:</label>
            <input type="text" id="send-ticket-btn" value="Создать тикет">
          </div>
          <div class="form-group" style="grid-column: 1 / -1;">
            <label>Заголовок панели:</label>
            <input type="text" id="send-ticket-title" value="🎫 Поддержка и обратная связь">
          </div>
          <div class="form-group" style="grid-column: 1 / -1;">
            <label>Описание на панели:</label>
            <textarea id="send-ticket-desc" rows="3">Возникли вопросы, проблемы или предложения?
Нажмите на зелёную кнопку ниже, чтобы создать приватное обращение.</textarea>
          </div>
        </div>
        <button class="btn" onclick="sendTicketPanel()">📨 Опубликовать панель тикетов в Discord</button>
      </div>
    </div>

    <!-- ВКЛАДКА 4: ГОЛОСОВЫЕ КАНАЛЫ -->
    <div id="tab-voice" class="tab-pane">
      <div class="card">
        <h2>🔊 Динамические голосовые каналы (Join to Create)</h2>
        <p class="desc">При заходе участника в голосовой канал-хаб («➕ Создать канал») бот автоматически создаёт для него приватную комнату с панелью управления.</p>
        <div class="grid-2">
          <div class="form-group">
            <label>Голосовой канал-хаб («➕ Создать канал»):</label>
            <select id="cfg-voice-hub"></select>
          </div>
          <div class="form-group">
            <label>Категория для создания временных комнат:</label>
            <select id="cfg-voice-cat"></select>
          </div>
        </div>
        <div style="display:flex;gap:12px;flex-wrap:wrap;">
          <button class="btn btn-success" onclick="saveVoiceConfig()">💾 Сохранить голосовой хаб</button>
          <button class="btn" onclick="autoCreateVoiceHub()">⚡ Автоматически создать новую категорию и канал «➕ Создать канал»</button>
        </div>
      </div>
    </div>

    <!-- ВКЛАДКА 5: РОЗЫГРЫШИ -->
    <div id="tab-giveaways" class="tab-pane">
      <div class="card">
        <h2>👑 Права на управление розыгрышами</h2>
        <p class="desc">Выберите роль, участники которой смогут запускать розыгрыши на сервере помимо администраторов.</p>
        <div class="form-group" style="max-width:420px;">
          <label>Роль ведущего розыгрышей:</label>
          <select id="cfg-gw-role"></select>
        </div>
        <button class="btn btn-success" onclick="saveGiveawayConfig()">💾 Сохранить роль розыгрышей</button>
      </div>

      <div class="card">
        <h2>🎉 Запустить новый розыгрыш с сайта</h2>
        <p class="desc">Розыгрыш будет мгновенно опубликован в выбранном канале с кнопкой участия и автоматической выдачей приза в ЛС.</p>
        <div class="grid-2">
          <div class="form-group">
            <label>Канал для публикации:</label>
            <select id="gw-channel"></select>
          </div>
          <div class="form-group">
            <label>Название приза:</label>
            <input type="text" id="gw-prize" placeholder="Например: VIP Привилегия на 30 дней">
          </div>
          <div class="form-group">
            <label>Длительность (например: 30м, 2ч, 1д):</label>
            <input type="text" id="gw-duration" value="1ч">
          </div>
          <div class="form-group">
            <label>Количество победителей:</label>
            <input type="number" id="gw-winners" value="1" min="1" max="50">
          </div>
          <div class="form-group">
            <label>Обязательная роль для участия (опционально):</label>
            <select id="gw-req-role"></select>
          </div>
          <div class="form-group">
            <label>Минимальный уровень для участия (0 = без ограничений):</label>
            <input type="number" id="gw-req-level" value="0" min="0">
          </div>
          <div class="form-group" style="grid-column: 1 / -1;">
            <label>Секретный текст / промокод для отправки победителю в ЛС (опционально):</label>
            <textarea id="gw-dm-text" rows="2" placeholder="Например: Ваш промокод: RUST-2026-VIP"></textarea>
          </div>
        </div>
        <button class="btn btn-success" onclick="startGiveaway()">🎁 Запустить розыгрыш в Discord</button>
      </div>
    </div>

    <!-- ВКЛАДКА 6: ЧИСТКА ЧАТА -->
    <div id="tab-moderation" class="tab-pane">
      <div class="card">
        <h2>🧹 Быстрая очистка чата прямо с сайта</h2>
        <p class="desc">Удалите спам или лишние сообщения в любом текстовом канале сервера одним нажатием.</p>
        <div class="grid-2">
          <div class="form-group">
            <label>Текстовый канал для очистки:</label>
            <select id="purge-channel"></select>
          </div>
          <div class="form-group">
            <label>Количество сообщений (1–100):</label>
            <input type="number" id="purge-amount" value="20" min="1" max="100">
          </div>
          <div class="form-group">
            <label>Фильтр сообщений:</label>
            <select id="purge-bots">
              <option value="false">Все сообщения</option>
              <option value="true">🤖 Только сообщения от ботов и вебхуков (анти-спам)</option>
            </select>
          </div>
        </div>
        <button class="btn btn-danger" onclick="purgeChannel()">🧹 Очистить выбранный канал</button>
      </div>
    </div>
  </main>
</div>

<div id="toast">✅ Изменения сохранены!</div>

<script>
const SERVER_INJECTED_TOKEN = "__INJECTED_SECRET__";
const INITIAL_BOOTSTRAP = __INITIAL_BOOTSTRAP_JSON__;

const urlParams = new URLSearchParams(window.location.search);
const TOKEN = urlParams.get('token') || SERVER_INJECTED_TOKEN || localStorage.getItem('dash_token') || '';
if (TOKEN) {
  try { localStorage.setItem('dash_token', TOKEN); } catch (e) {}
}

let currentGuild = null;

function showToast(msg, isError=false) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.borderLeftColor = isError ? '#ef4444' : '#22c55e';
  t.style.display = 'block';
  setTimeout(() => { t.style.display = 'none'; }, 3500);
}

function switchTab(tabId, btn) {
  document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById(tabId).classList.add('active');
  btn.classList.add('active');
}

async function apiCall(path, method='GET', body=null) {
  const opts = {
    method,
    headers: { 'X-Auth-Token': TOKEN, 'Content-Type': 'application/json' }
  };
  if (body) opts.body = JSON.stringify(body);
  const sep = path.includes('?') ? '&' : '?';
  const res = await fetch(path + sep + 'token=' + encodeURIComponent(TOKEN) + '&_t=' + Date.now(), opts);
  const text = await res.text();
  let data = {};
  try {
    data = JSON.parse(text);
  } catch (err) {
    throw new Error('Ошибка ответа сервера (' + res.status + ')');
  }
  if (!res.ok) throw new Error(data.error || 'Ошибка запроса');
  return data;
}

function fillSelect(selectId, items, selectedVal, emptyLabel='— Не выбрано —', includeEmpty=true) {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  sel.innerHTML = '';
  if (includeEmpty) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = emptyLabel;
    sel.appendChild(opt);
  }
  const targetStr = selectedVal ? String(selectedVal) : '';
  (items || []).forEach(item => {
    const opt = document.createElement('option');
    opt.value = String(item.id);
    opt.textContent = item.name;
    if (targetStr && targetStr === String(item.id)) {
      opt.selected = true;
    }
    sel.appendChild(opt);
  });
}

function findNameById(items, id, fallback='Не настроено') {
  if (!id) return fallback;
  const found = (items || []).find(x => String(x.id) === String(id));
  return found ? found.name : ('Удалено (ID: ' + id + ')');
}

function renderGuildData(data) {
  if (!data) return;
  currentGuild = data;
  const s = data.settings || {};

  document.getElementById('st-members').textContent = data.member_count ?? '-';
  document.getElementById('st-channels').textContent = (data.text_channels || []).length;
  document.getElementById('st-roles').textContent = (data.roles || []).length;
  document.getElementById('st-ping').textContent = (data.ping_ms ?? 0) + ' мс';

  // Сводка текущих настроек
  const summaryGrid = document.getElementById('live-summary-grid');
  const summaryItems = [
    { title: '📜 Канал логов аудита', val: findNameById(data.text_channels, s.log_channel_id) },
    { title: '🎭 Автороль новичков', val: findNameById(data.roles, s.auto_role_id) },
    { title: '⭐ Система уровней', val: (s.levels_enabled !== false ? 'Включена' : 'Выключена') + ' (' + (data.level_roles_view || []).length + ' рангов)' },
    { title: '🎫 Категория тикетов', val: findNameById(data.categories, s.ticket_category_id) },
    { title: '👮 Роль поддержки тикетов', val: findNameById(data.roles, s.support_role_id, 'Только админы') },
    { title: '🔊 Голосовой хаб', val: findNameById(data.voice_channels, s.voice_hub_channel_id) }
  ];
  summaryGrid.innerHTML = summaryItems.map(item =>
    `<div class="summary-item"><div class="s-title">${item.title}</div><div class="s-val">${item.val}</div></div>`
  ).join('');

  // Общие
  fillSelect('cfg-log-channel', data.text_channels, s.log_channel_id);
  fillSelect('cfg-auto-role', data.roles, s.auto_role_id);

  // Статус безопасности
  const secBox = document.getElementById('security-status-box');
  let secHtml = '';
  if (data.security && data.security.slash_ok) {
    secHtml += '<span class="badge badge-ok">✅ Команды /rank и /ранг открыты для участников</span>';
  } else {
    secHtml += '<span class="badge badge-warn">⚠️ У @everyone выключено право команд приложений!</span>';
  }
  if (data.security && data.security.webhooks_safe) {
    secHtml += '<span class="badge badge-ok">✅ Защита от спам-вебхуков активна</span>';
  } else {
    secHtml += '<span class="badge badge-warn">🚨 У @everyone включены вебхуки!</span>';
  }
  secBox.innerHTML = secHtml;

  // Уровни
  document.getElementById('cfg-levels-enabled').value = String(s.levels_enabled !== false);
  fillSelect('cfg-level-channel', data.text_channels, s.level_up_channel_id, '💬 В текущем канале сообщения');
  document.getElementById('cfg-level-replace').value = String(s.level_roles_replace !== false);
  fillSelect('new-lvl-role', data.roles, '', '— Выберите роль —', false);
  fillSelect('xp-member-select', data.members, '', '— Выберите участника —', false);

  // Таблица ролей за уровни
  const lrBody = document.querySelector('#level-roles-table tbody');
  lrBody.innerHTML = '';
  (data.level_roles_view || []).forEach(item => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><b>${item.range_text}</b></td><td>${item.role_name}</td>
      <td><button class="btn btn-danger" style="padding:5px 10px;font-size:0.8rem;" onclick="removeLevelRole('${item.level}')">Удалить</button></td>`;
    lrBody.appendChild(tr);
  });
  if (!data.level_roles_view || data.level_roles_view.length === 0) {
    lrBody.innerHTML = '<tr><td colspan="3" style="color:var(--text-muted);">Роли за уровни ещё не назначены</td></tr>';
  }

  // Таблица лидеров
  const lbBody = document.querySelector('#leaderboard-table tbody');
  lbBody.innerHTML = '';
  (data.leaderboard || []).forEach((u, idx) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>#${idx+1}</td><td><b>${u.name}</b></td><td>⭐ ${u.level}</td><td>${u.xp} XP</td><td>${u.messages}</td><td>${u.voice}</td>`;
    lbBody.appendChild(tr);
  });
  if (!data.leaderboard || data.leaderboard.length === 0) {
    lbBody.innerHTML = '<tr><td colspan="6" style="color:var(--text-muted);">Пока нет данных об активности</td></tr>';
  }

  // Тикеты
  fillSelect('cfg-ticket-cat', data.categories, s.ticket_category_id);
  fillSelect('cfg-ticket-role', data.roles, s.support_role_id, '— Только администраторы —');
  fillSelect('cfg-ticket-log', data.text_channels, s.ticket_log_channel_id, '— Использовать основной канал логов —');
  document.getElementById('cfg-t-modal-title').value = s.ticket_modal_title || '';
  document.getElementById('cfg-t-f1-label').value = s.ticket_field1_label || '';
  document.getElementById('cfg-t-f1-ph').value = s.ticket_field1_placeholder || '';
  document.getElementById('cfg-t-f2-label').value = s.ticket_field2_label || '';
  document.getElementById('cfg-t-f2-ph').value = s.ticket_field2_placeholder || '';
  document.getElementById('cfg-t-w-title').value = s.ticket_welcome_title || '';
  document.getElementById('cfg-t-w-text').value = s.ticket_welcome_text || '';
  fillSelect('send-ticket-channel', data.text_channels, '', '— Выберите канал —', false);

  // Войсы
  fillSelect('cfg-voice-hub', data.voice_channels, s.voice_hub_channel_id);
  fillSelect('cfg-voice-cat', data.categories, s.voice_category_id);

  // Розыгрыши и Чистка
  fillSelect('cfg-gw-role', data.roles, s.giveaway_role_id, '— Только администраторы —');
  fillSelect('gw-channel', data.text_channels, '', '— Выберите канал —', false);
  fillSelect('gw-req-role', data.roles, '', '— Без обязательной роли —');
  fillSelect('purge-channel', data.text_channels, '', '— Выберите канал —', false);
}

async function initDashboard() {
  try {
    if (INITIAL_BOOTSTRAP && INITIAL_BOOTSTRAP.guilds && INITIAL_BOOTSTRAP.guilds.length > 0) {
      document.getElementById('bot-name-badge').textContent = INITIAL_BOOTSTRAP.bot_name || 'Online';
      const sel = document.getElementById('guild-select');
      sel.innerHTML = '';
      INITIAL_BOOTSTRAP.guilds.forEach(g => {
        const opt = document.createElement('option');
        opt.value = String(g.id);
        opt.textContent = g.name;
        sel.appendChild(opt);
      });
      if (INITIAL_BOOTSTRAP.first_guild) {
        renderGuildData(INITIAL_BOOTSTRAP.first_guild);
        return;
      }
    }

    const info = await apiCall('/api/guilds');
    document.getElementById('bot-name-badge').textContent = info.bot_name;
    const sel = document.getElementById('guild-select');
    sel.innerHTML = '';
    info.guilds.forEach(g => {
      const opt = document.createElement('option');
      opt.value = String(g.id);
      opt.textContent = g.name;
      sel.appendChild(opt);
    });
    if (info.guilds.length > 0) {
      await loadGuildData();
    }
  } catch (e) {
    showToast('❌ ' + e.message, true);
  }
}

async function loadGuildData(notify=false) {
  const gid = document.getElementById('guild-select').value;
  if (!gid) return;
  try {
    const data = await apiCall('/api/guild/' + gid);
    renderGuildData(data);
    if (notify) showToast('🔄 Данные сервера обновлены!');
  } catch (e) {
    showToast('❌ ' + e.message, true);
  }
}

async function saveGeneral() {
  const gid = document.getElementById('guild-select').value;
  await apiCall(`/api/guild/${gid}/settings`, 'POST', {
    log_channel_id: document.getElementById('cfg-log-channel').value || null,
    auto_role_id: document.getElementById('cfg-auto-role').value || null
  });
  showToast('✅ Логи и Автороль сохранены!');
  await loadGuildData();
}

async function sendTestLog() {
  const gid = document.getElementById('guild-select').value;
  try {
    const res = await apiCall(`/api/guild/${gid}/action`, 'POST', { action: 'test_log' });
    showToast(res.message);
  } catch (e) { showToast('❌ ' + e.message, true); }
}

async function fixPermissions() {
  const gid = document.getElementById('guild-select').value;
  try {
    const res = await apiCall(`/api/guild/${gid}/action`, 'POST', { action: 'fix_permissions' });
    showToast(res.message);
    await loadGuildData();
  } catch (e) { showToast('❌ ' + e.message, true); }
}

async function saveLevelsConfig() {
  const gid = document.getElementById('guild-select').value;
  await apiCall(`/api/guild/${gid}/settings`, 'POST', {
    levels_enabled: document.getElementById('cfg-levels-enabled').value === 'true',
    level_up_channel_id: document.getElementById('cfg-level-channel').value || null,
    level_roles_replace: document.getElementById('cfg-level-replace').value === 'true'
  });
  showToast('✅ Настройки системы уровней сохранены!');
  await loadGuildData();
}

async function addLevelRole() {
  const gid = document.getElementById('guild-select').value;
  const level = document.getElementById('new-lvl-num').value;
  const role_id = document.getElementById('new-lvl-role').value;
  if (!level || !role_id) return showToast('⚠️ Укажите уровень и роль', true);
  try {
    const res = await apiCall(`/api/guild/${gid}/action`, 'POST', { action: 'add_level_role', level, role_id });
    showToast(res.message);
    document.getElementById('new-lvl-num').value = '';
    await loadGuildData();
  } catch (e) { showToast('❌ ' + e.message, true); }
}

async function removeLevelRole(level) {
  const gid = document.getElementById('guild-select').value;
  try {
    const res = await apiCall(`/api/guild/${gid}/action`, 'POST', { action: 'remove_level_role', level });
    showToast(res.message);
    await loadGuildData();
  } catch (e) { showToast('❌ ' + e.message, true); }
}

async function modifyXp(op) {
  const gid = document.getElementById('guild-select').value;
  const user_id = document.getElementById('xp-member-select').value;
  const amount = parseInt(document.getElementById('xp-amount-input').value || '0', 10);
  if (!user_id) return showToast('⚠️ Выберите участника', true);
  try {
    const res = await apiCall(`/api/guild/${gid}/action`, 'POST', { action: 'modify_xp', op, user_id, amount });
    showToast(res.message);
    await loadGuildData();
  } catch (e) { showToast('❌ ' + e.message, true); }
}

async function saveTicketsConfig() {
  const gid = document.getElementById('guild-select').value;
  await apiCall(`/api/guild/${gid}/settings`, 'POST', {
    ticket_category_id: document.getElementById('cfg-ticket-cat').value || null,
    support_role_id: document.getElementById('cfg-ticket-role').value || null,
    ticket_log_channel_id: document.getElementById('cfg-ticket-log').value || null,
    ticket_modal_title: document.getElementById('cfg-t-modal-title').value,
    ticket_field1_label: document.getElementById('cfg-t-f1-label').value,
    ticket_field1_placeholder: document.getElementById('cfg-t-f1-ph').value,
    ticket_field2_label: document.getElementById('cfg-t-f2-label').value,
    ticket_field2_placeholder: document.getElementById('cfg-t-f2-ph').value,
    ticket_welcome_title: document.getElementById('cfg-t-w-title').value,
    ticket_welcome_text: document.getElementById('cfg-t-w-text').value
  });
  showToast('✅ Настройки тикетов сохранены!');
  await loadGuildData();
}

async function sendTicketPanel() {
  const gid = document.getElementById('guild-select').value;
  try {
    const res = await apiCall(`/api/guild/${gid}/action`, 'POST', {
      action: 'send_ticket_panel',
      channel_id: document.getElementById('send-ticket-channel').value,
      title: document.getElementById('send-ticket-title').value,
      description: document.getElementById('send-ticket-desc').value,
      button_text: document.getElementById('send-ticket-btn').value
    });
    showToast(res.message);
  } catch (e) { showToast('❌ ' + e.message, true); }
}

async function saveVoiceConfig() {
  const gid = document.getElementById('guild-select').value;
  await apiCall(`/api/guild/${gid}/settings`, 'POST', {
    voice_hub_channel_id: document.getElementById('cfg-voice-hub').value || null,
    voice_category_id: document.getElementById('cfg-voice-cat').value || null
  });
  showToast('✅ Настройки голосового хаба сохранены!');
  await loadGuildData();
}

async function autoCreateVoiceHub() {
  const gid = document.getElementById('guild-select').value;
  try {
    const res = await apiCall(`/api/guild/${gid}/action`, 'POST', { action: 'create_voice_hub' });
    showToast(res.message);
    await loadGuildData();
  } catch (e) { showToast('❌ ' + e.message, true); }
}

async function saveGiveawayConfig() {
  const gid = document.getElementById('guild-select').value;
  await apiCall(`/api/guild/${gid}/settings`, 'POST', {
    giveaway_role_id: document.getElementById('cfg-gw-role').value || null
  });
  showToast('✅ Роль ведущего розыгрышей сохранена!');
  await loadGuildData();
}

async function startGiveaway() {
  const gid = document.getElementById('guild-select').value;
  try {
    const res = await apiCall(`/api/guild/${gid}/action`, 'POST', {
      action: 'start_giveaway',
      channel_id: document.getElementById('gw-channel').value,
      prize: document.getElementById('gw-prize').value,
      duration: document.getElementById('gw-duration').value,
      winners: document.getElementById('gw-winners').value,
      req_role_id: document.getElementById('gw-req-role').value || null,
      req_level: document.getElementById('gw-req-level').value || 0,
      dm_text: document.getElementById('gw-dm-text').value
    });
    showToast(res.message);
    document.getElementById('gw-prize').value = '';
  } catch (e) { showToast('❌ ' + e.message, true); }
}

async function purgeChannel() {
  const gid = document.getElementById('guild-select').value;
  try {
    const res = await apiCall(`/api/guild/${gid}/action`, 'POST', {
      action: 'purge_channel',
      channel_id: document.getElementById('purge-channel').value,
      amount: document.getElementById('purge-amount').value,
      only_bots: document.getElementById('purge-bots').value === 'true'
    });
    showToast(res.message);
  } catch (e) { showToast('❌ ' + e.message, true); }
}

initDashboard();
</script>
</body>
</html>
"""


class DashboardLinkView(ui.View):
    """Кнопки для быстрого перехода на сайт управления ботом."""

    def __init__(self, url: str):
        super().__init__(timeout=None)
        self.add_item(ui.Button(
            label="🌐 Открыть сайт управления ботом",
            style=discord.ButtonStyle.link,
            url=url
        ))


class WebDashboard(commands.Cog):
    """Веб-панель управления всеми настройками бота через браузер."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.port = int(os.getenv("PORT", os.getenv("SERVER_PORT", "8080")))
        self.secret = get_or_create_secret()
        self.runner: web.AppRunner | None = None
        self.tunnel_proc: asyncio.subprocess.Process | None = None
        self.public_url: str | None = os.getenv("PUBLIC_URL", "").strip() or None
        self._startup_task = asyncio.create_task(self.start_web_server())

    def cog_unload(self):
        if self._startup_task:
            self._startup_task.cancel()
        if self.tunnel_proc:
            try:
                self.tunnel_proc.terminate()
            except Exception:
                pass
        if self.runner:
            asyncio.create_task(self.runner.cleanup())

    def _check_auth(self, request: web.Request) -> bool:
        token = (
            request.query.get("token")
            or request.headers.get("X-Auth-Token")
            or request.cookies.get("dash_token")
            or ""
        )
        return secrets.compare_digest(token.strip(), self.secret)

    async def start_web_server(self):
        await self.bot.wait_until_ready()
        app = web.Application()
        app.router.add_get("/", self.handle_index)
        app.router.add_get("/api/guilds", self.handle_guilds)
        app.router.add_get("/api/guild/{guild_id}", self.handle_guild_detail)
        app.router.add_post("/api/guild/{guild_id}/settings", self.handle_save_settings)
        app.router.add_post("/api/guild/{guild_id}/action", self.handle_guild_action)

        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", self.port)
        try:
            await site.start()
            logger.info(f"🌐 Веб-панель управления запущена на порту {self.port}")
        except Exception as e:
            logger.error(f"Не удалось запустить веб-панель на порту {self.port}: {e}")
            return

        if not self.public_url:
            asyncio.create_task(self.start_cloudflare_tunnel())

    async def start_cloudflare_tunnel(self):
        """Автоматически поднимает бесплатный публичный HTTPS-адрес (*.trycloudflare.com)."""
        try:
            sys_name = platform.system().lower()
            machine = platform.machine().lower()

            if sys_name == "linux" and machine in ("x86_64", "amd64"):
                bin_path = DATA_DIR / "cloudflared"
                if not bin_path.exists():
                    logger.info("🌐 Загрузка модуля HTTPS-туннеля (cloudflared) для веб-панели...")
                    url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
                    await asyncio.to_thread(urllib.request.urlretrieve, url, str(bin_path))
                    bin_path.chmod(bin_path.stat().st_mode | stat.S_IEXEC)
            elif sys_name == "windows":
                bin_path = DATA_DIR / "cloudflared.exe"
                if not bin_path.exists():
                    url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
                    await asyncio.to_thread(urllib.request.urlretrieve, url, str(bin_path))
            else:
                return

            self.tunnel_proc = await asyncio.create_subprocess_exec(
                str(bin_path), "tunnel", "--url", f"http://127.0.0.1:{self.port}", "--no-autoupdate",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
            while self.tunnel_proc.stderr:
                line_bytes = await self.tunnel_proc.stderr.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="ignore")
                match = pattern.search(line)
                if match:
                    self.public_url = match.group(0)
                    logger.info("=" * 60)
                    logger.info(f"🌐 ВЕБ-ПАНЕЛЬ УПРАВЛЕНИЯ ДОСТУПНА ПО ССЫЛКЕ:")
                    logger.info(f"👉 {self.public_url}/?token={self.secret}")
                    logger.info("(Или введите команду /сайт или /dashboard в Discord)")
                    logger.info("=" * 60)
                    break
        except Exception as e:
            logger.warning(f"Не удалось автоматически создать внешний туннель для веб-панели: {e}")

    def get_dashboard_url(self) -> str:
        base = self.public_url or f"http://127.0.0.1:{self.port}"
        return f"{base}/?token={self.secret}"

    def _build_guild_payload(self, guild: discord.Guild) -> dict:
        """Собирает полную информацию о сервере с безопасной строковой сериализацией 19-значных ID."""
        raw_settings = config_manager.get_guild(guild.id)

        # Важно: переводим все 64-битные Discord ID в строки, чтобы браузерный JS не округлял последние цифры!
        id_keys = {
            "log_channel_id", "auto_role_id", "level_up_channel_id",
            "ticket_category_id", "support_role_id", "ticket_log_channel_id",
            "voice_hub_channel_id", "voice_category_id", "giveaway_role_id"
        }
        safe_settings = {}
        for k, v in raw_settings.items():
            if k in id_keys:
                safe_settings[k] = str(v) if v else None
            elif k == "level_roles" and isinstance(v, dict):
                safe_settings[k] = {str(lk): str(rv) for lk, rv in v.items()}
            elif k == "giveaway_users" and isinstance(v, list):
                safe_settings[k] = [str(u) for u in v]
            else:
                safe_settings[k] = v

        text_channels = [{"id": str(c.id), "name": f"#{c.name}"} for c in guild.text_channels]
        voice_channels = [{"id": str(c.id), "name": f"🔊 {c.name}"} for c in guild.voice_channels]
        categories = [{"id": str(c.id), "name": f"📁 {c.name}"} for c in guild.categories]
        roles = [
            {"id": str(r.id), "name": f"@{r.name}"}
            for r in reversed(guild.roles)
            if not r.is_default() and not r.managed
        ]
        members = [
            {"id": str(m.id), "name": f"{m.display_name} ({m.name})"}
            for m in guild.members if not m.bot
        ][:250]

        level_roles = raw_settings.get("level_roles", {})
        replace_mode = raw_settings.get("level_roles_replace", True)
        sorted_tiers = sorted(
            [(int(lvl), int(rid)) for lvl, rid in level_roles.items() if str(lvl).isdigit()],
            key=lambda x: x[0]
        )
        level_roles_view = []
        for idx, (lvl, rid) in enumerate(sorted_tiers):
            r_obj = guild.get_role(rid)
            r_name = f"@{r_obj.name}" if r_obj else f"Удалена (ID: {rid})"
            if replace_mode:
                if idx + 1 < len(sorted_tiers):
                    next_lvl = sorted_tiers[idx + 1][0]
                    rng = f"Уровни {lvl} – {next_lvl - 1}"
                else:
                    rng = f"Уровень {lvl}+"
            else:
                rng = f"Уровень {lvl}"
            level_roles_view.append({"level": str(lvl), "range_text": rng, "role_name": r_name})

        top_raw = levels_manager.get_leaderboard(guild.id, limit=20)
        leaderboard = []
        for uid, udata in top_raw:
            m = guild.get_member(uid)
            m_name = m.display_name if m else f"ID: {uid}"
            v_sec = udata.get("voice_seconds", 0)
            leaderboard.append({
                "id": str(uid),
                "name": m_name,
                "level": udata.get("level", 0),
                "xp": udata.get("xp", 0),
                "messages": udata.get("messages", 0),
                "voice": f"{v_sec // 3600}ч {(v_sec % 3600) // 60}м"
            })

        lat = self.bot.latency
        ping_ms = round(lat * 1000) if (lat and not math.isnan(lat) and not math.isinf(lat)) else 0
        ev_perms = guild.default_role.permissions

        return {
            "id": str(guild.id),
            "name": guild.name,
            "member_count": guild.member_count or len(guild.members),
            "ping_ms": ping_ms,
            "settings": safe_settings,
            "text_channels": text_channels,
            "voice_channels": voice_channels,
            "categories": categories,
            "roles": roles,
            "members": members,
            "level_roles_view": level_roles_view,
            "leaderboard": leaderboard,
            "security": {
                "slash_ok": bool(ev_perms.use_application_commands),
                "webhooks_safe": not bool(ev_perms.manage_webhooks)
            }
        }

    # ==========================================
    # HTTP ОБРАБОТЧИКИ ВЕБ-ПАНЕЛИ
    # ==========================================

    async def handle_index(self, request: web.Request) -> web.Response:
        # Предзагружаем все данные сервера прямо в HTML, чтобы интерфейс открывался мгновенно со всеми настройками!
        guilds_list = [{"id": str(g.id), "name": g.name} for g in self.bot.guilds]
        first_guild_data = self._build_guild_payload(self.bot.guilds[0]) if self.bot.guilds else None

        bootstrap = {
            "bot_name": str(self.bot.user) if self.bot.user else "Bot Online",
            "guilds": guilds_list,
            "first_guild": first_guild_data
        }

        html = DASHBOARD_HTML.replace("__INJECTED_SECRET__", self.secret)
        html = html.replace("__INITIAL_BOOTSTRAP_JSON__", json.dumps(bootstrap, ensure_ascii=False))

        resp = web.Response(text=html, content_type="text/html")
        resp.set_cookie("dash_token", self.secret, max_age=86400 * 30, httponly=False)
        return resp

    async def handle_guilds(self, request: web.Request) -> web.Response:
        guilds = [{"id": str(g.id), "name": g.name} for g in self.bot.guilds]
        return web.json_response({
            "bot_name": str(self.bot.user),
            "guilds": guilds
        })

    async def handle_guild_detail(self, request: web.Request) -> web.Response:
        gid = int(request.match_info["guild_id"])
        guild = self.bot.get_guild(gid)
        if not guild:
            return web.json_response({"error": "Сервер не найден"}, status=404)
        return web.json_response(self._build_guild_payload(guild))

    async def handle_save_settings(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Доступ запрещен"}, status=403)

        gid = int(request.match_info["guild_id"])
        guild = self.bot.get_guild(gid)
        if not guild:
            return web.json_response({"error": "Сервер не найден"}, status=404)

        body = await request.json()
        int_keys = {
            "log_channel_id", "auto_role_id", "level_up_channel_id",
            "ticket_category_id", "support_role_id", "ticket_log_channel_id",
            "voice_hub_channel_id", "voice_category_id", "giveaway_role_id"
        }
        bool_keys = {"levels_enabled", "level_roles_replace"}
        str_keys = {
            "ticket_modal_title", "ticket_field1_label", "ticket_field1_placeholder",
            "ticket_field2_label", "ticket_field2_placeholder",
            "ticket_welcome_title", "ticket_welcome_text"
        }

        for k, val in body.items():
            if k in int_keys:
                config_manager.set_guild_value(guild.id, k, int(val) if val else None)
            elif k in bool_keys:
                config_manager.set_guild_value(guild.id, k, bool(val))
            elif k in str_keys and isinstance(val, str):
                config_manager.set_guild_value(guild.id, k, val.strip())

        return web.json_response({"ok": True})

    async def handle_guild_action(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Доступ запрещен"}, status=403)

        gid = int(request.match_info["guild_id"])
        guild = self.bot.get_guild(gid)
        if not guild:
            return web.json_response({"error": "Сервер не найден"}, status=404)

        body = await request.json()
        action = body.get("action")

        # 1. Тестовый лог
        if action == "test_log":
            cid = config_manager.get_guild(guild.id).get("log_channel_id")
            if not cid:
                return web.json_response({"error": "Сначала выберите и сохраните канал логов!"}, status=400)
            ch = guild.get_channel(int(cid))
            if not isinstance(ch, discord.TextChannel):
                return web.json_response({"error": "Канал логов не найден на сервере"}, status=400)
            embed = discord.Embed(
                title="Проверка системы логирования",
                description="✅ Тестовый лог успешно отправлен с Веб-Панели управления ботом!",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Сервер: {guild.name}")
            await ch.send(embed=embed)
            return web.json_response({"message": f"✅ Тестовый лог отправлен в #{ch.name}!"})

        # 2. Починка прав /rank и защита @everyone
        if action == "fix_permissions":
            fixed = []
            if hasattr(self.bot, "ensure_member_command_permissions"):
                fixed = await self.bot.ensure_member_command_permissions(guild)
            if guild.me.guild_permissions.manage_roles:
                try:
                    p = guild.default_role.permissions
                    p.update(
                        use_application_commands=True,
                        manage_webhooks=False,
                        mention_everyone=False
                    )
                    if hasattr(p, "use_external_apps"):
                        p.use_external_apps = False
                    await guild.default_role.edit(permissions=p, reason="Защита сервера и включение /rank через Веб-Панель")
                except Exception:
                    pass
            return web.json_response({
                "message": f"✅ Права для /rank и /ранг открыты, защита @everyone включена! ({len(fixed)} объектов обновлено)"
            })

        # 3. Добавление роли за уровень
        if action == "add_level_role":
            lvl = int(body.get("level", 0))
            rid = int(body.get("role_id", 0))
            if lvl < 1 or not rid:
                return web.json_response({"error": "Некорректный уровень или роль"}, status=400)
            settings = config_manager.get_guild(guild.id)
            lr = settings.get("level_roles", {})
            lr[str(lvl)] = rid
            config_manager.set_guild_value(guild.id, "level_roles", lr)
            return web.json_response({"message": f"✅ Назначена роль за {lvl} уровень!"})

        # 4. Удаление роли за уровень
        if action == "remove_level_role":
            lvl = str(body.get("level", ""))
            settings = config_manager.get_guild(guild.id)
            lr = settings.get("level_roles", {})
            if lvl in lr:
                del lr[lvl]
                config_manager.set_guild_value(guild.id, "level_roles", lr)
            return web.json_response({"message": f"🗑️ Роль за {lvl} уровень удалена."})

        # 5. Управление опытом участника
        if action == "modify_xp":
            op = body.get("op")
            uid = int(body.get("user_id", 0))
            amount = int(body.get("amount", 0))
            member = guild.get_member(uid)
            lvl_cog = self.bot.get_cog("Leveling")

            if op == "add":
                _, new_lvl, _ = levels_manager.add_xp(guild.id, uid, amount)
                if member and lvl_cog:
                    await lvl_cog.update_member_level_roles(guild, member, new_lvl)
                levels_manager.save()
                return web.json_response({"message": f"✅ Начислено +{amount} XP (Уровень: {new_lvl})"})
            elif op == "remove":
                udata = levels_manager.get_user_data(guild.id, uid)
                new_xp = max(0, udata.get("xp", 0) - amount)
                _, new_lvl = levels_manager.set_xp(guild.id, uid, new_xp)
                if member and lvl_cog:
                    await lvl_cog.update_member_level_roles(guild, member, new_lvl)
                levels_manager.save()
                return web.json_response({"message": f"✅ Списано -{amount} XP (Уровень: {new_lvl})"})
            elif op == "reset":
                levels_manager.reset_user(guild.id, uid)
                if member and lvl_cog:
                    await lvl_cog.update_member_level_roles(guild, member, 0)
                levels_manager.save()
                return web.json_response({"message": "🗑️ Опыт и уровень участника сброшены!"})

        # 6. Публикация панели тикетов
        if action == "send_ticket_panel":
            cid = int(body.get("channel_id", 0))
            ch = guild.get_channel(cid)
            if not isinstance(ch, discord.TextChannel):
                return web.json_response({"error": "Канал не найден"}, status=400)
            embed = discord.Embed(
                title=body.get("title") or "🎫 Поддержка и обратная связь",
                description=body.get("description") or "Нажмите на кнопку ниже, чтобы создать обращение.",
                color=discord.Color.blue()
            )
            btn_label = body.get("button_text") or "Создать тикет"
            await ch.send(embed=embed, view=TicketLauncherView(button_label=btn_label))
            return web.json_response({"message": f"✅ Панель тикетов отправлена в #{ch.name}!"})

        # 7. Авто-создание голосового хаба
        if action == "create_voice_hub":
            cat = await guild.create_category("🔊 Голосовые комнаты")
            hub = await guild.create_voice_channel("➕ Создать канал", category=cat)
            config_manager.set_guild_value(guild.id, "voice_category_id", cat.id)
            config_manager.set_guild_value(guild.id, "voice_hub_channel_id", hub.id)
            return web.json_response({"message": "✅ Категория и канал «➕ Создать канал» успешно созданы!"})

        # 8. Запуск розыгрыша с сайта
        if action == "start_giveaway":
            cid = int(body.get("channel_id", 0))
            ch = guild.get_channel(cid)
            if not isinstance(ch, discord.TextChannel):
                return web.json_response({"error": "Выберите текстовый канал"}, status=400)
            prize = (body.get("prize") or "").strip()
            if not prize:
                return web.json_response({"error": "Укажите название приза"}, status=400)
            seconds = parse_duration(body.get("duration") or "1h")
            if not seconds or seconds < 10:
                return web.json_response({"error": "Некорректная длительность (пример: 30м, 2ч, 1д)"}, status=400)

            winners_count = max(1, min(50, int(body.get("winners") or 1)))
            req_role_id = int(body["req_role_id"]) if body.get("req_role_id") else None
            req_level = max(0, int(body.get("req_level") or 0))
            dm_text = (body.get("dm_text") or "").strip() or None

            now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
            end_time = now_ts + seconds
            gdata = {
                "guild_id": guild.id,
                "channel_id": ch.id,
                "message_id": 0,
                "prize": prize,
                "description": None,
                "dm_message": dm_text,
                "host_id": guild.owner_id or self.bot.user.id,
                "winners_count": winners_count,
                "created_at": now_ts,
                "end_timestamp": end_time,
                "required_role_id": req_role_id,
                "min_level": req_level,
                "participants": [],
                "ended": False,
                "cancelled": False,
                "winners": []
            }
            embed = build_giveaway_embed(gdata, guild)
            msg = await ch.send(embed=embed, view=GiveawayJoinView())
            gdata["message_id"] = msg.id
            giveaways_manager.add_giveaway(msg.id, gdata)
            try:
                await msg.edit(embed=build_giveaway_embed(gdata, guild))
            except Exception:
                pass
            return web.json_response({"message": f"🎉 Розыгрыш «{prize}» запущен в #{ch.name}!"})

        # 9. Очистка чата с сайта
        if action == "purge_channel":
            cid = int(body.get("channel_id", 0))
            ch = guild.get_channel(cid)
            if not isinstance(ch, discord.TextChannel):
                return web.json_response({"error": "Канал не найден"}, status=400)
            amount = max(1, min(100, int(body.get("amount") or 10)))
            only_bots = bool(body.get("only_bots"))
            deleted = await ch.purge(
                limit=amount,
                check=(lambda m: m.author.bot or m.webhook_id is not None) if only_bots else None,
                bulk=True
            )
            return web.json_response({"message": f"🧹 В канале #{ch.name} удалено {len(deleted)} сообщений!"})

        return web.json_response({"error": "Неизвестное действие"}, status=400)

    # ==========================================
    # КОМАНДЫ В DISCORD ДЛЯ ПОЛУЧЕНИЯ ССЫЛКИ НА САЙТ
    # ==========================================

    async def _send_dashboard_info(self, interaction: discord.Interaction):
        url = self.get_dashboard_url()
        local_url = f"http://127.0.0.1:{self.port}/?token={self.secret}"

        embed = discord.Embed(
            title="🌐 Веб-Панель управления сервером",
            description=(
                "Все настройки бота (логи, автороль, диапазоны рангов, опыт участников, тикеты, голосовые каналы, розыгрыши и чистка чата) доступны в удобном веб-интерфейсе!\n\n"
                f"🔗 **Ссылка для входа:**\n[Нажмите здесь, чтобы открыть сайт управления]({url})\n\n"
                f"🏠 **Локальный адрес (если бот на ПК/VPS):**\n`{local_url}`\n\n"
                "⚠️ *Не передавайте эту ссылку посторонним — в неё уже встроен ваш секретный ключ администратора.*"
            ),
            color=discord.Color.blurple()
        )
        if not self.public_url:
            embed.set_footer(text="Подождите 5–10 секунд после запуска бота, если внешний HTTPS-туннель ещё подключается.")
        else:
            embed.set_footer(text="Защищённое HTTPS-соединение активно")

        await interaction.response.send_message(
            embed=embed,
            view=DashboardLinkView(url),
            ephemeral=True
        )

    @app_commands.command(
        name="сайт",
        description="Открыть веб-сайт для удобной настройки всех функций бота в браузере"
    )
    @app_commands.default_permissions(administrator=True)
    async def cmd_site_ru(self, interaction: discord.Interaction):
        await self._send_dashboard_info(interaction)

    @app_commands.command(
        name="dashboard",
        description="Открыть веб-панель управления всеми настройками бота в браузере"
    )
    @app_commands.default_permissions(administrator=True)
    async def cmd_dashboard(self, interaction: discord.Interaction):
        await self._send_dashboard_info(interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(WebDashboard(bot))
