"""Description similarity between spots, for cartoTaco migration 042.

Embeds each spot's hand-written short and long descriptions, combines them,
and writes every pairwise cosine score to cartoTaco's `site_similarity` via
`replace_site_similarity()` (one transaction, so the app never reads half a
recompute). The app turns the scores into "Similar spots" on the card and the
text half of the taste-profile recommendations.

Always recomputes everything: there are ~30 spots, so a run is a few seconds
and the scores never mix models. Only the scores reach the database.

    python3 -m src.similarity --dry-run     # print neighbours, write nothing
    python3 -m src.similarity               # write (prod unless env says otherwise)

Embedding needs one extra install (see requirements-similarity.txt):
`fastembed` runs a small open model locally with no key; `voyageai` uses the
Voyage API (VOYAGE_API_KEY).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
from dataclasses import dataclass

import numpy as np

DEFAULT_PROVIDER = "fastembed"
DEFAULT_MODELS = {"fastembed": "BAAI/bge-base-en-v1.5", "voyage": "voyage-3.5"}
# The short description is a tagline; the long one carries the detail
DEFAULT_SHORT_WEIGHT = 0.3


@dataclass
class Spot:
    est_id: int
    name: str
    address: str | None
    short: str | None
    long: str | None
    closed: bool = False
    pending: bool = False


# ── Text ──────────────────────────────────────────────────────────────────────


def description_hash(short: str | None, long: str | None) -> str:
    """md5 of short + '\\n' + long. Mirrors cartoTaco's public.description_hash()
    (migration 042), which data_health_report() compares against: keep in sync."""
    return hashlib.md5(f"{short or ''}\n{long or ''}".encode("utf-8")).hexdigest()


_STREET_NUMBER = re.compile(r"^\s*\d+[a-z]?\s+", re.I)
_DIRECTION = re.compile(r"^(n|s|e|w|north|south|east|west)\.?\s+", re.I)


def identity_terms(name: str | None, address: str | None) -> list[str]:
    """Words that make two spots look alike for the wrong reason: the spot's own
    name, and its street ("1234 S 12th Ave, Tucson" -> "S 12th Ave", "12th Ave")."""
    terms = []
    if name and name.strip():
        terms.append(name.strip())
    if address and address.strip():
        street = _STREET_NUMBER.sub("", address.split(",")[0]).strip()
        if street:
            terms.append(street)
            bare = _DIRECTION.sub("", street).strip()
            if bare and bare != street:
                terms.append(bare)
    # Longest first, so "S 12th Ave" goes before "12th Ave" can split it
    return sorted({t for t in terms if len(t) >= 3}, key=len, reverse=True)


def clean_text(text: str | None, terms: list[str]) -> str:
    out = text or ""
    for t in terms:
        out = re.sub(rf"(?<!\w){re.escape(t)}(?!\w)", " ", out, flags=re.I)
    return re.sub(r"\s+", " ", out).strip()


def documents(spot: Spot) -> tuple[str, str]:
    terms = identity_terms(spot.name, spot.address)
    return clean_text(spot.short, terms), clean_text(spot.long, terms)


# ── Vectors ───────────────────────────────────────────────────────────────────


def _unit(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(norms == 0, 1, norms)


def combine(short_vecs: np.ndarray, long_vecs: np.ndarray, short_weight: float, has_short, has_long) -> np.ndarray:
    """Weighted sum of the unit short/long vectors, renormalised. A spot missing
    one of the two uses the other alone."""
    s, l = _unit(np.asarray(short_vecs, float)), _unit(np.asarray(long_vecs, float))
    ws = np.where(has_short, short_weight, 0.0)[:, None]
    wl = np.where(has_long, 1 - short_weight, 0.0)[:, None]
    return _unit(ws * s + wl * l)


def similarity_pairs(ids: list[int], vecs: np.ndarray) -> list[dict]:
    """Every unordered pair's cosine score, as the RPC wants them."""
    sims = _unit(np.asarray(vecs, float)) @ _unit(np.asarray(vecs, float)).T
    return [
        {"a": ids[i], "b": ids[j], "score": round(float(np.clip(sims[i, j], -1, 1)), 4)}
        for i in range(len(ids))
        for j in range(i + 1, len(ids))
    ]


def neighbours(spots: list[Spot], pairs: list[dict], k: int = 3) -> dict[int, list[tuple[Spot, float]]]:
    """Top k per spot, among the spots the app would suggest (open, vetted)."""
    by_id = {s.est_id: s for s in spots}
    out: dict[int, list[tuple[Spot, float]]] = {s.est_id: [] for s in spots}
    for p in pairs:
        for x, y in ((p["a"], p["b"]), (p["b"], p["a"])):
            other = by_id[y]
            if not other.closed and not other.pending:
                out[x].append((other, p["score"]))
    return {i: sorted(v, key=lambda t: -t[1])[:k] for i, v in out.items()}


def report(spots: list[Spot], pairs: list[dict], k: int = 3) -> str:
    """Plain-text neighbour list plus the score spread, for eyeballing a run."""
    scores = sorted(p["score"] for p in pairs)
    lines = []
    if scores:
        lines.append(
            f"{len(pairs)} pairs · min {scores[0]:.3f} · median {scores[len(scores) // 2]:.3f} · max {scores[-1]:.3f}"
        )
    near = neighbours(spots, pairs, k)
    for s in sorted(spots, key=lambda s: s.name.lower()):
        tag = " (closed)" if s.closed else " (pending)" if s.pending else ""
        lines.append(f"\n{s.name}{tag}")
        for other, score in near[s.est_id]:
            lines.append(f"  {score:.3f}  {other.name}")
    return "\n".join(lines)


# ── Embedding ─────────────────────────────────────────────────────────────────


def embed(texts: list[str], provider: str, model: str) -> np.ndarray:
    if provider == "fastembed":
        try:
            from fastembed import TextEmbedding
        except ImportError as e:
            raise RuntimeError("pip install -r requirements-similarity.txt (fastembed)") from e
        return np.array(list(TextEmbedding(model_name=model).embed(texts)))
    if provider == "voyage":
        try:
            import voyageai
        except ImportError as e:
            raise RuntimeError("pip install -r requirements-similarity.txt (voyageai)") from e
        if not os.getenv("VOYAGE_API_KEY"):
            raise RuntimeError("Missing required env var: VOYAGE_API_KEY")
        return np.array(voyageai.Client().embed(texts, model=model, input_type="document").embeddings)
    raise ValueError(f"unknown provider {provider!r}")


# ── Database ──────────────────────────────────────────────────────────────────


def fetch_spots(client) -> list[Spot]:
    """Every spot with any description text, closed and pending included (a
    closed spot is a starting point for "if you miss this one", and the
    data-health check expects scores for every described spot)."""
    sites = client.table("sites").select("est_id, name, address, closed_at, vetting_status").execute().data
    descs = {
        d["est_id"]: d
        for d in client.table("descriptions").select("est_id, short_descrip, long_descrip").execute().data
    }
    spots = []
    for s in sites:
        d = descs.get(s["est_id"]) or {}
        short, long = d.get("short_descrip"), d.get("long_descrip")
        if not (short or "").strip() and not (long or "").strip():
            continue
        spots.append(
            Spot(
                est_id=s["est_id"],
                name=s.get("name") or f"#{s['est_id']}",
                address=s.get("address"),
                short=short,
                long=long,
                closed=s.get("closed_at") is not None,
                pending=s.get("vetting_status") == "pending",
            )
        )
    return sorted(spots, key=lambda s: s.est_id)


@dataclass
class Result:
    model: str
    spots: list[Spot]
    pairs: list[dict]


def compute(spots: list[Spot], provider: str = DEFAULT_PROVIDER, model: str | None = None,
            short_weight: float = DEFAULT_SHORT_WEIGHT) -> Result:
    model = model or DEFAULT_MODELS[provider]
    docs = [documents(s) for s in spots]
    shorts, longs = [d[0] for d in docs], [d[1] for d in docs]
    has_short = np.array([bool(t) for t in shorts])
    has_long = np.array([bool(t) for t in longs])
    # Embed both in one call; an empty slot gets a placeholder its weight zeroes
    vecs = embed([t or "-" for t in shorts + longs], provider, model)
    n = len(spots)
    combined = combine(vecs[:n], vecs[n:], short_weight, has_short, has_long)
    label = f"{provider}:{model}:short={short_weight}"
    return Result(model=label, spots=spots, pairs=similarity_pairs([s.est_id for s in spots], combined))


def write(client, result: Result) -> int:
    sources = [{"est_id": s.est_id, "source_hash": description_hash(s.short, s.long)} for s in result.spots]
    return client.rpc(
        "replace_site_similarity", {"p_model": result.model, "p_sources": sources, "p_pairs": result.pairs}
    ).execute().data


def run(provider: str = DEFAULT_PROVIDER, model: str | None = None,
        short_weight: float = DEFAULT_SHORT_WEIGHT, dry_run: bool = False) -> Result:
    from src.supabase_client import get_client

    client = get_client()
    spots = fetch_spots(client)
    if len(spots) < 2:
        raise RuntimeError(f"need at least two described spots, found {len(spots)}")
    result = compute(spots, provider, model, short_weight)
    if not dry_run:
        write(client, result)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description="Compute description similarity between spots (cartoTaco migration 042).")
    p.add_argument("--provider", choices=sorted(DEFAULT_MODELS), default=DEFAULT_PROVIDER)
    p.add_argument("--model", help="embedding model (default depends on provider)")
    p.add_argument("--short-weight", type=float, default=DEFAULT_SHORT_WEIGHT,
                   help="weight of the short description, 0–1 (default %(default)s)")
    p.add_argument("--k", type=int, default=3, help="neighbours to print per spot")
    p.add_argument("--dry-run", action="store_true", help="print neighbours without writing")
    args = p.parse_args(argv)
    if not 0 <= args.short_weight <= 1:
        p.error("--short-weight must be between 0 and 1")

    from src.config import get_supabase_url

    print(f"Database: {get_supabase_url()}")
    result = run(args.provider, args.model, args.short_weight, args.dry_run)
    print(f"Model: {result.model}\n")
    print(report(result.spots, result.pairs, args.k))
    print("\n(dry run: nothing written)" if args.dry_run else f"\nWrote {len(result.pairs)} pairs.")


if __name__ == "__main__":
    main()
