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
