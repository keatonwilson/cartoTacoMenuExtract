"""Data health checks and self-healing, backed by cartoTaco migration 034.

The checks and the spec-link sweep live in the database
(data_health_report() / heal_spec_links()) so the nightly GitHub Action in
cartoTaco and this admin app run exactly the same logic.
"""

from src.supabase_client import get_client

SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2}


def get_report() -> list[dict]:
    """All open findings, most severe first."""
    rows = get_client().rpc("data_health_report").execute().data or []
    return sorted(rows, key=lambda r: (SEVERITY_ORDER.get(r["severity"], 9), r["check_name"], r.get("est_id") or 0))


def summarize(rows: list[dict]) -> dict[str, int]:
    """Finding counts per severity (all severities present, zero-filled)."""
    counts = {s: 0 for s in SEVERITY_ORDER}
    for r in rows:
        counts[r["severity"]] = counts.get(r["severity"], 0) + 1
    return counts


def run_spec_link_sweep() -> int:
    """Fill every empty spec_id_N whose name resolves; returns links filled."""
    return get_client().rpc("heal_spec_links", {"p_source": "admin_app"}).execute().data or 0


def recent_heals(limit: int = 50) -> list[dict]:
    """Most recent automatic fixes from heal_log."""
    return (
        get_client()
        .table("heal_log")
        .select("ran_at, source, check_name, table_name, est_id, column_name, old_value, new_value, note")
        .order("ran_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )
