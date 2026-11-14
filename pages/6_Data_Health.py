import streamlit as st

from src.data_health import get_report, recent_heals, run_spec_link_sweep, summarize

st.set_page_config(page_title="Data Health", page_icon="🩺", layout="wide")
st.title("🩺 Data Health")
st.caption(
    "Read-only checks on production data (cartoTaco migration 034). Specialty links "
    "heal automatically on write and nightly; everything listed here needs a human. "
    "Fix a spec name or create the missing spec on **Spec Tables** and the link fills itself."
)

try:
    rows = get_report()
except Exception as e:
    st.error(f"Could not run data_health_report(): {e}")
    st.info("Run cartoTaco `migrations/034_spec_link_healing.sql` on this database first.")
    st.stop()

counts = summarize(rows)
c1, c2, c3 = st.columns(3)
c1.metric("🔴 Errors", counts["error"], help="Visibly wrong on the site")
c2.metric("🟡 Warnings", counts["warn"], help="Probably wrong")
c3.metric("⚪ Info", counts["info"], help="Housekeeping")

severities = st.multiselect("Severity", ["error", "warn", "info"], default=["error", "warn"])
checks = sorted({r["check_name"] for r in rows})
picked = st.multiselect("Checks", checks, default=checks)
shown = [r for r in rows if r["severity"] in severities and r["check_name"] in picked]

if shown:
    st.dataframe(shown, use_container_width=True, hide_index=True)
else:
    st.success("Nothing to show for these filters.")

st.divider()
st.subheader("Self-healing")
if st.button("Run spec-link sweep now"):
    filled = run_spec_link_sweep()
    st.success(f"Filled {filled} specialty link(s).")
    st.rerun()

heals = recent_heals()
if heals:
    st.markdown("**Recent automatic fixes** (`heal_log`)")
    st.dataframe(heals, use_container_width=True, hide_index=True)
else:
    st.caption("No automatic fixes logged yet.")

st.divider()
st.subheader("Description similarity")
st.caption(
    "Scores behind **Similar spots** on the card and the description half of taste-profile "
    "recommendations (cartoTaco migration 042). Re-run after editing descriptions; "
    "`similarity_stale` above lists spots that changed. Same as `python3 -m src.similarity`."
)
sim_provider = st.radio("Embedding provider", ["fastembed", "voyage"], horizontal=True,
                        help="fastembed runs locally; voyage needs VOYAGE_API_KEY")
c1, c2 = st.columns(2)
preview = c1.button("Preview neighbours (writes nothing)")
recompute = c2.button("Recompute and write", type="primary")
if preview or recompute:
    from src.similarity import neighbours, run

    try:
        with st.spinner("Embedding descriptions…"):
            result = run(provider=sim_provider, dry_run=preview)
    except Exception as e:
        st.error(f"Similarity run failed: {e}")
    else:
        if recompute:
            st.success(f"Wrote {len(result.pairs)} pairs ({result.model}).")
        near = neighbours(result.spots, result.pairs, 3)
        st.dataframe(
            [
                {"spot": s.name + (" (closed)" if s.closed else " (pending)" if s.pending else ""),
                 **{f"#{i + 1}": f"{o.name} · {score:.3f}" for i, (o, score) in enumerate(near[s.est_id])}}
                for s in sorted(result.spots, key=lambda s: s.name.lower())
            ],
            use_container_width=True, hide_index=True,
        )
