"""Тесты загрузки и валидации конфигурации."""
from __future__ import annotations

import pytest

from config import Config, ConfigError

_REQUIRED = {
    "TELEGRAM_BOT_TOKEN": "123:abc",
    "ALLOWED_CHAT_IDS": "111,222",
}

_OPTIONAL_KEYS = [
    "DEFAULT_CITY",
    "DEFAULT_RADIUS_KM",
    "POLL_INTERVAL_MINUTES",
    "PUBLISHED_SINCE_DAYS",
    "AUSBILDUNG_SINCE_DAYS",
    "SUBSCRIPTION_SINCE_DAYS",
    "DEFAULT_ARBEITSZEIT",
    "DB_PATH",
]


@pytest.fixture()
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Чистое окружение: только обязательные переменные, остальное удалено."""
    for key in _OPTIONAL_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in _REQUIRED.items():
        monkeypatch.setenv(key, value)


def test_load_defaults(clean_env: None) -> None:
    config = Config.load()
    assert config.bot_token == "123:abc"
    assert config.allowed_chat_ids == frozenset({111, 222})
    assert config.default_city == "Chemnitz"
    assert config.published_since_days == 30
    assert config.subscription_since_days == 14
    assert config.ausbildung_since_days == 100


def test_missing_token_raises(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(ConfigError):
        Config.load()


def test_missing_allowed_ids_raises(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ALLOWED_CHAT_IDS", raising=False)
    with pytest.raises(ConfigError):
        Config.load()


def test_invalid_chat_id_raises(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "111,notanumber")
    with pytest.raises(ConfigError):
        Config.load()


def test_int_out_of_range_raises(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PUBLISHED_SINCE_DAYS", "9999")
    with pytest.raises(ConfigError):
        Config.load()


def test_invalid_default_arbeitszeit_raises(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEFAULT_ARBEITSZEIT", "vz nonsense")
    with pytest.raises(ConfigError):
        Config.load()


def test_arbeitszeit_normalized(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEFAULT_ARBEITSZEIT", "vollzeit teilzeit")
    config = Config.load()
    assert config.default_arbeitszeit == "vz;tz"
