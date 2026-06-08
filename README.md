# YouTube → Discord через GitHub Actions

Этот проект автоматически проверяет YouTube RSS и постит новое видео в Discord через webhook.

## Что внутри

- `youtube_to_discord.py` — основной скрипт
- `.github/workflows/youtube-discord.yml` — запуск каждые 5 минут
- `state.json` — создастся автоматически после первого запуска

## 1. Создай GitHub репозиторий

Загрузи в него все файлы из этой папки.

## 2. Добавь GitHub Secrets

В репозитории открой:
`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

Создай такие секреты:

- `DISCORD_WEBHOOK_URL` — URL твоего Discord webhook
- `YOUTUBE_CHANNEL_ID` — ID YouTube-канала
- `DISCORD_ROLE_ID` — ID роли для пинга, если нужен; если не нужен, можно оставить пустым
- `BOT_NAME` — имя webhook-бота, например `YouTube Notifier`
- `BOT_AVATAR_URL` — ссылка на аватар, можно оставить пустым

## 3. Включи GitHub Actions

Открой вкладку `Actions` и разреши запуск workflow, если GitHub попросит.

## 4. Первый запуск

Запусти workflow вручную через `Actions` → `YouTube to Discord` → `Run workflow`.

Первый запуск **не отправляет сообщение** в Discord. Он только сохраняет текущее последнее видео в `state.json`, чтобы бот не запостил старый ролик как новый.

## 5. Дальше всё автоматически

После этого workflow будет запускаться по расписанию каждые 5 минут.

## Как получить YouTube Channel ID

Открой канал и найди именно `channel_id`, затем подставь его в RSS-ленту:

`https://www.youtube.com/feeds/videos.xml?channel_id=ТВОЙ_CHANNEL_ID`

## Как тегнуть роль

Для роли используется формат `<@&ROLE_ID>`. Скрипт автоматически подставит его в `content`, если секрет `DISCORD_ROLE_ID` заполнен.

## Важно

- У роли должно быть разрешено упоминание, иначе пинг может не сработать.
- Никому не показывай `DISCORD_WEBHOOK_URL`.
- GitHub Actions для `schedule` запускается минимум раз в 5 минут, иногда бывают небольшие задержки.


---
*Last updated: 2026-06-08*
