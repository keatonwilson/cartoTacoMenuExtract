import uuid

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


def _clear_form_state():
    """Drop all keyed form widget state so the next extraction starts clean."""
    for k in list(st.session_state.keys()):
        if k.startswith(("menu_", "prot_", "hrs_", "salsa_", "site_", "lat_", "lon_", "desc_", "notes")):
            del st.session_state[k]

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
            _clear_form_state()  # discard any prior establishment's form state
            st.session_state["extraction"] = result
            st.session_state["raw_json"] = raw_json
            st.session_state["uploaded_files"] = uploaded_files
            # New namespace token so every form widget is a brand-new widget that
            # initializes from this extraction (Streamlit retains widget state by
            # identity, so reusing keys would bleed the prior establishment in).
            st.session_state["form_token"] = uuid.uuid4().hex
            st.success("Extraction complete!")
        except Exception as e:
            st.error(f"Extraction failed: {e}")

# --- Review Form ---
if "extraction" in st.session_state:
    ext: ExtractedEstablishment = st.session_state["extraction"]
    ftok = st.session_state.get("form_token", "")

    def K(base: str) -> str:
        """Namespace a widget key to the current extraction."""
        return f"{base}__{ftok}"

    st.divider()
    st.subheader("Review & Edit Extracted Data")

    tab_site, tab_menu, tab_protein, tab_hours, tab_salsa, tab_desc = st.tabs(
        ["Site Info", "Menu Items", "Proteins", "Hours", "Salsas", "Description"]
    )

    # --- Site Info ---
    with tab_site:
        # Seed keyed widget state from the extraction once (cleared on new
        # extraction / save). Enrich/geocode write into these same keys so their
        # results reliably appear in the form.
        site_defaults = {
            K("site_name"): ext.restaurant_name,
            K("site_addr"): ext.site.address,
            K("site_phone"): ext.site.phone,
            K("site_web"): ext.site.website,
            K("site_ig"): ext.site.instagram,
            K("site_fb"): ext.site.facebook,
            K("site_contact"): ext.site.contact,
        }
        for k, v in site_defaults.items():
            if k not in st.session_state:
                st.session_state[k] = v
        # Apply a pending geocode result, then init lat/lon from the extraction.
        if K("lat_geocoded") in st.session_state:
            st.session_state[K("lat_1")] = st.session_state.pop(K("lat_geocoded"))
            st.session_state[K("lon_1")] = st.session_state.pop(K("lon_geocoded"))
        if K("lat_1") not in st.session_state:
            st.session_state[K("lat_1")] = ext.site.lat_1 or 0.0
        if K("lon_1") not in st.session_state:
            st.session_state[K("lon_1")] = ext.site.lon_1 or 0.0

        if st.button("🌐 Enrich from Web"):
            with st.spinner("Searching the web for business details..."):
                try:
                    from src.description_gen import enrich_from_web

                    result = enrich_from_web(
                        st.session_state[K("site_name")], st.session_state[K("site_addr")]
                    )
                    if result.address and not st.session_state[K("site_addr")]:
                        st.session_state[K("site_addr")] = result.address
                    if result.phone and not st.session_state[K("site_phone")]:
                        st.session_state[K("site_phone")] = result.phone
                    if result.website and not st.session_state[K("site_web")]:
                        st.session_state[K("site_web")] = result.website
                    if result.instagram and not st.session_state[K("site_ig")]:
                        st.session_state[K("site_ig")] = result.instagram
                    if result.facebook and not st.session_state[K("site_fb")]:
                        st.session_state[K("site_fb")] = result.facebook
                    if result.hours:
                        for field_name, value in result.hours.items():
                            hrs_key = K(f"hrs_{field_name.replace('_start', '_s').replace('_end', '_e')}")
                            if value and not st.session_state.get(hrs_key, ""):
                                st.session_state[hrs_key] = value
                    st.success("Enrichment complete! Empty fields have been filled in.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Enrichment failed: {e}")
        c1, c2 = st.columns(2)
        name = c1.text_input("Restaurant Name", key=K("site_name"))
        site_type = c2.selectbox(
            "Type",
            ["Brick and Mortar", "Stand", "Truck", ""],
            index=["Brick and Mortar", "Stand", "Truck", ""].index(ext.site.type)
            if ext.site.type in ["Brick and Mortar", "Stand", "Truck"]
            else 3,
            key=K("site_type"),
        )
        address = st.text_input("Address", key=K("site_addr"))
        c1, c2, c3 = st.columns(3)
        phone = c1.text_input("Phone", key=K("site_phone"))
        website = c2.text_input("Website", key=K("site_web"))
        instagram = c3.text_input("Instagram", key=K("site_ig"))
        facebook = st.text_input("Facebook", key=K("site_fb"))
        contact = st.text_input("Contact", key=K("site_contact"))
        c1, c2 = st.columns(2)
        lat_1 = c1.number_input("Latitude", format="%.6f", key=K("lat_1"))
        lon_1 = c2.number_input("Longitude", format="%.6f", key=K("lon_1"))
        if st.button("📍 Geocode from Address"):
            if address:
                with st.spinner("Geocoding..."):
                    from src.description_gen import geocode_address
                    coords = geocode_address(address)
                    if coords:
                        st.session_state[K("lat_geocoded")] = coords[0]
                        st.session_state[K("lon_geocoded")] = coords[1]
                        st.success(f"Found: {coords[0]:.6f}, {coords[1]:.6f}")
                        st.rerun()
                    else:
                        st.warning("Could not geocode address.")
            else:
                st.warning("Enter an address first.")

    # --- Menu Items ---
    with tab_menu:
        st.markdown("**Items served:**")
        menu_flags = {}
        menu_percs = {}
        items = [
            "burro", "taco", "torta", "dog", "plate", "cocktail", "gordita",
            "huarache", "cemita", "flauta", "chalupa", "molote", "tostada",
            "enchilada", "tamale", "sope", "caldo", "snacks", "quesadilla",
        ]
        cols = st.columns(4)
        for i, item in enumerate(items):
            col = cols[i % 4]
            yes_key = f"{item}_yes"
            perc_key = f"{item}_perc"
            menu_flags[yes_key] = col.checkbox(
                item.capitalize(), getattr(ext.menu, yes_key), key=K(f"menu_{yes_key}")
            )
            menu_percs[perc_key] = col.number_input(
                f"{item.capitalize()} prop", min_value=0.0, max_value=1.0,
                value=float(getattr(ext.menu, perc_key) or 0.0),
                step=0.05, format="%.2f",
                key=K(f"menu_{perc_key}"),
            ) or None
        c1, c2 = st.columns(2)
        flour_corn = c1.selectbox(
            "Tortilla Type",
            ["", "Flour", "Corn", "Both"],
            index=["", "Flour", "Corn", "Both"].index(ext.menu.flour_corn)
            if ext.menu.flour_corn in ["", "Flour", "Corn", "Both"]
            else 0,
            key=K("menu_flour_corn"),
        )
        handmade = c2.checkbox("Handmade Tortilla", ext.menu.handmade_tortilla, key=K("menu_handmade"))
        specialty_text = st.text_area(
            "Specialty Items (one per line)",
            "\n".join(ext.menu.specialty_items),
            key=K("menu_specialty"),
        )

    # --- Proteins ---
    with tab_protein:
        protein_data = {}
        for prot in ["chicken", "beef", "pork", "fish", "veg"]:
            st.markdown(f"**{prot.capitalize()}**")
            c_yes, c_perc = st.columns([2, 1])
            protein_data[f"{prot}_yes"] = c_yes.checkbox(
                f"Serves {prot}", getattr(ext.protein, f"{prot}_yes"), key=K(f"prot_{prot}")
            )
            protein_data[f"{prot}_perc"] = c_perc.number_input(
                f"{prot.capitalize()} prop", min_value=0.0, max_value=1.0,
                value=float(getattr(ext.protein, f"{prot}_perc") or 0.0),
                step=0.05, format="%.2f",
                key=K(f"prot_{prot}_perc"),
            ) or None
            c1, c2, c3 = st.columns(3)
            protein_data[f"{prot}_style_1"] = c1.text_input(
                "Style 1", getattr(ext.protein, f"{prot}_style_1"), key=K(f"prot_{prot}_s1")
            )
            protein_data[f"{prot}_style_2"] = c2.text_input(
                "Style 2", getattr(ext.protein, f"{prot}_style_2"), key=K(f"prot_{prot}_s2")
            )
            protein_data[f"{prot}_style_3"] = c3.text_input(
                "Style 3", getattr(ext.protein, f"{prot}_style_3"), key=K(f"prot_{prot}_s3")
            )
        protein_spec_text = st.text_area(
            "Specialty Proteins (one per line)",
            "\n".join(ext.protein.protein_specs),
            key=K("prot_specs"),
        )

    # --- Hours ---
    with tab_hours:
        hours_data = {}
        days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        day_labels = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for day, label in zip(days, day_labels):
            c1, c2 = st.columns(2)
            hours_data[f"{day}_start"] = c1.text_input(
                f"{label} Open", getattr(ext.hours, f"{day}_start"), key=K(f"hrs_{day}_s"),
                placeholder="e.g. 10:00 or 10am",
            )
            hours_data[f"{day}_end"] = c2.text_input(
                f"{label} Close", getattr(ext.hours, f"{day}_end"), key=K(f"hrs_{day}_e"),
                placeholder="e.g. 10:00 or 10pm",
            )

    # --- Salsas ---
    with tab_salsa:
        c1, c2 = st.columns(2)
        total_num = c1.number_input("Total Salsas", value=ext.salsa.total_num or 0, min_value=0, key=K("salsa_total"))
        heat_overall = c2.number_input(
            "Overall Heat (1–10)", min_value=1, max_value=10,
            value=ext.salsa.heat_overall or 1, key=K("salsa_heat"),
        ) or None
        salsa_flags = {}
        salsa_types = ["verde", "rojo", "pico", "pickles", "chipotle", "avo", "molcajete", "macha"]
        cols = st.columns(4)
        for i, s in enumerate(salsa_types):
            key = f"{s}_yes"
            salsa_flags[key] = cols[i % 4].checkbox(
                s.capitalize(), getattr(ext.salsa, key), key=K(f"salsa_{key}")
            )
        st.markdown("**Other salsas:**")
        other_salsa = {}
        for n in [1, 2, 3]:
            c1, c2 = st.columns(2)
            other_salsa[f"other_{n}_name"] = c1.text_input(
                f"Other {n} Name", getattr(ext.salsa, f"other_{n}_name"), key=K(f"salsa_o{n}_n")
            )
            other_salsa[f"other_{n}_descrip"] = c2.text_input(
                f"Other {n} Description",
                getattr(ext.salsa, f"other_{n}_descrip"),
                key=K(f"salsa_o{n}_d"),
            )
        salsa_spec_text = st.text_area(
            "Specialty Salsas (one per line)",
            "\n".join(ext.salsa.salsa_specs),
            key=K("salsa_specs"),
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
                        site=SiteData(name=name, type=site_type, address=address,
                            lat_1=lat_1 or None, lon_1=lon_1 or None),
                        menu=MenuData(
                            **menu_flags, **menu_percs, flour_corn=flour_corn,
                            handmade_tortilla=handmade,
                            specialty_items=[s.strip() for s in specialty_text.split("\n") if s.strip()],
                        ),
                        protein=ProteinData(
                            **protein_data,
                            protein_specs=[s.strip() for s in protein_spec_text.split("\n") if s.strip()],
                        ),
                        hours=HoursData(**hours_data),
                        salsa=SalsaData(
                            total_num=total_num if total_num > 0 else None,
                            heat_overall=heat_overall,
                            **salsa_flags, **other_salsa,
                            salsa_specs=[s.strip() for s in salsa_spec_text.split("\n") if s.strip()],
                        ),
                        description=DescriptionData(
                            short_descrip=ext.description.short_descrip,
                            long_descrip=ext.description.long_descrip,
                            region=ext.description.region,
                        ),
                    )
                    short_gen, long_gen = generate_descriptions(current)
                    st.session_state[K("desc_short")] = short_gen
                    st.session_state[K("desc_long")] = long_gen
                    # Keep the in-memory extraction in sync too.
                    ext.description.short_descrip = short_gen
                    ext.description.long_descrip = long_gen
                    st.session_state["extraction"] = ext
                    st.rerun()
                except Exception as e:
                    st.error(f"Description generation failed: {e}")
        if K("desc_short") not in st.session_state:
            st.session_state[K("desc_short")] = ext.description.short_descrip
        if K("desc_long") not in st.session_state:
            st.session_state[K("desc_long")] = ext.description.long_descrip
        if K("desc_region") not in st.session_state:
            st.session_state[K("desc_region")] = ext.description.region
        short_descrip = st.text_area("Short Description", key=K("desc_short"))
        long_descrip = st.text_area("Long Description", key=K("desc_long"))
        region = st.text_input("Region", key=K("desc_region"))

    # --- Save to Staging ---
    st.divider()
    notes = st.text_area("Notes (optional)", key=K("notes"))

    if st.button("💾 Save to Staging", type="primary"):
        with st.spinner("Uploading images and saving..."):
            try:
                # Build updated models from form state
                updated = ExtractedEstablishment(
                    restaurant_name=name,
                    site=SiteData(
                        name=name, type=site_type, address=address, phone=phone,
                        website=website, instagram=instagram, facebook=facebook,
                        contact=contact, lat_1=lat_1 or None, lon_1=lon_1 or None,
                    ),
                    menu=MenuData(
                        **menu_flags, **menu_percs,
                        flour_corn=flour_corn,
                        handmade_tortilla=handmade,
                        specialty_items=[s.strip() for s in specialty_text.split("\n") if s.strip()],
                    ),
                    protein=ProteinData(
                        **protein_data,
                        protein_specs=[s.strip() for s in protein_spec_text.split("\n") if s.strip()],
                    ),
                    hours=HoursData(**hours_data),
                    salsa=SalsaData(
                        total_num=total_num if total_num > 0 else None,
                        heat_overall=heat_overall,
                        **salsa_flags, **other_salsa,
                        salsa_specs=[s.strip() for s in salsa_spec_text.split("\n") if s.strip()],
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
                # Clear extraction + all form state so the next upload starts clean
                del st.session_state["extraction"]
                del st.session_state["raw_json"]
                del st.session_state["uploaded_files"]
                st.session_state.pop("form_token", None)
                _clear_form_state()
            except Exception as e:
                st.error(f"Save failed: {e}")
