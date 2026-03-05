import streamlit as st
from src.staging import list_extractions, get_extraction, update_extraction, set_status
from src.models import (
    SiteData, MenuData, ProteinData, HoursData, SalsaData, DescriptionData,
)

st.set_page_config(page_title="Staging Review", page_icon="📋", layout="wide")
st.title("📋 Staging Review")

# --- Filter & Select ---
status_filter = st.selectbox(
    "Filter by status",
    ["pending_review", "approved", "rejected", "promoted", None],
    format_func=lambda x: x or "All",
)
rows = list_extractions(status_filter)

if not rows:
    st.info("No extractions found.")
    st.stop()

options = {r["id"]: f"{r['restaurant_name']} ({r['status']}) — {r['created_at'][:10]}" for r in rows}
selected_id = st.selectbox("Select extraction", options.keys(), format_func=lambda x: options[x])

row = get_extraction(selected_id)

# --- Source Images ---
if row.get("source_image_urls"):
    st.subheader("Source Images")
    img_cols = st.columns(min(len(row["source_image_urls"]), 4))
    for i, url in enumerate(row["source_image_urls"]):
        img_cols[i % len(img_cols)].image(url, use_container_width=True)

st.divider()

# --- Editable Form ---
site = SiteData.model_validate(row["site_data"])
menu = MenuData.model_validate(row["menu_data"])
protein = ProteinData.model_validate(row["protein_data"])
hours = HoursData.model_validate(row["hours_data"])
salsa = SalsaData.model_validate(row["salsa_data"])
desc = DescriptionData.model_validate(row["description_data"])

tab_site, tab_menu, tab_protein, tab_hours, tab_salsa, tab_desc = st.tabs(
    ["Site Info", "Menu Items", "Proteins", "Hours", "Salsas", "Description"]
)

with tab_site:
    c1, c2 = st.columns(2)
    r_name = c1.text_input("Restaurant Name", row["restaurant_name"], key="r_name")
    site_type = c2.selectbox(
        "Type", ["Brick and Mortar", "Stand", "Truck", ""],
        index=["Brick and Mortar", "Stand", "Truck", ""].index(site.type)
        if site.type in ["Brick and Mortar", "Stand", "Truck"] else 3,
        key="r_type",
    )
    address = st.text_input("Address", site.address, key="r_addr")
    c1, c2, c3 = st.columns(3)
    phone = c1.text_input("Phone", site.phone, key="r_phone")
    website = c2.text_input("Website", site.website, key="r_web")
    instagram = c3.text_input("Instagram", site.instagram, key="r_ig")
    facebook = st.text_input("Facebook", site.facebook, key="r_fb")
    contact = st.text_input("Contact", site.contact, key="r_contact")

with tab_menu:
    menu_flags = {}
    items = [
        "burro", "taco", "torta", "dog", "plate", "cocktail", "gordita",
        "huarache", "cemita", "flauta", "chalupa", "molote", "tostada",
        "enchilada", "tamale", "sope", "caldo",
    ]
    cols = st.columns(4)
    for i, item in enumerate(items):
        key = f"{item}_yes"
        menu_flags[key] = cols[i % 4].checkbox(
            item.capitalize(), getattr(menu, key), key=f"rev_menu_{key}"
        )
    c1, c2 = st.columns(2)
    flour_corn = c1.selectbox(
        "Tortilla Type", ["", "Flour", "Corn", "Both"],
        index=["", "Flour", "Corn", "Both"].index(menu.flour_corn)
        if menu.flour_corn in ["", "Flour", "Corn", "Both"] else 0,
        key="rev_fc",
    )
    handmade = c2.checkbox("Handmade Tortilla", menu.handmade_tortilla, key="rev_hm")
    specialty_text = st.text_area(
        "Specialty Items (one per line)", "\n".join(menu.specialty_items), key="rev_spec"
    )

with tab_protein:
    prot_data = {}
    for prot in ["chicken", "beef", "pork", "fish", "veg"]:
        st.markdown(f"**{prot.capitalize()}**")
        prot_data[f"{prot}_yes"] = st.checkbox(
            f"Serves {prot}", getattr(protein, f"{prot}_yes"), key=f"rev_prot_{prot}"
        )
        c1, c2, c3 = st.columns(3)
        prot_data[f"{prot}_style_1"] = c1.text_input(
            "Style 1", getattr(protein, f"{prot}_style_1"), key=f"rev_prot_{prot}_s1"
        )
        prot_data[f"{prot}_style_2"] = c2.text_input(
            "Style 2", getattr(protein, f"{prot}_style_2"), key=f"rev_prot_{prot}_s2"
        )
        prot_data[f"{prot}_style_3"] = c3.text_input(
            "Style 3", getattr(protein, f"{prot}_style_3"), key=f"rev_prot_{prot}_s3"
        )

with tab_hours:
    hrs_data = {}
    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    day_labels = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for day, label in zip(days, day_labels):
        c1, c2 = st.columns(2)
        hrs_data[f"{day}_start"] = c1.text_input(
            f"{label} Open", getattr(hours, f"{day}_start"), key=f"rev_hrs_{day}_s"
        )
        hrs_data[f"{day}_end"] = c2.text_input(
            f"{label} Close", getattr(hours, f"{day}_end"), key=f"rev_hrs_{day}_e"
        )

with tab_salsa:
    total_num = st.number_input(
        "Total Salsas", value=salsa.total_num or 0, min_value=0, key="rev_salsa_total"
    )
    sal_flags = {}
    salsa_types = ["verde", "rojo", "pico", "pickles", "chipotle", "avo", "molcajete", "macha"]
    cols = st.columns(4)
    for i, s in enumerate(salsa_types):
        key = f"{s}_yes"
        sal_flags[key] = cols[i % 4].checkbox(
            s.capitalize(), getattr(salsa, key), key=f"rev_salsa_{key}"
        )
    other_sal = {}
    for n in [1, 2, 3]:
        c1, c2 = st.columns(2)
        other_sal[f"other_{n}_name"] = c1.text_input(
            f"Other {n} Name", getattr(salsa, f"other_{n}_name"), key=f"rev_salsa_o{n}_n"
        )
        other_sal[f"other_{n}_descrip"] = c2.text_input(
            f"Other {n} Description", getattr(salsa, f"other_{n}_descrip"), key=f"rev_salsa_o{n}_d"
        )

with tab_desc:
    short_descrip = st.text_area("Short Description", desc.short_descrip, key="rev_sd")
    long_descrip = st.text_area("Long Description", desc.long_descrip, key="rev_ld")
    region = st.text_input("Region", desc.region, key="rev_reg")

# --- Actions ---
st.divider()
notes = st.text_area("Notes", row.get("notes") or "", key="rev_notes")

col1, col2, col3 = st.columns(3)

if col1.button("💾 Save Changes"):
    updates = {
        "restaurant_name": r_name,
        "site_data": SiteData(
            name=r_name, type=site_type, address=address, phone=phone,
            website=website, instagram=instagram, facebook=facebook, contact=contact,
        ).model_dump(),
        "menu_data": MenuData(
            **menu_flags, flour_corn=flour_corn, handmade_tortilla=handmade,
            specialty_items=[s.strip() for s in specialty_text.split("\n") if s.strip()],
        ).model_dump(),
        "protein_data": ProteinData(**prot_data).model_dump(),
        "hours_data": HoursData(**hrs_data).model_dump(),
        "salsa_data": SalsaData(
            total_num=total_num if total_num > 0 else None, **sal_flags, **other_sal,
        ).model_dump(),
        "description_data": DescriptionData(
            short_descrip=short_descrip, long_descrip=long_descrip, region=region,
        ).model_dump(),
        "notes": notes,
    }
    update_extraction(selected_id, updates)
    st.success("Changes saved!")

if col2.button("✅ Approve"):
    set_status(selected_id, "approved")
    st.success("Marked as approved!")
    st.rerun()

if col3.button("❌ Reject"):
    set_status(selected_id, "rejected")
    st.warning("Marked as rejected.")
    st.rerun()
