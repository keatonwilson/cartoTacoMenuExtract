import streamlit as st
from src.staging import list_extractions
from src.promotion import promote

st.set_page_config(page_title="Promote to Production", page_icon="🚀", layout="wide")
st.title("🚀 Promote to Production")

rows = list_extractions("approved")

if not rows:
    st.info("No approved extractions to promote.")
    st.stop()

# --- Select Row ---
options = {r["id"]: f"{r['restaurant_name']} — {r['created_at'][:10]}" for r in rows}
selected_id = st.selectbox("Select approved extraction", options.keys(), format_func=lambda x: options[x])

row = next(r for r in rows if r["id"] == selected_id)

# Show summary
st.markdown(f"**Restaurant:** {row['restaurant_name']}")

site_data = row.get("site_data", {})
if site_data.get("address"):
    st.markdown(f"**Address:** {site_data['address']}")

menu_items = [k.replace("_yes", "") for k, v in row.get("menu_data", {}).items() if k.endswith("_yes") and v]
if menu_items:
    st.markdown(f"**Menu items:** {', '.join(menu_items)}")

# --- Promote ---
st.divider()
if st.button("🚀 Promote to Production", type="primary"):
    with st.spinner("Creating new site and promoting to production tables..."):
        try:
            result_id = promote(selected_id)
            st.success(f"Promoted! est_id: `{result_id}`")

            specialty_items = row.get("menu_data", {}).get("specialty_items", [])
            if specialty_items:
                st.info(
                    f"Specialty items noted: {', '.join(specialty_items)}. "
                    "These need manual FK linking in the `menu` table."
                )
            st.rerun()
        except Exception as e:
            st.error(f"Promotion failed: {e}")
