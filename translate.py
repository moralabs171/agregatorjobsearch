"""Перевод запроса с русского на немецкий через бесплатный API MyMemory.

Без API-ключа. Используется как запасной вариант, когда слова нет в словаре.
Документация: https://mymemory.translated.net/doc/spec.php
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_URL = "https://api.mymemory.translated.net/get"
_TIMEOUT_SECONDS = 8.0
_MAX_LEN = 100


def has_cyrillic(text: str) -> bool:
    """True, если в строке есть кириллица (значит, нужен перевод)."""
    return any("\u0400" <= ch <= "\u04ff" for ch in text)


async def translate_ru_de(text: str) -> str | None:
    """Переводит русский текст на немецкий.

    Возвращает перевод или None при любой ошибке/пустом результате.
    Исключения не пробрасываются — вызывающий код продолжает с исходным текстом.
    """
    query = (text or "").strip()
    if not query or len(query) > _MAX_LEN:
        return None
    params = {"q": query, "langpair": "ru|de", "de": "jobsbot@example.com"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Перевод не удался: %s", exc)
        return None

    if not isinstance(data, dict):
        return None
    if data.get("responseStatus") != 200:
        return None
    translated = (data.get("responseData") or {}).get("translatedText")
    if not translated or not isinstance(translated, str):
        return None
    translated = translated.strip()
    # MyMemory при ошибке иногда возвращает само сообщение об ошибке.
    if not translated or translated.upper() == query.upper():
        return None
    if "MYMEMORY WARNING" in translated.upper() or "INVALID" in translated.upper():
        return None
    # Для одного слова MyMemory иногда склеивает мусор ("JURIST verliehn").
    # Берём только первое слово и нормализуем регистр (нем. существительные с большой).
    if " " not in query and " " in translated:
        translated = translated.split()[0]
    if translated.isupper():
        translated = translated.capitalize()
    return translated
