import streamlit as st

from src.models import ScrapedSpot, SiteData, HoursData, DescriptionData
from src.scraping import scout_spot, find_duplicates
from src.staging import save_scraped_spot
from src.description_gen import geocode_address

st.set_page_config(page_title="Scout New Spots", page_icon="🔭", layout="wide")
st.title("🔭 Scout New Spots")
st.markdown(
    "Research a taco spot we haven't visited yet. Claude searches the web for "
    "business details, you review and geocode, and the spot stages as a "
    "**pending (unvetted)** entry — it appears on the map flagged as pending "
    "until the team visits and runs the normal menu-photo pipeline."
)

CONFIDENCE_ICONS = {"high": "🟢", "medium": "🟡", "low": "🔴"}

# --- Input ---
name_input = st.text_input("Spot name", placeholder="e.g. Tacos El Ejemplo")
urls_input = st.text_area(
    "Known URLs (optional, one per line)",
    placeholder="https://instagram.com/tacoselejemplo\nhttps://tacoselejemplo.com",
    help="The spot's own website/socials if you already found them — steers the search.",
)

if st.button("🔭 Scout the web", type="primary", disabled=not name_input.strip()):
    hint_urls = [u.strip() for u in urls_input.split("\n") if u.strip()]
    with st.spinner("Searching the web and structuring what's out there..."):
        try:
            spot, raw = scout_spot(name_input.strip(), hint_urls)
            st.session_state["scout_result"] = spot.model_dump()
            st.session_state["scout_raw"] = raw
            # Clear stale form state from a previous scout
            for key in list(st.session_state.keys()):
                if key.startswith("sc_"):
                    del st.session_state[key]
            st.rerun()
        except Exception as e:
            st.error(f"Scouting failed: {e}")

if "scout_result" not in st.session_state:
    st.stop()

spot = ScrapedSpot.model_validate(st.session_state["scout_result"])

st.divider()

# --- Confidence + evidence ---
conf_bits = [
    f"{CONFIDENCE_ICONS.get(spot.confidence.get(section, ''), '⚪')} {section}: "
    f"{spot.confidence.get(section, 'unknown')}"
    for section in ("site", "hours", "description")
]
st.markdown("**Confidence:** " + " · ".join(conf_bits))
if spot.evidence_urls:
    st.markdown("**Sources:** " + " · ".join(f"[{u}]({u})" for u in spot.evidence_urls))

# --- Editable review form ---
tab_site, tab_hours, tab_desc = st.tabs(["Site Info", "Hours", "Description"])

with tab_site:
    c1, c2 = st.columns(2)
    r_name = c1.text_input("Name", spot.site.name or spot.restaurant_name, key="sc_name")
    site_type = c2.selectbox(
        "Type", ["Brick and Mortar", "Stand", "Truck", ""],
        index=["Brick and Mortar", "Stand", "Truck", ""].index(spot.site.type)
        if spot.site.type in ["Brick and Mortar", "Stand", "Truck"] else 3,
        key="sc_type",
    )
    address = st.text_input("Address", spot.site.address, key="sc_addr")
    days_loc = st.text_input(
        "Typical location/days (trucks & stands)", spot.site.days_loc_1, key="sc_days"
    )
    c1, c2, c3 = st.columns(3)
    phone = c1.text_input("Phone", spot.site.phone, key="sc_phone")
    website = c2.text_input("Website", spot.site.website, key="sc_web")
    instagram = c3.text_input("Instagram", spot.site.instagram, key="sc_ig")
    facebook = st.text_input("Facebook", spot.site.facebook, key="sc_fb")

    c1, c2 = st.columns(2)
    if "sc_lat_geocoded" in st.session_state:
        st.session_state["sc_lat"] = st.session_state.pop("sc_lat_geocoded")
        st.session_state["sc_lon"] = st.session_state.pop("sc_lon_geocoded")
    if "sc_lat" not in st.session_state:
        st.session_state["sc_lat"] = spot.site.lat_1 or 0.0
    if "sc_lon" not in st.session_state:
        st.session_state["sc_lon"] = spot.site.lon_1 or 0.0
    lat_1 = c1.number_input("Latitude", format="%.6f", key="sc_lat")
    lon_1 = c2.number_input("Longitude", format="%.6f", key="sc_lon")

    if st.button("📍 Geocode from Address"):
        if address:
            with st.spinner("Geocoding..."):
                coords = geocode_address(address)
                if coords:
                    st.session_state["sc_lat_geocoded"] = coords[0]
                    st.session_state["sc_lon_geocoded"] = coords[1]
                    st.success(f"Found: {coords[0]:.6f}, {coords[1]:.6f}")
                    st.rerun()
                else:
                    st.warning("Could not geocode address.")
        else:
            st.warning("Enter an address first.")

    if lat_1 and lon_1:
        st.map({"lat": [lat_1], "lon": [lon_1]}, zoom=13)

with tab_hours:
    st.caption("Only include hours a source actually states — unknown days stay blank.")
    hrs_data = {}
    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    day_labels = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for day, label in zip(days, day_labels):
        c1, c2 = st.columns(2)
        hrs_data[f"{day}_start"] = c1.text_input(
            f"{label} Open", getattr(spot.hours, f"{day}_start"), key=f"sc_hrs_{day}_s",
            placeholder="e.g. 10:00 or 10am",
        )
        hrs_data[f"{day}_end"] = c2.text_input(
            f"{label} Close", getattr(spot.hours, f"{day}_end"), key=f"sc_hrs_{day}_e",
            placeholder="e.g. 10:00 or 10pm",
        )

with tab_desc:
    st.caption("Original AI-written text from scraped facts — shown on the pending card.")
    short_descrip = st.text_area("Short Description", spot.description.short_descrip, key="sc_sd")
    long_descrip = st.text_area("Long Description", spot.description.long_descrip, key="sc_ld")
    region = st.text_input("Region", spot.description.region, key="sc_reg")

# --- Duplicate check ---
st.divider()
st.subheader("Duplicate check")
dupes = find_duplicates(r_name, lat_1 or None, lon_1 or None)

has_dupes = bool(dupes["production"] or dupes["staging"])
if has_dupes:
    for m in dupes["production"]:
        status = "⏳ pending" if m.get("vetting_status") == "pending" else "✅ vetted"
        st.warning(
            f"Production: **{m['name']}** (est_id {m['est_id']}, {status}, "
            f"{m.get('address') or 'no address'}) — matched by {m['match']}"
        )
    for m in dupes["staging"]:
        st.warning(
            f"Staging: **{m['restaurant_name']}** ({m['status']}, {m.get('pipeline', 'menu_photo')}, "
            f"{m['created_at'][:10]})"
        )
    acknowledged = st.checkbox("These are different spots — stage anyway")
else:
    st.success("No similar names in production or staging, nothing within 150 m.")
    acknowledged = True

# --- Save ---
if st.button("💾 Save to staging as pending spot", type="primary", disabled=not acknowledged):
    try:
        reviewed = ScrapedSpot(
            restaurant_name=r_name,
            site=SiteData(
                name=r_name, type=site_type, address=address, phone=phone,
                website=website, instagram=instagram, facebook=facebook,
                days_loc_1=days_loc, lat_1=lat_1 or None, lon_1=lon_1 or None,
            ),
            hours=HoursData(**hrs_data),
            description=DescriptionData(
                short_descrip=short_descrip, long_descrip=long_descrip, region=region,
            ),
            confidence=spot.confidence,
            evidence_urls=spot.evidence_urls,
        )
        row_id = save_scraped_spot(reviewed, st.session_state.get("scout_raw", {}))
        st.success(f"Staged! Row ID: `{row_id}` — review/approve it in Staging Review, then promote.")
        del st.session_state["scout_result"]
    except Exception as e:
        st.error(f"Save failed: {e}")
