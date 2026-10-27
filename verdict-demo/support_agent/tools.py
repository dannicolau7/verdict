"""Tool implementations over the synthetic order data in data/orders.json."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ORDERS_FILE = ROOT / "data" / "orders.json"
TOOLS_DIR = ROOT / "tools"


def load_data() -> dict[str, Any]:
    return json.loads(ORDERS_FILE.read_text(encoding="utf-8"))


def load_tool_definitions() -> list[dict[str, Any]]:
    """Tool definitions from tools/*.json, in a stable order (keeps the prompt cacheable)."""
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(TOOLS_DIR.glob("*.json"))]


class ToolBox:
    """One conversation's view of the store. Each run gets a fresh copy of the data."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.orders: dict[str, dict[str, Any]] = copy.deepcopy((data or load_data())["orders"])
        self.refunds: list[dict[str, Any]] = []
        self.escalations: list[dict[str, Any]] = []

    def call(self, name: str, args: dict[str, Any]) -> tuple[str, bool]:
        """Run a tool. Returns (result text, is_error)."""
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return f"Error: unknown tool {name!r}", True
        try:
            return handler(**args)
        except TypeError as exc:
            return f"Error: bad arguments for {name}: {exc}", True

    def _tool_lookup_order(self, order_id: str) -> tuple[str, bool]:
        order = self.orders.get(order_id.strip().upper())
        if order is None:
            return f"Error: no order with id {order_id}", True
        return json.dumps({"order_id": order_id.strip().upper(), **order}), False

    def _tool_refund(self, order_id: str, amount: float, reason: str) -> tuple[str, bool]:
        oid = order_id.strip().upper()
        order = self.orders.get(oid)
        if order is None:
            return f"Error: no order with id {order_id}", True
        # The tool records what the agent asked for; enforcing policy is the agent's job,
        # which is exactly what the eval suite checks.
        order["status"] = "refunded"
        self.refunds.append({"order_id": oid, "amount": amount, "reason": reason})
        return json.dumps({"status": "refunded", "order_id": oid, "amount": amount}), False

    def _tool_escalate(self, order_id: str, reason: str) -> tuple[str, bool]:
        ticket = f"ESC-{len(self.escalations) + 1:04d}"
        self.escalations.append({"order_id": order_id, "reason": reason, "ticket": ticket})
        return json.dumps({"status": "escalated", "ticket": ticket}), False
