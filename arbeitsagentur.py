"""Клиент к публичному REST API Bundesagentur für Arbeit (Jobsuche).

Документация: https://jobsuche.api.bund.dev/
Аутентификация: фиксированный заголовок X-API-Key: jobboerse-jobsuche
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import IntEnum

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
_API_KEY = "jobboerse-jobsuche"
_DETAIL_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/"

_HEADERS = {
    "X-API-Key": _API_KEY,
    "User-Agent": "JobsucheBot/1.0 (+https://jobsuche.api.bund.dev/)",
    "Accept": "application/json",
}

_MAX_RETRIES = 3
_TIMEOUT_SECONDS = 30.0


class OfferType(IntEnum):
    """angebotsart из API."""

    JOB = 1
    AUSBILDUNG = 4


ARBEITSZEIT_LABELS: dict[str, str] = {
    "vz": "Vollzeit",
    "tz": "Teilzeit",
    "ho": "Homeoffice",
    "mj": "Minijob",
    "snw": "Schicht/Nacht/Wochenende",
}

_ARBEITSZEIT_ALIASES: dict[str, str] = {
    "vz": "vz", "vollzeit": "vz", "fulltime": "vz", "full": "vz",
    "tz": "tz", "teilzeit": "tz", "parttime": "tz", "part": "tz",
    "ho": "ho", "homeoffice": "ho", "remote": "ho", "home": "ho",
    "mj": "mj", "minijob": "mj", "mini": "mj",
    "snw": "snw", "schicht": "snw", "nacht": "snw", "wochenende": "snw",
}


def normalize_arbeitszeit(tokens: list[str]) -> tuple[str | None, list[str]]:
    """Преобразует слова пользователя в коды API (vz;tz;...).

    Возвращает (строка_кодов_или_None, список_нераспознанных_токенов).
    """
    codes: list[str] = []
    invalid: list[str] = []
    for token in tokens:
        key = token.strip().lower()
        if not key:
            continue
        code = _ARBEITSZEIT_ALIASES.get(key)
        if code is None:
            invalid.append(token)
        elif code not in codes:
            codes.append(code)
    return (";".join(codes) if codes else None, invalid)


class ArbeitsagenturError(RuntimeError):
    """Не удалось получить данные от API."""


@dataclass(frozen=True)
class JobListing:
    refnr: str
    title: str
    employer: str
    city: str
    published: str
    url: str

    @classmethod
    def from_api(cls, item: dict) -> JobListing | None:
        refnr = item.get("refnr")
        if not refnr:
            return None
        ort = (item.get("arbeitsort") or {}).get("ort") or "—"
        external = item.get("externeUrl")
        url = external or f"{_DETAIL_URL}{refnr}"
        return cls(
            refnr=str(refnr),
            title=str(item.get("titel") or item.get("beruf") or "Без названия"),
            employer=str(item.get("arbeitgeber") or "—"),
            city=str(ort),
            published=str(item.get("aktuelleVeroeffentlichungsdatum") or "—"),
            url=url,
        )


async def search(
    *,
    what: str | None,
    where: str,
    offer_type: OfferType,
    radius_km: int,
    published_since_days: int,
    arbeitszeit: str | None = None,
    size: int = 50,
) -> list[JobListing]:
    """Ищет объявления. Бросает ArbeitsagenturError при сетевой ошибке."""
    params: dict[str, object] = {
        "wo": where,
        "umkreis": radius_km,
        "angebotsart": int(offer_type),
        "page": 1,
        "size": max(1, min(size, 100)),
        "pav": "false",
    }
    if what and what.strip():
        params["was"] = what.strip()
    if published_since_days > 0:
        params["veroeffentlichtseit"] = published_since_days
    if arbeitszeit:
        params["arbeitszeit"] = arbeitszeit

    payload = await _request_with_retry(params)
    items = payload.get("stellenangebote") or []
    listings = (JobListing.from_api(item) for item in items)
    return [listing for listing in listings if listing is not None]


async def _request_with_retry(params: dict[str, object]) -> dict:
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, headers=_HEADERS) as client:
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await client.get(_BASE_URL, params=params)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_exc = exc
                logger.warning("Запрос к API не удался (попытка %s): %s", attempt, exc)
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)
    raise ArbeitsagenturError("API недоступно") from last_exc
