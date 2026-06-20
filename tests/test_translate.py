"""Тесты перевода RU->DE. Сеть замокана — реальных запросов не делаем."""
from __future__ import annotations

import pytest

import translate


def test_has_cyrillic() -> None:
    assert translate.has_cyrillic("повар") is True
    assert translate.has_cyrillic("Koch") is False
    assert translate.has_cyrillic("Koch повар") is True


class _FakeResponse:
    def __init__(self, data: object) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> object:
        return self._data


class _FakeClient:
    def __init__(self, data: object) -> None:
        self._data = data

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def get(self, url: str, params: dict | None = None) -> _FakeResponse:
        return _FakeResponse(self._data)


def _patch_response(monkeypatch: pytest.MonkeyPatch, data: object) -> None:
    monkeypatch.setattr(
        translate.httpx, "AsyncClient", lambda *a, **k: _FakeClient(data)
    )


@pytest.mark.asyncio
async def test_translate_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_response(
        monkeypatch,
        {"responseStatus": 200, "responseData": {"translatedText": "Koch"}},
    )
    assert await translate.translate_ru_de("повар") == "Koch"


@pytest.mark.asyncio
async def test_translate_non_200_status(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_response(
        monkeypatch,
        {"responseStatus": 403, "responseData": {"translatedText": "x"}},
    )
    assert await translate.translate_ru_de("повар") is None


@pytest.mark.asyncio
async def test_translate_single_word_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    # MyMemory иногда возвращает мусор после слова и в верхнем регистре
    _patch_response(
        monkeypatch,
        {"responseStatus": 200, "responseData": {"translatedText": "JURIST verliehn"}},
    )
    assert await translate.translate_ru_de("юрист") == "Jurist"


@pytest.mark.asyncio
async def test_translate_rejects_too_long_without_network() -> None:
    # длиннее лимита — None ещё до сетевого вызова
    assert await translate.translate_ru_de("я" * 200) is None


@pytest.mark.asyncio
async def test_translate_rejects_warning_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_response(
        monkeypatch,
        {
            "responseStatus": 200,
            "responseData": {"translatedText": "MYMEMORY WARNING: limit"},
        },
    )
    assert await translate.translate_ru_de("повар") is None
