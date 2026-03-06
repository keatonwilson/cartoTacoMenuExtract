import streamlit as st
import pandas as pd
from src.spec_tables import (
    list_item_specs, create_item_spec, update_item_spec, delete_item_spec,
    list_protein_specs, create_protein_spec, update_protein_spec, delete_protein_spec,
    upload_spec_image,
)

st.set_page_config(page_title="Spec Tables", page_icon="📖", layout="wide")
st.title("📖 Spec Tables")

tab_item, tab_protein = st.tabs(["Item Specs", "Protein Specs"])


def _description_button(name: str, origin: str, spec_type: str, key_prefix: str):
    """Render a Generate Descriptions button and populate session state."""
    if st.button("✨ Generate Descriptions", key=f"{key_prefix}_gen"):
        with st.spinner("Generating descriptions with Claude..."):
            try:
                from src.description_gen import generate_spec_descriptions
                short, long = generate_spec_descriptions(name, origin, spec_type)
                st.session_state[f"{key_prefix}_short"] = short
                st.session_state[f"{key_prefix}_long"] = long
                st.rerun()
            except Exception as e:
                st.error(f"Generation failed: {e}")


# --- Item Specs ---
with tab_item:
    items = list_item_specs()

    if items:
        df = pd.DataFrame(items)[["id", "name", "short_descrip", "origin"]]
        st.dataframe(df, use_container_width=True, hide_index=True)

    # Add New
    with st.expander("➕ Add New Item Spec"):
        new_name = st.text_input("Name", key="new_item_name")
        new_origin = st.text_input("Origin", key="new_item_origin")
        _description_button(new_name, new_origin, "item", "new_item")
        new_short = st.text_area("Short Description", key="new_item_short")
        new_long = st.text_area("Long Description", key="new_item_long")
        new_img = st.file_uploader("Image", type=["jpg", "jpeg", "png"], key="new_item_img")

        if st.button("Create Item Spec", type="primary", key="create_item"):
            if not new_name:
                st.error("Name is required.")
            else:
                data = {
                    "name": new_name,
                    "short_descrip": new_short or None,
                    "long_descrip": new_long or None,
                    "origin": new_origin or None,
                }
                if new_img:
                    data["img_url"] = upload_spec_image(new_img.getvalue(), new_img.name)
                create_item_spec(data)
                st.success(f"Created '{new_name}'!")
                st.rerun()

    # Edit/Delete
    for item in items:
        with st.expander(f"✏️ {item['name']} (ID: {item['id']})"):
            key_pfx = f"item_{item['id']}"
            edit_name = st.text_input("Name", item["name"], key=f"{key_pfx}_name")
            edit_origin = st.text_input("Origin", item.get("origin") or "", key=f"{key_pfx}_origin")
            _description_button(edit_name, edit_origin, "item", key_pfx)
            edit_short = st.text_area(
                "Short Description", item.get("short_descrip") or "", key=f"{key_pfx}_short"
            )
            edit_long = st.text_area(
                "Long Description", item.get("long_descrip") or "", key=f"{key_pfx}_long"
            )
            if item.get("img_url"):
                st.image(item["img_url"], width=200)
            edit_img = st.file_uploader("Replace Image", type=["jpg", "jpeg", "png"], key=f"{key_pfx}_img")

            c1, c2 = st.columns(2)
            if c1.button("💾 Save", key=f"{key_pfx}_save"):
                updates = {
                    "name": edit_name,
                    "short_descrip": edit_short or None,
                    "long_descrip": edit_long or None,
                    "origin": edit_origin or None,
                }
                if edit_img:
                    updates["img_url"] = upload_spec_image(edit_img.getvalue(), edit_img.name)
                update_item_spec(item["id"], updates)
                st.success("Saved!")
                st.rerun()
            if c2.button("🗑️ Delete", key=f"{key_pfx}_del"):
                delete_item_spec(item["id"])
                st.warning(f"Deleted '{item['name']}'.")
                st.rerun()


# --- Protein Specs ---
with tab_protein:
    proteins = list_protein_specs()

    if proteins:
        df = pd.DataFrame(proteins)[["id", "name", "short_descrip", "origin"]]
        st.dataframe(df, use_container_width=True, hide_index=True)

    # Add New
    with st.expander("➕ Add New Protein Spec"):
        new_pname = st.text_input("Name", key="new_prot_name")
        new_porigin = st.text_input("Origin", key="new_prot_origin")
        _description_button(new_pname, new_porigin, "protein", "new_prot")
        new_pshort = st.text_area("Short Description", key="new_prot_short")
        new_plong = st.text_area("Long Description", key="new_prot_long")

        if st.button("Create Protein Spec", type="primary", key="create_prot"):
            if not new_pname:
                st.error("Name is required.")
            else:
                data = {
                    "name": new_pname,
                    "short_descrip": new_pshort or None,
                    "long_descrip": new_plong or None,
                    "origin": new_porigin or None,
                }
                create_protein_spec(data)
                st.success(f"Created '{new_pname}'!")
                st.rerun()

    # Edit/Delete
    for prot in proteins:
        with st.expander(f"✏️ {prot['name']} (ID: {prot['id']})"):
            key_pfx = f"prot_{prot['id']}"
            edit_pname = st.text_input("Name", prot["name"], key=f"{key_pfx}_name")
            edit_porigin = st.text_input("Origin", prot.get("origin") or "", key=f"{key_pfx}_origin")
            _description_button(edit_pname, edit_porigin, "protein", key_pfx)
            edit_pshort = st.text_area(
                "Short Description", prot.get("short_descrip") or "", key=f"{key_pfx}_short"
            )
            edit_plong = st.text_area(
                "Long Description", prot.get("long_descrip") or "", key=f"{key_pfx}_long"
            )

            c1, c2 = st.columns(2)
            if c1.button("💾 Save", key=f"{key_pfx}_save"):
                updates = {
                    "name": edit_pname,
                    "short_descrip": edit_pshort or None,
                    "long_descrip": edit_plong or None,
                    "origin": edit_porigin or None,
                }
                update_protein_spec(prot["id"], updates)
                st.success("Saved!")
                st.rerun()
            if c2.button("🗑️ Delete", key=f"{key_pfx}_del"):
                delete_protein_spec(prot["id"])
                st.warning(f"Deleted '{prot['name']}'.")
                st.rerun()
