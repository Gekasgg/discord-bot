@echo off
chcp 65001 > nul
title Discord Bot (Logs & Tickets)
echo ====================================================
echo Запуск Discord Бота (Логирование + Тикеты)
echo ====================================================

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не обнаружен в системе!
    echo Установите Python с официального сайта python.org и поставьте галочку "Add to PATH".
    pause
    exit /b 1
)

echo Проверка и установка зависимостей...
python -m pip install -r requirements.txt

echo.
echo Запуск бота...
python bot.py

pause
