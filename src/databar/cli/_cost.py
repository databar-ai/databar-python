"""What a run cost, and what it would cost (DEV-5305).

After a run: the task the API answered with carries ``credits_spent``. It goes beside
``data`` in the JSON envelope and as one status line otherwise.

Before a run (``--dry-run``): the catalog prices at the caller's workspace rates, times the
rows. Nothing is run and nothing is charged. A waterfall is a range: the cheapest provider
answering first, up to every provider running (plus the verifier per step), the same range
the API quotes to MCP clients. A flow asks the API's own ``/flows/cost-estimate``.
"""

from __future__ import annotations

from typing import Any, Optional

from ._output import OutputFormat, info, output


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _credits(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".") or "0"


def spent_extra(client) -> Optional[dict]:
    """``{"credits_spent": x}`` for the task the client last saw finish, or None."""
    task = getattr(client, "last_task", None)
    spent = getattr(task, "credits_spent", None)
    if not isinstance(spent, (int, float)):
        return None
    return {"credits_spent": spent}


def report_spent(extra: Optional[dict]) -> None:
    """The charge as a status line (no-op in JSON mode, where it rides in the envelope)."""
    if extra is not None:
        info(f"Credits spent: {_credits(extra['credits_spent'])}")


def _balance(client) -> Optional[float]:
    try:
        return float(client.get_user().balance)
    except Exception:
        return None


def show_estimate(
    client,
    fmt: OutputFormat,
    *,
    what: str,
    records: int,
    minimum: float,
    maximum: float,
    unit_price: Optional[float] = None,
    note: Optional[str] = None,
) -> None:
    balance = _balance(client)
    estimate: dict[str, Any] = {
        "dry_run": True,
        "what": what,
        "records": records,
        "estimated_credits": {"min": round(minimum, 6), "max": round(maximum, 6)},
        "balance": balance,
    }
    if unit_price is not None:
        estimate["unit_price_credits"] = unit_price
    if note:
        estimate["note"] = note

    if fmt == OutputFormat.JSON:
        output(estimate, fmt)
        return

    cost = _credits(maximum) if minimum == maximum else f"{_credits(minimum)}–{_credits(maximum)}"
    rows = "row" if records == 1 else "rows"
    line = f"Estimated cost of {what}: {cost} credits for {records} {rows}."
    if balance is not None:
        line += f" Balance: {_credits(balance)} credits."
    output(
        [{"what": what, "records": records, "min_credits": minimum, "max_credits": maximum, "balance": balance}],
        fmt,
    )
    info(line + " Nothing was run.")
    if note:
        info(note)


def estimate_enrichment(client, fmt: OutputFormat, enrichment_id: int, records: int) -> None:
    enrichment = client.get_enrichment(enrichment_id)
    price = _num(enrichment.price)
    show_estimate(
        client,
        fmt,
        what=f"enrichment #{enrichment_id}",
        records=records,
        minimum=price * records,
        maximum=price * records,
        unit_price=price,
        note="Rows that return no data may not be charged; this is the ceiling.",
    )


def estimate_waterfall(
    client,
    fmt: OutputFormat,
    identifier: str,
    records: int,
    providers: Optional[list[int]],
    email_verifier: Optional[int],
) -> None:
    waterfall = client.get_waterfall(identifier)
    by_id = {e.id: e for e in waterfall.available_enrichments}
    if providers:
        chosen = [by_id[pid] for pid in providers if pid in by_id]
    else:
        chosen = [e for e in waterfall.available_enrichments if e.enabled_by_default]
    prices = [_num(e.price) for e in chosen]
    verifier = 0.0
    if email_verifier is not None:
        for v in waterfall.email_verifiers or []:
            if isinstance(v, dict) and v.get("id") == email_verifier:
                verifier = _num(v.get("price"))
    if prices:
        per_min = min(prices) + verifier
        per_max = sum(prices) + verifier * len(prices)
    else:
        per_min = per_max = 0.0
    show_estimate(
        client,
        fmt,
        what=f"waterfall {identifier} ({len(chosen)} providers)",
        records=records,
        minimum=per_min * records,
        maximum=per_max * records,
        note="Min: the cheapest provider answers first. Max: every provider runs.",
    )


def estimate_flow(client, fmt: OutputFormat, flow_id: str, records: int) -> None:
    flow = client.get_flow(flow_id)
    one = client.estimate_flow_cost(flow.config)
    show_estimate(
        client,
        fmt,
        what=f"flow {flow_id}",
        records=records,
        minimum=_num(one.min) * records,
        maximum=_num(one.max) * records,
        note="Max assumes every branch and waterfall provider runs.",
    )
