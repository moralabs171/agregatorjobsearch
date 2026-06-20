"""Тесты клиента API: нормализация занятости и парсинг объявлений."""
from __future__ import annotations

from arbeitsagentur import JobListing, OfferType, normalize_arbeitszeit


def test_normalize_arbeitszeit_aliases() -> None:
    codes, invalid = normalize_arbeitszeit(["vollzeit", "remote"])
    assert codes == "vz;ho"
    assert invalid == []


def test_normalize_arbeitszeit_dedupes_and_keeps_order() -> None:
    codes, invalid = normalize_arbeitszeit(["vz", "vollzeit", "tz"])
    assert codes == "vz;tz"
    assert invalid == []


def test_normalize_arbeitszeit_reports_invalid() -> None:
    codes, invalid = normalize_arbeitszeit(["vz", "wat"])
    assert codes == "vz"
    assert invalid == ["wat"]


def test_normalize_arbeitszeit_empty() -> None:
    codes, invalid = normalize_arbeitszeit([])
    assert codes is None
    assert invalid == []


def test_joblisting_from_api_full_item() -> None:
    item = {
        "refnr": "12345",
        "titel": "Fachinformatiker",
        "arbeitgeber": "ACME GmbH",
        "arbeitsort": {"ort": "Chemnitz"},
        "aktuelleVeroeffentlichungsdatum": "2026-06-01",
    }
    listing = JobListing.from_api(item)

    assert listing is not None
    assert listing.refnr == "12345"
    assert listing.title == "Fachinformatiker"
    assert listing.employer == "ACME GmbH"
    assert listing.city == "Chemnitz"
    assert listing.published == "2026-06-01"
    assert listing.refnr in listing.url  # дефолтный URL содержит refnr


def test_joblisting_from_api_without_refnr_is_none() -> None:
    assert JobListing.from_api({"titel": "x"}) is None


def test_joblisting_from_api_prefers_external_url() -> None:
    listing = JobListing.from_api({"refnr": "1", "externeUrl": "https://ext.example/x"})
    assert listing is not None
    assert listing.url == "https://ext.example/x"


def test_joblisting_from_api_defaults() -> None:
    listing = JobListing.from_api({"refnr": "1"})
    assert listing is not None
    assert listing.city == "—"
    assert listing.employer == "—"


def test_offer_type_values() -> None:
    assert int(OfferType.JOB) == 1
    assert int(OfferType.AUSBILDUNG) == 4
