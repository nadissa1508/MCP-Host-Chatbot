"""Symptom triage: turns a free-text symptom list into a condition guess,
severity, safety-critical red flags and suggested therapeutic classes.

Red flags are enforced here, in the server, rather than left to the LLM's
judgement -- the assignment's safety rule ("this must actually medicate the
user, safely") depends on the tool refusing to soften a dangerous case.
"""

from __future__ import annotations

from typing import Any

from src.servers.pharmacy.core.domain.data_loader import load

MIN_INFANT_AGE = 2
PROLONGED_SYMPTOM_DAYS = 10


def _conditions() -> list[dict[str, Any]]:
    return load("symptoms.json")["conditions"]


def _red_flag_rules() -> list[dict[str, str]]:
    return load("symptoms.json")["red_flags"]


def _find_red_flags(symptoms: list[str], age: int, duration_days: int) -> list[str]:
    text = " ".join(s.lower() for s in symptoms)
    flags = [rule["message"] for rule in _red_flag_rules() if rule["keyword"] in text]

    if age < MIN_INFANT_AGE:
        flags.append("Symptoms in infants under 2 years old require in-person medical evaluation.")
    if duration_days > PROLONGED_SYMPTOM_DAYS:
        flags.append(
            f"Symptoms lasting more than {PROLONGED_SYMPTOM_DAYS} days should be evaluated by a doctor."
        )
    return flags


def _best_condition_matches(symptoms: list[str]) -> list[dict[str, Any]]:
    normalized = {s.lower() for s in symptoms}
    scored = []
    for condition in _conditions():
        overlap = normalized & {s.lower() for s in condition["match_symptoms"]}
        if overlap:
            scored.append((len(overlap), condition))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [condition for _, condition in scored[:2]]


def assess_symptoms(
    symptoms: list[str],
    duration_days: int = 1,
    age: int = 30,
    pregnant: bool = False,
    chronic_conditions: list[str] | None = None,
) -> dict[str, Any]:
    chronic_conditions = chronic_conditions or []
    red_flags = _find_red_flags(symptoms, age, duration_days)
    matches = _best_condition_matches(symptoms)

    therapeutic_classes: list[str] = []
    for condition in matches:
        for tc in condition["therapeutic_classes"]:
            if tc not in therapeutic_classes:
                therapeutic_classes.append(tc)

    if red_flags:
        severity = "urgent"
    elif duration_days > 5:
        severity = "moderate"
    else:
        severity = "mild"

    advice_parts = [c["advice"] for c in matches]
    likely_conditions = [c["id"] for c in matches] or ["unspecified"]

    return {
        "likely_conditions": likely_conditions,
        "severity": severity,
        "red_flags": red_flags,
        "therapeutic_classes": therapeutic_classes,
        "advice": " ".join(advice_parts) or "Not enough matching symptoms to suggest a specific condition.",
        "pregnant": pregnant,
        "chronic_conditions": chronic_conditions,
        "disclaimer": (
            "This is not a medical diagnosis. It is a general OTC symptom-relief suggestion. "
            "Consult a physician for a proper diagnosis, especially if symptoms persist or worsen."
        ),
    }
