"""Загрузка и валидация конфигурации из переменных окружения."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from arbeitsagentur import normalize_arbeitszeit

load_dotenv()


class ConfigError(RuntimeError):
    """Конфигурация некорректна или неполна."""


def _get_int(name: str, default: int, *, lo: int, hi: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} должен быть целым числом") from exc
    if not lo <= value <= hi:
        raise ConfigError(f"{name} должен быть в диапазоне {lo}..{hi}")
    return value


def _parse_chat_ids(raw: str | None) -> frozenset[int]:
    if not raw or not raw.strip():
        return frozenset()
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError as exc:
            raise ConfigError(f"Некорректный chat_id: {part!r}") from exc
    return frozenset(ids)


def _parse_arbeitszeit(raw: str | None) -> str:
    if not raw or not raw.strip():
        return ""
    codes, invalid = normalize_arbeitszeit(raw.replace(";", " ").split())
    if invalid:
        raise ConfigError(
            "DEFAULT_ARBEITSZEIT содержит неизвестные значения: "
            + ", ".join(invalid)
        )
    return codes or ""


@dataclass(frozen=True)
class Config:
    bot_token: str
    allowed_chat_ids: frozenset[int]
    default_city: str
    default_radius_km: int
    poll_interval_minutes: int
    published_since_days: int
    ausbildung_since_days: int
    subscription_since_days: int
    db_path: str
    default_arbeitszeit: str

    @classmethod
    def load(cls) -> Config:
        token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        if not token:
            raise ConfigError(
                "TELEGRAM_BOT_TOKEN не задан. Заполни .env (см. .env.example)."
            )

        allowed = _parse_chat_ids(os.getenv("ALLOWED_CHAT_IDS"))
        if not allowed:
            raise ConfigError(
                "ALLOWED_CHAT_IDS не задан. Укажи свой chat_id, "
                "иначе ботом сможет пользоваться кто угодно."
            )

        return cls(
            bot_token=token,
            allowed_chat_ids=allowed,
            default_city=(os.getenv("DEFAULT_CITY") or "Chemnitz").strip(),
            default_radius_km=_get_int("DEFAULT_RADIUS_KM", 25, lo=0, hi=300),
            poll_interval_minutes=_get_int("POLL_INTERVAL_MINUTES", 60, lo=5, hi=1440),
            published_since_days=_get_int("PUBLISHED_SINCE_DAYS", 30, lo=0, hi=100),
            ausbildung_since_days=_get_int(
                "AUSBILDUNG_SINCE_DAYS", 100, lo=0, hi=100
            ),
            subscription_since_days=_get_int(
                "SUBSCRIPTION_SINCE_DAYS", 14, lo=0, hi=100
            ),
            db_path=(os.getenv("DB_PATH") or "jobs.db").strip(),
            default_arbeitszeit=_parse_arbeitszeit(os.getenv("DEFAULT_ARBEITSZEIT")),
        )
