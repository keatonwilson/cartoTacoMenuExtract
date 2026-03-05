import streamlit as st

st.set_page_config(page_title="CartoTaco Menu Extract", page_icon="🌮", layout="wide")

st.title("🌮 CartoTaco Menu Extract")
st.markdown(
    "Upload menu photos, extract structured data with Claude Vision, "
    "review it, and promote to the CartoTaco production database."
)

# Dashboard: staging row counts by status
try:
    from src.supabase_client import get_client

    client = get_client()
    rows = client.table("staging_extractions").select("id, status").execute().data

    counts = {"pending_review": 0, "approved": 0, "promoted": 0, "rejected": 0}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Pending Review", counts["pending_review"])
    col2.metric("Approved", counts["approved"])
    col3.metric("Promoted", counts["promoted"])
    col4.metric("Rejected", counts["rejected"])

except Exception as e:
    st.warning(f"Could not load staging data: {e}")
    st.info("Make sure your `.env` is configured and the staging table exists.")
