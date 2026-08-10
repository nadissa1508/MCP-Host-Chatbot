"""Order lifecycle: validates a cart against stock and prescription rules,
then creates and tracks orders in memory for the lifetime of the server
process.
"""

from __future__ import annotations

import uuid
from typing import Any

from src.servers.pharmacy.core.domain.catalog import get_medication
from src.servers.pharmacy.core.domain.errors import PharmacyError
from src.servers.pharmacy.core.domain.inventory import get_branch

_ORDERS: dict[str, dict[str, Any]] = {}


def create_order(
    items: list[dict[str, Any]],
    branch_id: str,
    fulfillment: str = "pickup",
    prescription_id: str | None = None,
) -> dict[str, Any]:
    if not items:
        raise PharmacyError("An order must contain at least one item.")

    branch = get_branch(branch_id)
    line_items = []
    total = 0.0

    for item in items:
        sku = item["sku"]
        quantity = int(item.get("quantity", 1))
        if quantity <= 0:
            raise PharmacyError(f"Invalid quantity for {sku}: {quantity}")

        medication = get_medication(sku)
        if not medication["otc"] and not prescription_id:
            raise PharmacyError(
                f"{medication['name']} requires a prescription. "
                "Provide a prescription_id to order it."
            )

        available = branch["stock"].get(medication["sku"], 0)
        if available < quantity:
            raise PharmacyError(
                f"Not enough stock of {medication['name']} at {branch['name']} "
                f"(requested {quantity}, available {available})."
            )

        line_total = medication["price"] * quantity
        total += line_total
        line_items.append(
            {
                "sku": medication["sku"],
                "name": medication["name"],
                "quantity": quantity,
                "unit_price": medication["price"],
                "line_total": round(line_total, 2),
            }
        )

    # Stock is only committed after every line item has been validated, so a
    # rejected order never leaves partial deductions behind.
    for line_item in line_items:
        branch["stock"][line_item["sku"]] -= line_item["quantity"]

    order_id = uuid.uuid4().hex[:8].upper()
    order = {
        "order_id": order_id,
        "status": "confirmed",
        "branch_id": branch["id"],
        "branch_name": branch["name"],
        "fulfillment": fulfillment,
        "prescription_id": prescription_id,
        "items": line_items,
        "total": round(total, 2),
    }
    _ORDERS[order_id] = order
    return order


def get_order_status(order_id: str) -> dict[str, Any]:
    order = _ORDERS.get(order_id.upper())
    if order is None:
        raise PharmacyError(f"Unknown order id: {order_id}")
    return order
