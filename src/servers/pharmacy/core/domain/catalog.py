"""Product catalog: searching medications and reading their full monograph."""

from __future__ import annotations

from typing import Any

from src.servers.pharmacy.core.domain.data_loader import load
from src.servers.pharmacy.core.domain.errors import PharmacyError


def _medications() -> list[dict[str, Any]]:
    return load("medications.json")["medications"]


def _by_sku() -> dict[str, dict[str, Any]]:
    return {m["sku"]: m for m in _medications()}


def get_medication(sku: str) -> dict[str, Any]:
    medication = _by_sku().get(sku.upper())
    if medication is None:
        raise PharmacyError(f"Unknown medication SKU: {sku}")
    return medication


def summarize(medication: dict[str, Any]) -> dict[str, Any]:
    return {
        "sku": medication["sku"],
        "name": medication["name"],
        "active_ingredient": medication["active_ingredient"],
        "therapeutic_class": medication["therapeutic_class"],
        "otc": medication["otc"],
        "price": medication["price"],
    }


def search_medications(
    query: str | None = None,
    therapeutic_class: str | None = None,
    otc_only: bool = True,
) -> list[dict[str, Any]]:
    results = []
    for medication in _medications():
        if otc_only and not medication["otc"]:
            continue
        if therapeutic_class and medication["therapeutic_class"] != therapeutic_class.lower():
            continue
        if query:
            haystack = " ".join(
                [medication["name"], medication["active_ingredient"], medication["therapeutic_class"]]
            ).lower()
            if query.lower() not in haystack:
                continue
        results.append(summarize(medication))
    return results


def get_medication_details(sku: str) -> dict[str, Any]:
    return get_medication(sku)
