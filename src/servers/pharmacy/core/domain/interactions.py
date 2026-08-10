"""Drug-drug and allergy interaction checking for a set of candidate products."""

from __future__ import annotations

from typing import Any

from src.servers.pharmacy.core.domain.catalog import get_medication
from src.servers.pharmacy.core.domain.data_loader import load


def _rules() -> dict[frozenset, dict[str, str]]:
    rules: dict[frozenset, dict[str, str]] = {}
    for rule in load("interactions.json")["rules"]:
        key = frozenset(ingredient.lower() for ingredient in rule["pair"])
        rules[key] = rule
    return rules


def check_interactions(
    candidate_skus: list[str],
    current_medications: list[str] | None = None,
    allergies: list[str] | None = None,
) -> dict[str, Any]:
    current_medications = [m.lower() for m in (current_medications or [])]
    allergies = [a.lower() for a in (allergies or [])]
    rules = _rules()

    blocking: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    allergy_conflicts: list[dict[str, str]] = []

    for sku in candidate_skus:
        medication = get_medication(sku)
        ingredient = medication["active_ingredient"].lower()

        for tag in medication["allergy_tags"]:
            if tag.lower() in allergies:
                allergy_conflicts.append(
                    {
                        "sku": sku,
                        "name": medication["name"],
                        "allergy": tag,
                    }
                )

        for other in current_medications:
            rule = rules.get(frozenset({ingredient, other}))
            if rule is None:
                continue
            entry = {
                "sku": sku,
                "name": medication["name"],
                "with": other,
                "description": rule["description"],
            }
            (blocking if rule["severity"] == "blocking" else warnings).append(entry)

    return {
        "safe_to_recommend": not blocking and not allergy_conflicts,
        "blocking": blocking,
        "warnings": warnings,
        "allergy_conflicts": allergy_conflicts,
    }
