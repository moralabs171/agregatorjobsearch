# Job & Ausbildung Telegram Bot

![CI](https://github.com/moralabs171/parserjobsearch/actions/workflows/ci.yml/badge.svg)

A Telegram bot that searches **jobs** and **Ausbildung** (apprenticeship) openings via
the public REST API of the **Bundesagentur für Arbeit** — Germany's largest job
database — and delivers results on demand and via hourly subscriptions.

It speaks both German and Russian: type a profession in Russian (e.g. «электрик»,
«логопед») and the bot maps or translates it to the German query automatically.

## Features

- **On-demand search** for jobs and Ausbildung in a configurable city/radius.
- **Two search modes** from the inline menu:
  - 🔍 *Search all* — everything currently open (wider window).
  - 🆕 *Fresh only* — just recently (re)published listings.
- **Hourly subscriptions** that notify you about **new** matches only
  (deduplicated via SQLite, so you never get the same listing twice).
- **Russian input support** — a profession dictionary plus automatic RU→DE
  translation (MyMemory) and fuzzy typo correction.
- **Employment-type filters**: `vz` Vollzeit, `tz` Teilzeit, `ho` Homeoffice,
  `mj` Minijob, `snw` shift/night/weekend.
- **Paginated results** (5 per page with a "Show more" button).
- **Duplicate-safe subscriptions** — an accidental double-tap won't create copies.
- **Clean per-user numbering** for subscriptions (1, 2, 3…), independent of
  internal database ids.
- **Private by design** — the bot only answers allow-listed `chat_id`s.

### Command reference

| Command | Description |
|---|---|
| `/search <words>` | One-off job search |
| `/ausbildung <words>` | One-off Ausbildung search |
| `/watch job\|ausbildung <words>` | Subscribe (hourly checks) |
| `/list` | List your subscriptions |
| `/unwatch <number>` | Remove a subscription (number from `/list`) |

Examples:

```
/search Fachinformatiker | vz tz
/ausbildung Koch | ho
/watch job Lagerist | tz
```

## Data source

Uses the public REST API at `https://rest.arbeitsagentur.de` (fixed header
`X-API-Key: jobboerse-jobsuche`). API docs: <https://jobsuche.api.bund.dev/>.
It is unofficial but stable and widely used.

> **Why not StepStone/Indeed/LinkedIn?** Their terms of service forbid scraping
> and they actively block bots. The Arbeitsagentur API is a legal, structured
> source that covers most German vacancies, since employers are required to list there.

The bot filters and displays the `aktuelleVeroeffentlichungsdatum` (latest
publication date). Stale, forgotten postings that employers never refresh
naturally drop out of narrow time windows, while actively maintained ones stay.

## Architecture

The code is split into small, single-responsibility modules:

| Module | Responsibility |
|---|---|
| `bot.py` | Telegram handlers, keyboards, conversation/UX flow |
| `arbeitsagentur.py` | API client: request/retry, parsing, employment-type normalization |
| `storage.py` | SQLite persistence: subscriptions + per-subscription "seen" dedup |
| `config.py` | Environment loading & validation (fails fast on bad config) |
| `translate.py` | RU→DE translation fallback (network-isolated, never raises) |

```
parser/
├── bot.py                # Telegram bot & handlers
├── arbeitsagentur.py     # Arbeitsagentur API client
├── storage.py            # SQLite layer
├── config.py             # Config loading/validation
├── translate.py          # RU→DE translation
├── tests/                # pytest suite (unit + mocked network)
├── .github/workflows/    # CI (ruff + pytest on 3.11 & 3.12)
├── requirements.txt      # Runtime deps
├── requirements-dev.txt  # Dev/test deps
├── pyproject.toml        # pytest & ruff config
└── DECISIONS.md          # Architecture decision log
```

## Tech stack

Python 3.11+, [python-telegram-bot](https://python-telegram-bot.org/) 21.x,
`httpx` (async), SQLite (stdlib), `pytest` + `pytest-asyncio`, `ruff`.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in TELEGRAM_BOT_TOKEN and ALLOWED_CHAT_IDS
```

Get a bot token from [@BotFather](https://t.me/BotFather) and your `chat_id`
from [@userinfobot](https://t.me/userinfobot).

## Run

```bash
python bot.py
```

### Run in the background on macOS (launchd)

```bash
# 1. Copy the template and replace __PROJECT_DIR__ with your project path
cp com.jobsbot.chemnitz.plist.template ~/Library/LaunchAgents/com.jobsbot.chemnitz.plist

# 2. Start the service (auto-restarts on crash and at login)
launchctl load ~/Library/LaunchAgents/com.jobsbot.chemnitz.plist

# manage
launchctl list | grep jobsbot                                       # status
launchctl kickstart -k gui/$(id -u)/com.jobsbot.chemnitz            # restart
launchctl unload ~/Library/LaunchAgents/com.jobsbot.chemnitz.plist  # stop
```

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | Bot token (required) |
| `ALLOWED_CHAT_IDS` | — | Comma-separated allowed chat ids (required) |
| `DEFAULT_CITY` | `Chemnitz` | Search city |
| `DEFAULT_RADIUS_KM` | `25` | Radius around the city |
| `POLL_INTERVAL_MINUTES` | `60` | Subscription check interval |
| `PUBLISHED_SINCE_DAYS` | `30` | Publication-date window for manual job search (0–100) |
| `AUSBILDUNG_SINCE_DAYS` | `100` | Publication-date window for Ausbildung (0–100) |
| `SUBSCRIPTION_SINCE_DAYS` | `14` | Freshness window for subscription notifications (0–100) |
| `DEFAULT_ARBEITSZEIT` | (empty) | Default employment type: `vz tz ho mj snw` |
| `DB_PATH` | `jobs.db` | SQLite database file |

## Testing & linting

```bash
pip install -r requirements-dev.txt
pytest            # run the test suite
ruff check .      # lint
```

CI runs `ruff` and `pytest` on Python 3.11 and 3.12 for every push and pull request.

## Security notes

- Secrets live only in `.env` (git-ignored); `.env.example` ships placeholders.
- Access is restricted to allow-listed `chat_id`s.
- All SQL uses parameterized queries; user output is HTML-escaped.
- The translation call is HTTPS-only, length-limited, and never propagates
  exceptions to the user.
- Bot-token URLs are kept out of logs (httpx logger raised to WARNING).

See [`DECISIONS.md`](DECISIONS.md) for the architecture decision log.
