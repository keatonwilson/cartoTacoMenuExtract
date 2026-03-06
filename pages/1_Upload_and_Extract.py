import streamlit as st
from src.extraction import extract_from_images, _resize_image
from src.staging import save_extraction, upload_image
from src.models import (
    ExtractedEstablishment,
    SiteData,
    MenuData,
    ProteinData,
    HoursData,
    SalsaData,
    DescriptionData,
)

st.set_page_config(page_title="Upload & Extract", page_icon="📸", layout="wide")
st.title("📸 Upload & Extract Menu")

# --- Upload ---
uploaded_files = st.file_uploader(
    "Upload menu photo(s)",
    type=["jpg", "jpeg", "png", "heic"],
    accept_multiple_files=True,
)

if uploaded_files:
    cols = st.columns(min(len(uploaded_files), 4))
    for i, f in enumerate(uploaded_files):
        cols[i % len(cols)].image(f, caption=f.name, use_container_width=True)

# --- Extract ---
if uploaded_files and st.button("🔍 Extract with Claude Vision", type="primary"):
    with st.spinner("Sending to Claude Vision..."):
        image_files = [(f.name, f.getvalue()) for f in uploaded_files]
        try:
            result, raw_json = extract_from_images(image_files)
            st.session_state["extraction"] = result
            st.session_state["raw_json"] = raw_json
            st.session_state["uploaded_files"] = uploaded_files
            st.success("Extraction complete!")
        except Exception as e:
            st.error(f"Extraction failed: {e}")

# --- Review Form ---
if "extraction" in st.session_state:
    ext: ExtractedEstablishment = st.session_state["extraction"]
    st.divider()
    st.subheader("Review & Edit Extracted Data")

    tab_site, tab_menu, tab_protein, tab_hours, tab_salsa, tab_desc = st.tabs(
        ["Site Info", "Menu Items", "Proteins", "Hours", "Salsas", "Description"]
    )

    # --- Site Info ---
    with tab_site:
        if st.button("🌐 Enrich from Web"):
            with st.spinner("Searching the web for business details..."):
                try:
                    from src.description_gen import enrich_from_web

                    result = enrich_from_web(ext.restaurant_name, ext.site.address)
                    if result.address and not ext.site.address:
                        ext.site.address = result.address
                    if result.phone and not ext.site.phone:
                        ext.site.phone = result.phone
                    if result.website and not ext.site.website:
                        ext.site.website = result.website
                    if result.instagram and not ext.site.instagram:
                        ext.site.instagram = result.instagram
                    if result.facebook and not ext.site.facebook:
                        ext.site.facebook = result.facebook
                    if result.hours:
                        for field_name, value in result.hours.items():
                            if value and not getattr(ext.hours, field_name, ""):
                                setattr(ext.hours, field_name, value)
                    st.session_state["extraction"] = ext
                    st.success("Enrichment complete! Empty fields have been filled in.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Enrichment failed: {e}")
        c1, c2 = st.columns(2)
        name = c1.text_input("Restaurant Name", ext.restaurant_name)
        site_type = c2.selectbox(
            "Type",
            ["Brick and Mortar", "Stand", "Truck", ""],
            index=["Brick and Mortar", "Stand", "Truck", ""].index(ext.site.type)
            if ext.site.type in ["Brick and Mortar", "Stand", "Truck"]
            else 3,
        )
        address = st.text_input("Address", ext.site.address)
        c1, c2, c3 = st.columns(3)
        phone = c1.text_input("Phone", ext.site.phone)
        website = c2.text_input("Website", ext.site.website)
        instagram = c3.text_input("Instagram", ext.site.instagram)
        facebook = st.text_input("Facebook", ext.site.facebook)
        contact = st.text_input("Contact", ext.site.contact)

    # --- Menu Items ---
    with tab_menu:
        st.markdown("**Items served:**")
        menu_flags = {}
        menu_percs = {}
        items = [
            "burro", "taco", "torta", "dog", "plate", "cocktail", "gordita",
            "huarache", "cemita", "flauta", "chalupa", "molote", "tostada",
            "enchilada", "tamale", "sope", "caldo",
        ]
        cols = st.columns(4)
        for i, item in enumerate(items):
            col = cols[i % 4]
            yes_key = f"{item}_yes"
            perc_key = f"{item}_perc"
            menu_flags[yes_key] = col.checkbox(
                item.capitalize(), getattr(ext.menu, yes_key), key=f"menu_{yes_key}"
            )
            menu_percs[perc_key] = col.number_input(
                f"{item.capitalize()} prop", min_value=0.0, max_value=1.0,
                value=float(getattr(ext.menu, perc_key) or 0.0),
                step=0.05, format="%.2f",
                key=f"menu_{perc_key}",
            ) or None
        c1, c2 = st.columns(2)
        flour_corn = c1.selectbox(
            "Tortilla Type",
            ["", "Flour", "Corn", "Both"],
            index=["", "Flour", "Corn", "Both"].index(ext.menu.flour_corn)
            if ext.menu.flour_corn in ["", "Flour", "Corn", "Both"]
            else 0,
        )
        handmade = c2.checkbox("Handmade Tortilla", ext.menu.handmade_tortilla)
        specialty_text = st.text_area(
            "Specialty Items (one per line)",
            "\n".join(ext.menu.specialty_items),
        )

    # --- Proteins ---
    with tab_protein:
        protein_data = {}
        for prot in ["chicken", "beef", "pork", "fish", "veg"]:
            st.markdown(f"**{prot.capitalize()}**")
            c_yes, c_perc = st.columns([2, 1])
            protein_data[f"{prot}_yes"] = c_yes.checkbox(
                f"Serves {prot}", getattr(ext.protein, f"{prot}_yes"), key=f"prot_{prot}"
            )
            protein_data[f"{prot}_perc"] = c_perc.number_input(
                f"{prot.capitalize()} prop", min_value=0.0, max_value=1.0,
                value=float(getattr(ext.protein, f"{prot}_perc") or 0.0),
                step=0.05, format="%.2f",
                key=f"prot_{prot}_perc",
            ) or None
            c1, c2, c3 = st.columns(3)
            protein_data[f"{prot}_style_1"] = c1.text_input(
                "Style 1", getattr(ext.protein, f"{prot}_style_1"), key=f"prot_{prot}_s1"
            )
            protein_data[f"{prot}_style_2"] = c2.text_input(
                "Style 2", getattr(ext.protein, f"{prot}_style_2"), key=f"prot_{prot}_s2"
            )
            protein_data[f"{prot}_style_3"] = c3.text_input(
                "Style 3", getattr(ext.protein, f"{prot}_style_3"), key=f"prot_{prot}_s3"
            )

    # --- Hours ---
    with tab_hours:
        hours_data = {}
        days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        day_labels = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for day, label in zip(days, day_labels):
            c1, c2 = st.columns(2)
            hours_data[f"{day}_start"] = c1.text_input(
                f"{label} Open", getattr(ext.hours, f"{day}_start"), key=f"hrs_{day}_s",
                placeholder="e.g. 10:00 or 10am",
            )
            hours_data[f"{day}_end"] = c2.text_input(
                f"{label} Close", getattr(ext.hours, f"{day}_end"), key=f"hrs_{day}_e",
                placeholder="e.g. 10:00 or 10pm",
            )

    # --- Salsas ---
    with tab_salsa:
        total_num = st.number_input("Total Salsas", value=ext.salsa.total_num or 0, min_value=0)
        salsa_flags = {}
        salsa_types = ["verde", "rojo", "pico", "pickles", "chipotle", "avo", "molcajete", "macha"]
        cols = st.columns(4)
        for i, s in enumerate(salsa_types):
            key = f"{s}_yes"
            salsa_flags[key] = cols[i % 4].checkbox(
                s.capitalize(), getattr(ext.salsa, key), key=f"salsa_{key}"
            )
        st.markdown("**Other salsas:**")
        other_salsa = {}
        for n in [1, 2, 3]:
            c1, c2 = st.columns(2)
            other_salsa[f"other_{n}_name"] = c1.text_input(
                f"Other {n} Name", getattr(ext.salsa, f"other_{n}_name"), key=f"salsa_o{n}_n"
            )
            other_salsa[f"other_{n}_descrip"] = c2.text_input(
                f"Other {n} Description",
                getattr(ext.salsa, f"other_{n}_descrip"),
                key=f"salsa_o{n}_d",
            )

    # --- Description ---
    with tab_desc:
        if st.button("✨ Generate Descriptions"):
            with st.spinner("Generating descriptions with Claude..."):
                try:
                    from src.description_gen import generate_descriptions

                    # Build current state into an ExtractedEstablishment
                    current = ExtractedEstablishment(
                        restaurant_name=name,
                        site=SiteData(name=name, type=site_type, address=address),
                        menu=MenuData(
                            **menu_flags, **menu_percs, flour_corn=flour_corn,
                            handmade_tortilla=handmade,
                            specialty_items=[s.strip() for s in specialty_text.split("\n") if s.strip()],
                        ),
                        protein=ProteinData(**protein_data),
                        hours=HoursData(**hours_data),
                        salsa=SalsaData(
                            total_num=total_num if total_num > 0 else None,
                            **salsa_flags, **other_salsa,
                        ),
                        description=DescriptionData(
                            short_descrip=ext.description.short_descrip,
                            long_descrip=ext.description.long_descrip,
                            region=ext.description.region,
                        ),
                    )
                    short_gen, long_gen = generate_descriptions(current)
                    ext.description.short_descrip = short_gen
                    ext.description.long_descrip = long_gen
                    st.session_state["extraction"] = ext
                    st.rerun()
                except Exception as e:
                    st.error(f"Description generation failed: {e}")
        short_descrip = st.text_area("Short Description", ext.description.short_descrip)
        long_descrip = st.text_area("Long Description", ext.description.long_descrip)
        region = st.text_input("Region", ext.description.region)

    # --- Save to Staging ---
    st.divider()
    notes = st.text_area("Notes (optional)")

    if st.button("💾 Save to Staging", type="primary"):
        with st.spinner("Uploading images and saving..."):
            try:
                # Build updated models from form state
                updated = ExtractedEstablishment(
                    restaurant_name=name,
                    site=SiteData(
                        name=name, type=site_type, address=address, phone=phone,
                        website=website, instagram=instagram, facebook=facebook,
                        contact=contact,
                    ),
                    menu=MenuData(
                        **menu_flags, **menu_percs,
                        flour_corn=flour_corn,
                        handmade_tortilla=handmade,
                        specialty_items=[s.strip() for s in specialty_text.split("\n") if s.strip()],
                    ),
                    protein=ProteinData(**protein_data),
                    hours=HoursData(**hours_data),
                    salsa=SalsaData(
                        total_num=total_num if total_num > 0 else None,
                        **salsa_flags,
                        **other_salsa,
                    ),
                    description=DescriptionData(
                        short_descrip=short_descrip,
                        long_descrip=long_descrip,
                        region=region,
                    ),
                )

                # Upload images to Supabase Storage
                image_urls = []
                for f in st.session_state.get("uploaded_files", []):
                    resized = _resize_image(f.getvalue())
                    url = upload_image(resized, f.name)
                    image_urls.append(url)

                row_id = save_extraction(
                    updated, st.session_state["raw_json"], image_urls
                )
                st.success(f"Saved to staging! ID: `{row_id}`")
                # Clear extraction from session
                del st.session_state["extraction"]
                del st.session_state["raw_json"]
                del st.session_state["uploaded_files"]
            except Exception as e:
                st.error(f"Save failed: {e}")
