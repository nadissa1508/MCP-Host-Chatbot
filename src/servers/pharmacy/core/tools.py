"""Tool catalog for the pharmacy MCP server: JSON schemas plus the handler
that maps `tools/call` arguments onto the domain layer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from src.mcp.models import ToolResult
from src.servers.pharmacy.core.domain import catalog, interactions, inventory, orders, triage
from src.servers.pharmacy.core.domain.errors import PharmacyError


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]

    def to_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }

    def call(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            result = self.handler(arguments)
        except PharmacyError as exc:
            return ToolResult.text_result(str(exc), is_error=True)
        except (KeyError, TypeError, ValueError) as exc:
            return ToolResult.text_result(f"Invalid arguments: {exc}", is_error=True)
        return ToolResult.text_result(json.dumps(result, indent=2))


def _assess_symptoms(args: dict[str, Any]) -> Any:
    return triage.assess_symptoms(
        symptoms=args["symptoms"],
        duration_days=args.get("duration_days", 1),
        age=args.get("age", 30),
        pregnant=args.get("pregnant", False),
        chronic_conditions=args.get("chronic_conditions", []),
    )


def _search_medications(args: dict[str, Any]) -> Any:
    return catalog.search_medications(
        query=args.get("query"),
        therapeutic_class=args.get("therapeutic_class"),
        otc_only=args.get("otc_only", True),
    )


def _get_medication_details(args: dict[str, Any]) -> Any:
    return catalog.get_medication_details(args["sku"])


def _check_interactions(args: dict[str, Any]) -> Any:
    return interactions.check_interactions(
        candidate_skus=args["candidate_skus"],
        current_medications=args.get("current_medications", []),
        allergies=args.get("allergies", []),
    )


def _check_stock(args: dict[str, Any]) -> Any:
    return inventory.check_stock(sku=args["sku"], branch_id=args.get("branch_id"))


def _create_order(args: dict[str, Any]) -> Any:
    return orders.create_order(
        items=args["items"],
        branch_id=args["branch_id"],
        fulfillment=args.get("fulfillment", "pickup"),
        prescription_id=args.get("prescription_id"),
    )


def _get_order_status(args: dict[str, Any]) -> Any:
    return orders.get_order_status(args["order_id"])


TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="assess_symptoms",
        description=(
            "Assess a list of self-reported symptoms and return a likely condition, "
            "severity, safety red flags and suggested OTC therapeutic classes. "
            "Always call this before recommending a medication."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "symptoms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Symptoms in plain language, e.g. [\"runny nose\", \"sore throat\"]",
                },
                "duration_days": {"type": "integer", "description": "How many days the symptoms have lasted"},
                "age": {"type": "integer", "description": "Patient age in years"},
                "pregnant": {"type": "boolean", "description": "Whether the patient is pregnant"},
                "chronic_conditions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Known chronic conditions, e.g. [\"hypertension\"]",
                },
            },
            "required": ["symptoms"],
        },
        handler=_assess_symptoms,
    ),
    ToolSpec(
        name="search_medications",
        description="Search the OTC catalog by free-text query and/or therapeutic class.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text search, e.g. brand or ingredient"},
                "therapeutic_class": {
                    "type": "string",
                    "description": "Filter by class, e.g. \"analgesic\", \"antihistamine\", \"decongestant\"",
                },
                "otc_only": {"type": "boolean", "description": "If true (default), exclude prescription-only items"},
            },
            "required": [],
        },
        handler=_search_medications,
    ),
    ToolSpec(
        name="get_medication_details",
        description="Get the full monograph for one medication by SKU: dosage, contraindications, side effects, price.",
        input_schema={
            "type": "object",
            "properties": {"sku": {"type": "string", "description": "Medication SKU, e.g. \"PARA500\""}},
            "required": ["sku"],
        },
        handler=_get_medication_details,
    ),
    ToolSpec(
        name="check_interactions",
        description=(
            "Check candidate medications against the current medications and "
            "allergies on file for drug-drug interactions and allergy conflicts."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "candidate_skus": {"type": "array", "items": {"type": "string"}},
                "current_medications": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Active ingredients already being taken, e.g. [\"warfarin\"]",
                },
                "allergies": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["candidate_skus"],
        },
        handler=_check_interactions,
    ),
    ToolSpec(
        name="check_stock",
        description="Check price and availability of one SKU, at one branch or across all branches.",
        input_schema={
            "type": "object",
            "properties": {
                "sku": {"type": "string"},
                "branch_id": {"type": "string", "description": "Optional; omit to check all branches"},
            },
            "required": ["sku"],
        },
        handler=_check_stock,
    ),
    ToolSpec(
        name="create_order",
        description=(
            "Place an order for one or more SKUs at a branch. Prescription-only "
            "medications require a prescription_id or the order is refused."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sku": {"type": "string"},
                            "quantity": {"type": "integer"},
                        },
                        "required": ["sku", "quantity"],
                    },
                },
                "branch_id": {"type": "string"},
                "fulfillment": {"type": "string", "enum": ["pickup", "delivery"]},
                "prescription_id": {"type": "string"},
            },
            "required": ["items", "branch_id"],
        },
        handler=_create_order,
    ),
    ToolSpec(
        name="get_order_status",
        description="Look up an order by its order_id.",
        input_schema={
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
        handler=_get_order_status,
    ),
]
