import streamlit as st
from src.staging import list_extractions
from src.promotion import (
    promote,
    find_sites_by_name,
    list_pending_sites,
    retract_pending_site,
    mark_vetted,
)

st.set_page_config(page_title="Promote to Production", page_icon="🚀", layout="wide")
st.title("🚀 Promote to Production")

rows = list_extractions("approved")

if not rows:
    st.info("No approved extractions to promote.")
else:
    # --- Select Row ---
    options = {
        r["id"]: f"{'🔭 ' if r.get('pipeline') == 'web_scrape' else ''}"
                 f"{r['restaurant_name']} — {r['created_at'][:10]}"
        for r in rows
    }
    selected_id = st.selectbox("Select approved extraction", options.keys(), format_func=lambda x: options[x])

    row = next(r for r in rows if r["id"] == selected_id)
    is_scouted = row.get("pipeline") == "web_scrape"

    # Show summary
    st.markdown(f"**Restaurant:** {row['restaurant_name']}")
    site_data = row.get("site_data", {})
    if site_data.get("address"):
        st.markdown(f"**Address:** {site_data['address']}")
    if is_scouted:
        st.info(
            "🔭 Scouted spot — will be created as a **pending (unvetted)** site: "
            "sites + descriptions + hours only, flagged as pending on the map "
            "until vetted with a menu-photo promotion."
        )
    else:
        menu_items = [k.replace("_yes", "") for k, v in row.get("menu_data", {}).items() if k.endswith("_yes") and v]
        if menu_items:
            st.markdown(f"**Menu items:** {', '.join(menu_items)}")

    # --- Duplicate check ---
    st.divider()
    matches = find_sites_by_name(row["restaurant_name"])

    if matches:
        st.warning(
            f"Found {len(matches)} existing site(s) with a similar name. "
            "Choose one to update, or create a new entry."
        )
        match_options = {
            m["est_id"]: f"{'⏳ ' if m.get('vetting_status') == 'pending' else ''}"
                         f"{m['name']} (est_id: {m['est_id']}) — {m.get('address') or 'no address'}"
            for m in matches
        }
        # Vetting a scouted spot the team has now visited should funnel into
        # its existing pending est_id, not create a duplicate — default there.
        pending_ids = [m["est_id"] for m in matches if m.get("vetting_status") == "pending"]
        radio_options = ["new"] + list(match_options.keys())
        default_index = radio_options.index(pending_ids[0]) if (pending_ids and not is_scouted) else 0
        choice = st.radio(
            "Promote as:",
            options=radio_options,
            index=default_index,
            format_func=lambda x: "Create new site" if x == "new" else match_options[x],
        )
        target_est_id = None if choice == "new" else choice
        if not is_scouted and target_est_id in pending_ids:
            st.info("⏳ → ✅ Promoting menu-photo data into this pending spot will mark it **vetted**.")
    else:
        target_est_id = None
        st.info("No existing sites found with a similar name — will create a new entry.")

    button_label = "🔭 Promote as Pending Spot" if is_scouted else "🚀 Promote to Production"
    if st.button(button_label, type="primary"):
        label = "Updating existing site" if target_est_id else "Creating new site"
        with st.spinner(f"{label} and promoting to production tables..."):
            try:
                result_id = promote(selected_id, est_id=target_est_id)
                if is_scouted:
                    st.success(f"Promoted as pending spot! est_id: `{result_id}` — now on the map, flagged as pending.")
                else:
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

# --- Pending sites management ---
st.divider()
st.subheader("⏳ Pending spots in production")

try:
    pending = list_pending_sites()
except Exception as e:
    pending = []
    st.warning(f"Could not load pending sites: {e}")

if not pending:
    st.caption("No pending spots — everything on the map is vetted.")
else:
    st.caption(
        "Web-scouted spots awaiting a visit. Vet them by promoting menu-photo data "
        "into their est_id above, or manage them here."
    )
    for site in pending:
        c1, c2, c3 = st.columns([4, 1, 1])
        source = f" · [source]({site['source_url']})" if site.get("source_url") else ""
        c1.markdown(
            f"**{site['name']}** (est_id {site['est_id']}) — "
            f"{site.get('address') or 'no address'}{source}"
        )
        if c2.button("✅ Mark vetted", key=f"vet_{site['est_id']}"):
            try:
                mark_vetted(site["est_id"])
                st.success(f"{site['name']} marked vetted.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")
        if c3.button("🗑️ Retract", key=f"retract_{site['est_id']}"):
            try:
                retract_pending_site(site["est_id"])
                st.warning(f"{site['name']} retracted (deleted).")
                st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")
