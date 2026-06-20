# Job & Ausbildung Telegram Bot

Бот ищет вакансии и места Ausbildung через официальное публичное REST API
**Bundesagentur für Arbeit** (крупнейшая база вакансий Германии) и присылает
результаты в Telegram — по команде и автоматически раз в час.

## Возможности

- `/search <слова>` — разовый поиск вакансий в заданном городе
- `/ausbildung <слова>` — разовый поиск Ausbildung / дуального обучения
- `/watch job|ausbildung <слова>` — подписка с автопроверкой (по умолчанию раз в час)
- `/list` — список подписок
- `/unwatch <id>` — удалить подписку
- Фильтр по типу занятости через `|`: `vz` Vollzeit, `tz` Teilzeit,
  `ho` Homeoffice, `mj` Minijob, `snw` смена/ночь/выходные
- Поиск на русском: словарь профессий + авто-перевод RU→DE (MyMemory),
  поэтому можно писать «экономист», «логопед», «кровельщик» и т.п.
- Выдача постранично по 5 с кнопкой «Показать ещё»
- Дедупликация: в подписке приходят только новые объявления (SQLite)
- Приватность: бот отвечает только разрешённым `chat_id`

### Примеры

```
/search Fachinformatiker | vz tz
/ausbildung Koch | ho
/watch job Lagerist | tz
```

## Источник данных

Неофициальное, но стабильное и широко используемое REST API
(`https://rest.arbeitsagentur.de`), аутентификация фиксированным заголовком
`X-API-Key: jobboerse-jobsuche`. Документация: <https://jobsuche.api.bund.dev/>.

> Почему не StepStone/Indeed/LinkedIn: их условия использования запрещают
> скрейпинг, и они активно блокируют ботов. API Arbeitsagentur легально
> и покрывает большинство вакансий, т.к. работодатели обязаны там публиковаться.

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# заполни TELEGRAM_BOT_TOKEN и ALLOWED_CHAT_IDS
```

Токен бота — у [@BotFather](https://t.me/BotFather).
Свой `chat_id` — у [@userinfobot](https://t.me/userinfobot).

## Запуск

```bash
python bot.py
```

### Фоновый запуск на macOS (launchd)

```bash
# 1. Подставь свой путь к проекту вместо __PROJECT_DIR__
cp com.jobsbot.chemnitz.plist.template ~/Library/LaunchAgents/com.jobsbot.chemnitz.plist
# отредактируй ~/Library/LaunchAgents/com.jobsbot.chemnitz.plist (замени __PROJECT_DIR__)

# 2. Запусти службу (работает в фоне, перезапуск при падении и старте системы)
launchctl load ~/Library/LaunchAgents/com.jobsbot.chemnitz.plist

# управление
launchctl list | grep jobsbot              # статус
launchctl unload ~/Library/LaunchAgents/com.jobsbot.chemnitz.plist  # стоп
```

## Настройки (`.env`)

| Переменная | По умолчанию | Описание |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | Токен бота (обязательно) |
| `ALLOWED_CHAT_IDS` | — | Разрешённые chat_id через запятую (обязательно) |
| `DEFAULT_CITY` | `Chemnitz` | Город поиска |
| `DEFAULT_RADIUS_KM` | `25` | Радиус вокруг города |
| `POLL_INTERVAL_MINUTES` | `60` | Период автопроверки подписок |
| `PUBLISHED_SINCE_DAYS` | `30` | Окно по дате последней публикации для ручного поиска вакансий (0–100) |
| `AUSBILDUNG_SINCE_DAYS` | `100` | Глубина поиска Ausbildung по дате (0–100) |
| `SUBSCRIPTION_SINCE_DAYS` | `14` | Окно свежести для уведомлений по подпискам (0–100) |
| `DEFAULT_ARBEITSZEIT` | (пусто) | Тип занятости по умолчанию: `vz tz ho mj snw` |
| `DB_PATH` | `jobs.db` | Файл базы SQLite |
