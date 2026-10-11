"""Salsa Field Notes: photos taken at a spot → sightings and catalog entries for the Salsa Atlas."""

from datetime import date

import pandas as pd
import streamlit as st

from src import salsa_field as sf

st.set_page_config(page_title="Salsa Field Notes", page_icon="🌶️", layout="wide")
st.title("🌶️ Salsa Field Notes")
st.caption(
    "In the field: photograph the salsa with the grey card in frame, location services on. "
    "Here: upload the photo, confirm the spot and the colours, and save."
)

try:
    sites = sf.list_sites()
    styles = sf.list_styles()
except Exception as e:
    st.error(f"Could not load sites and salsa styles: {e}")
    st.info("The Salsa Atlas tables come from cartoTaco migrations 036–038. Have they reached this database?")
    st.stop()

NEW_STYLE = "➕ New style (saved as a draft)"


def swatches(palette: list[str]) -> None:
    """A row of colour chips with their hex codes."""
    chips = "".join(
        f'<span style="display:inline-block;width:64px;height:44px;background:{c};'
        f'border:1px solid #0003"></span>'
        for c in palette
    )
    st.markdown(chips + "<br><code>" + "  ".join(palette) + "</code>", unsafe_allow_html=True)


def box_sliders(label: str, box: sf.Box, key: str) -> sf.Box:
    """Two range sliders (across, down) that edit a fractional box."""
    x = st.slider(f"{label}: across", 0.0, 1.0, (box[0], box[2]), 0.01, key=f"{key}_x")
    y = st.slider(f"{label}: down", 0.0, 1.0, (box[1], box[3]), 0.01, key=f"{key}_y")
    return (x[0], y[0], x[1], y[1])


def style_label(style: dict) -> str:
    return style["name"] + (" (draft)" if style["status"] == "draft" else "")


tab_new, tab_sightings, tab_catalog = st.tabs(["📸 New sighting", "🗂 Sightings", "📚 Catalog"])

# ── New sighting ─────────────────────────────────────────────────────────────
with tab_new:
    upload = st.file_uploader("Salsa photo", type=["jpg", "jpeg", "png", "heic", "heif"], key="sighting_photo")

    if upload:
        raw = upload.getvalue()
        try:
            photo = sf.load_photo(raw)
        except Exception as e:
            st.error(f"Could not read that image ({e}). For HEIC photos, run `pip install pillow-heif`.")
            st.stop()
        meta = sf.read_photo_meta(raw)

        # A new photo resets the regions found for the last one
        if st.session_state.get("sighting_file") != upload.file_id:
            st.session_state["sighting_file"] = upload.file_id
            st.session_state["located"] = None
            for k in ("salsa_x", "salsa_y", "card_x", "card_y"):
                st.session_state.pop(k, None)

        left, right = st.columns([3, 2])

        with right:
            st.subheader("1 · Where")
            if meta["lat"] is not None:
                ranked = sf.nearest_sites(sites, meta["lat"], meta["lon"])
                st.caption("Spots ordered by distance from where the photo was taken.")
                site = st.selectbox(
                    "Spot", ranked, format_func=lambda s: f"{s['name']} · {round(s['distance_m'])} m"
                )
                if ranked and ranked[0]["distance_m"] > 300:
                    st.warning("The nearest spot is over 300 m from this photo. Is the spot in CartoTaco yet?")
            else:
                st.caption("No location in this photo, so spots are in name order.")
                site = st.selectbox("Spot", sites, format_func=lambda s: s["name"])

            st.subheader("2 · Colour")
            if st.button("✨ Find the salsa and the card", help="Asks Claude to outline both in the photo"):
                with st.spinner("Looking at the photo…"):
                    try:
                        found = sf.locate_regions(photo, [s["slug"] for s in styles])
                        st.session_state["located"] = found
                        for k in ("salsa_x", "salsa_y", "card_x", "card_y"):
                            st.session_state.pop(k, None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not analyse the photo: {e}")
            located = st.session_state.get("located") or {}

            salsa_box = box_sliders("Salsa", located.get("salsa_box") or sf.DEFAULT_SALSA_BOX, "salsa")
            has_card = st.checkbox(
                "Grey card is in the photo",
                value=bool(located.get("card_box")),
                help="Without a card the colours keep whatever cast the lighting gave them.",
            )
            card_box = box_sliders("Card", located.get("card_box") or (0.05, 0.05, 0.2, 0.2), "card") if has_card else None

            card_grey = None
            if has_card:
                known = st.checkbox(
                    "It is a standard 18% grey card",
                    value=True,
                    help="Also corrects exposure: the photo is brightened or darkened until the card reads its "
                    "true grey. Untick for a white card or a card of unknown grey; only the colour cast is removed.",
                )
                card_grey = sf.GREY_CARD_18 if known else None

            corrected = sf.white_balance(photo, card_box, card_grey) if card_box else photo
            palette = sf.extract_palette(corrected, salsa_box)
            st.caption("Sampled colours, most dominant first. Adjust any that look wrong.")
            cols = st.columns(len(palette))
            palette = [
                col.color_picker(f"No. {i + 1}", c, key=f"pick_{upload.file_id}_{c}_{i}").lower()
                for i, (col, c) in enumerate(zip(cols, palette))
            ]
            if not card_box:
                st.warning("No grey card: these hex codes are not corrected for the lighting.")

        with left:
            st.image(
                sf.annotate(corrected, salsa_box, card_box),
                caption="Red: sampled salsa · Blue: grey card" + (" · white-balanced" if card_box else ""),
                use_container_width=True,
            )

        st.subheader("3 · What")
        guess = next((s for s in styles if s["slug"] == located.get("style_slug")), None)
        options = styles + [NEW_STYLE]
        choice = st.selectbox(
            "Salsa style",
            options,
            index=options.index(guess) if guess else 0,
            format_func=lambda s: s if isinstance(s, str) else style_label(s),
        )
        if guess:
            st.caption(f"Claude's guess from the photo: {guess['name']}.")
        if located.get("visible_ingredients"):
            st.caption("Visible in the photo: " + ", ".join(located["visible_ingredients"]) + ".")

        new_name = new_family = new_region = None
        if choice == NEW_STYLE:
            c1, c2, c3 = st.columns(3)
            new_name = c1.text_input("Name", placeholder="Salsa de …")
            new_family = c2.selectbox("Family", sf.FAMILIES)
            new_region = c3.selectbox("Region", sf.REGIONS)

        c1, c2, c3 = st.columns(3)
        rate_heat = c1.checkbox("Record heat", value=True)
        heat = c1.slider("Heat at this spot", 0, 10, 5, disabled=not rate_heat)
        house_name = c2.text_input("What the spot calls it", placeholder="optional")
        observed = c3.date_input("Date", value=meta["taken_on"] or date.today())
        note = st.text_area(
            "Note",
            placeholder="What you learned here, in your own words. Paraphrase; don't quote or name people.",
        )

        if st.button("Save sighting", type="primary"):
            if choice == NEW_STYLE and not (new_name or "").strip():
                st.error("Give the new style a name.")
            else:
                try:
                    style = (
                        sf.draft_style_from_sighting(new_name, new_family, new_region, palette, located.get("chunk"))
                        if choice == NEW_STYLE
                        else choice
                    )
                    photo_url = sf.upload_photo(sf.to_jpeg(corrected), f"sightings/{site['est_id']}")
                    sf.save_sighting(
                        site["est_id"],
                        style["id"],
                        {
                            "photo_url": photo_url,
                            "palette": palette,
                            "observed_at": observed.isoformat(),
                            "heat": heat if rate_heat else None,
                            "house_name": house_name.strip() or None,
                            "note": note.strip() or None,
                        },
                    )
                    st.success(f"Saved {style['name']} at {site['name']}.")
                    if choice == NEW_STYLE:
                        st.info("The new style is a draft. Finish and publish it on the Catalog tab.")
                except Exception as e:
                    st.error(f"Could not save: {e}")

# ── Sightings ────────────────────────────────────────────────────────────────
with tab_sightings:
    try:
        links = sf.list_sightings()
    except Exception as e:
        links = []
        st.error(f"Could not load sightings: {e}")

    documented = [link for link in links if link.get("photo_url")]
    st.caption(f"{len(documented)} of {len(links)} spot–salsa links have a field photo.")
    only_documented = st.toggle("Only links with a photo", value=True)

    for link in documented if only_documented else links:
        title = f"{link['salsa_styles']['name']} at {link['sites']['name']}"
        with st.expander(title + (f" · {link['observed_at']}" if link.get("observed_at") else "")):
            key = f"link_{link['est_id']}_{link['style_id']}"
            c1, c2 = st.columns([1, 2])
            if link.get("photo_url"):
                c1.image(link["photo_url"], use_container_width=True)
            with c2:
                if link.get("palette"):
                    swatches(link["palette"])
                has_heat = st.checkbox("Record heat", value=link.get("heat") is not None, key=f"{key}_hasheat")
                edit_heat = st.slider("Heat", 0, 10, link.get("heat") or 5, key=f"{key}_heat", disabled=not has_heat)
                edit_house = st.text_input("House name", link.get("house_name") or "", key=f"{key}_house")
                edit_note = st.text_area("Note", link.get("note") or "", key=f"{key}_note")
                b1, b2 = st.columns(2)
                if b1.button("Save", key=f"{key}_save", type="primary"):
                    sf.save_sighting(
                        link["est_id"],
                        link["style_id"],
                        {
                            "heat": edit_heat if has_heat else None,
                            "house_name": edit_house.strip() or None,
                            "note": edit_note.strip() or None,
                        },
                    )
                    st.rerun()
                remove_help = (
                    "This link comes from the spot's salsa row, so only the field data is cleared."
                    if link.get("synced")
                    else "Deletes this spot–salsa link."
                )
                if b2.button("Remove sighting", key=f"{key}_remove", help=remove_help):
                    sf.remove_sighting(link)
                    st.rerun()

# ── Catalog ──────────────────────────────────────────────────────────────────
with tab_catalog:
    if styles:
        st.dataframe(
            pd.DataFrame(styles)[["name", "slug", "status", "family", "region", "origin"]],
            use_container_width=True,
            hide_index=True,
        )
    try:
        all_links = sf.list_sightings()
    except Exception:
        all_links = []

    for style in styles:
        with st.expander(("📝 " if style["status"] == "draft" else "") + style_label(style)):
            key = f"style_{style['id']}"
            c1, c2, c3, c4 = st.columns(4)
            name = c1.text_input("Name", style["name"], key=f"{key}_name")
            family = c2.selectbox("Family", sf.FAMILIES, sf.FAMILIES.index(style["family"]), key=f"{key}_family")
            region = c3.selectbox("Region", sf.REGIONS, sf.REGIONS.index(style["region"]), key=f"{key}_region")
            status = c4.selectbox(
                "Status", ["draft", "published"], ["draft", "published"].index(style["status"]), key=f"{key}_status"
            )
            tagline = st.text_input("Tagline", style.get("tagline") or "", key=f"{key}_tagline")
            origin = st.text_input("Origin (shown on the page)", style.get("origin") or "", key=f"{key}_origin")
            ingredients = st.text_area(
                "Ingredients, one per line", "\n".join(style.get("ingredients") or []), key=f"{key}_ingredients"
            )
            history = st.text_area("History", style.get("history") or "", height=180, key=f"{key}_history")

            heat_range = st.slider(
                "Typical heat", 0, 10, (style.get("heat_min") or 0, style.get("heat_max") or 0), key=f"{key}_heat"
            )
            score_cols = st.columns(len(sf.FLAVOUR_AXES))
            scores = {
                axis: col.slider(axis.capitalize(), 0, 10, style[axis], key=f"{key}_{axis}")
                for axis, col in zip(sf.FLAVOUR_AXES, score_cols)
            }

            st.markdown("**Palette** — the first colour is the definitive one")
            sighting_palettes = [
                link["palette"] for link in all_links if link["style_id"] == style["id"] and link.get("palette")
            ]
            derived = sf.pad_palette(sf.merge_palettes(sighting_palettes))
            if derived:
                st.caption(f"From {len(sighting_palettes)} field sighting(s):")
                swatches(derived)
                if st.button("Use these colours", key=f"{key}_derive"):
                    sf.update_style(style["id"], {"palette": derived})
                    st.rerun()
            pick_cols = st.columns(len(style["palette"]))
            palette = [
                col.color_picker(f"No. {i + 1}", c, key=f"{key}_pal_{i}_{c}").lower()
                for i, (col, c) in enumerate(zip(pick_cols, style["palette"]))
            ]

            if style.get("img_url"):
                st.image(style["img_url"], width=220)
            new_img = st.file_uploader("Photo", type=["jpg", "jpeg", "png", "heic", "heif"], key=f"{key}_img")
            img_credit = st.text_input("Photo credit", style.get("img_credit") or "", key=f"{key}_credit")

            if st.button("Save", key=f"{key}_save", type="primary"):
                data = {
                    "name": name.strip(),
                    "family": family,
                    "region": region,
                    "status": status,
                    "tagline": tagline.strip(),
                    "origin": origin.strip() or None,
                    "ingredients": [line.strip() for line in ingredients.splitlines() if line.strip()],
                    "history": history.strip() or None,
                    "heat_min": heat_range[0],
                    "heat_max": heat_range[1],
                    "palette": palette,
                    "img_credit": img_credit.strip() or None,
                    **scores,
                }
                try:
                    if new_img:
                        data["img_url"] = sf.upload_photo(sf.to_jpeg(sf.load_photo(new_img.getvalue())), "styles")
                    sf.update_style(style["id"], data)
                    st.success(f"Saved {name}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not save: {e}")
