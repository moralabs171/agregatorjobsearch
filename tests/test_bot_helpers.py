"""Тесты чистых хелперов бота: парсинг запроса, резолв синонимов, метки."""
from __future__ import annotations

import arbeitsagentur as aa
import bot


def test_parse_query_and_times_query_only() -> None:
    query, times, invalid = bot._parse_query_and_times("Koch")
    assert query == "Koch"
    assert times is None
    assert invalid == []


def test_parse_query_and_times_with_filter() -> None:
    query, times, invalid = bot._parse_query_and_times("Koch | vz tz")
    assert query == "Koch"
    assert times == "vz;tz"
    assert invalid == []


def test_parse_query_and_times_invalid_filter() -> None:
    query, times, invalid = bot._parse_query_and_times("Koch | wat")
    assert query == "Koch"
    assert times is None
    assert invalid == ["wat"]


def test_parse_query_and_times_empty_query() -> None:
    query, times, invalid = bot._parse_query_and_times("  ")
    assert query is None
    assert times is None


def test_resolve_query_known_russian_synonym() -> None:
    german, note = bot._resolve_query("повар")
    assert german == "Koch"
    assert note is not None  # должно сообщить, как понял


def test_resolve_query_exact_german_no_note() -> None:
    german, note = bot._resolve_query("Koch")
    assert german == "Koch"
    assert note is None


def test_resolve_query_unknown_passthrough() -> None:
    german, note = bot._resolve_query("Quantenphysiker")
    assert german == "Quantenphysiker"
    assert note is None


def test_resolve_query_typo_fuzzy_match() -> None:
    # опечатка в известном алиасе должна подтянуть близкое значение
    german, note = bot._resolve_query("электирк")
    assert german == "Elektroniker"
    assert note is not None


def test_times_label() -> None:
    assert bot._times_label("vz;tz") == "Vollzeit, Teilzeit"
    assert bot._times_label(None) == ""


def test_offer_label() -> None:
    assert bot._offer_label(int(aa.OfferType.AUSBILDUNG)) == "Ausbildung"
    assert bot._offer_label(int(aa.OfferType.JOB)) == "вакансии"
