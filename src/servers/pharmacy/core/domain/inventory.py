"""Branch stock lookups."""

from __future__ import annotations

from typing import Any

from src.servers.pharmacy.core.domain.catalog import get_medication
from src.servers.pharmacy.core.domain.data_loader import load
from src.servers.pharmacy.core.domain.errors import PharmacyError


def _branches() -> list[dict[str, Any]]:
    return load("branches.json")["branches"]


def get_branch(branch_id: str) -> dict[str, Any]:
    for branch in _branches():
        if branch["id"] == branch_id:
            return branch
    raise PharmacyError(f"Unknown branch: {branch_id}")


def check_stock(sku: str, branch_id: str | None = None) -> dict[str, Any]:
    medication = get_medication(sku)

    if branch_id:
        branch = get_branch(branch_id)
        quantity = branch["stock"].get(medication["sku"], 0)
        return {
            "sku": medication["sku"],
            "name": medication["name"],
            "price": medication["price"],
            "branches": [
                {"branch_id": branch["id"], "branch_name": branch["name"], "quantity": quantity}
            ],
        }

    availability = [
        {
            "branch_id": branch["id"],
            "branch_name": branch["name"],
            "quantity": branch["stock"].get(medication["sku"], 0),
        }
        for branch in _branches()
    ]
    return {
        "sku": medication["sku"],
        "name": medication["name"],
        "price": medication["price"],
        "branches": availability,
    }
