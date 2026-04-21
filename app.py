import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Data Matcher", layout="wide")
st.title("📊 Servtracker vs. Wellsky Matcher")

def get_strict_key(full_name):
    """
    Turns 'Adams, Thomas B' into 'adamsthomas'.
    Turns 'Adhikari, Dhan' into 'adhikaridhan'.
    """
    if pd.isna(full_name) or not full_name: return ""
    name_str = str(full_name).lower()
    if "," in name_str:
        last, first_part = name_str.split(",", 1)
        # Take only the first word of the first name (ignores middle initials)
        first = first_part.strip().split(" ")[0]
        return re.sub(r'[^a-z]', '', last + first)
    return re.sub(r'[^a-z]', '', name_str)

col1, col2 = st.columns(2)
with col1:
    serv_file = st.file_uploader("1. Upload Servtracker", type=['xlsx'])
with col2:
    well_file = st.file_uploader("2. Upload Wellsky", type=['xls', 'csv'])

if serv_file and well_file:
    try:
        # --- 1. SERVTRACKER ---
        df_s_raw = pd.read_excel(serv_file)
        s_list = []
        # Name is in Col 0, Units in Col 108
        for _, row in df_s_raw.iloc[5:].iterrows():
            name = str(row.iloc[0])
            if "," in name and "Total" not in name:
                val = pd.to_numeric(row.iloc[108], errors='coerce') or 0
                if val > 0:
                    s_list.append({
                        'Name': name, 
                        'Key': get_strict_key(name), 
                        'Serv': val
                    })
        df_s = pd.DataFrame(s_list)

        # --- 2. WELLSKY SCANNER ---
        try:
            well_df = pd.read_csv(well_file, header=None, encoding='latin1', on_bad_lines='skip')
        except:
            well_file.seek(0)
            well_df = pd.read_excel(well_file, header=None)

        w_list = []
        current_key = None

        for _, row in well_df.iterrows():
            # Convert row to list and skip the first 'index' column if it exists
            cells = [str(c).strip() for c in row.values]
            row_str = " ".join(cells)

            # A. Find the Person Row (Look for the long ID number)
            # In your file, ID is at index 2 or 3. We'll search for any long digit.
            ids = [c for c in cells if c.isdigit() and len(c) >= 7]
            if ids:
                # Find alphabetic cells for names. 
                # In your file: Last is index 6, First is index 11.
                try:
                    last = cells[6] if len(cells) > 6 else ""
                    first = cells[11] if len(cells) > 11 else ""
                    current_key = re.sub(r'[^a-z]', '', (last + first).lower())
                except: continue

            # B. Find the Units (Look for "Sub Total")
            if "Sub Total" in row_str and current_key:
                # Units are in the cell at index 20
                try:
                    units_val = cells[20] if len(cells) > 20 else "0"
                    units_clean = re.sub(r'[^\d.]', '', units_val)
                    if units_clean:
                        w_list.append({'Key': current_key, 'Well': float(units_clean)})
                except: pass
                # We don't reset current_key here in case there are multiple sub-totals

        # Group and sum Wellsky units
        df_w = pd.DataFrame(w_list).groupby('Key').sum().reset_index() if w_list else pd.DataFrame(columns=['Key', 'Well'])

        # --- 3. MERGE ---
        if not df_s.empty:
            final = pd.merge(df_s, df_w, on='Key', how='left').fillna(0)
            final['Diff'] = final['Serv'] - final['Well']
            
            st.success(f"Matched {len(final[final['Well'] > 0])} out of {len(df_s)} clients.")
            
            display_df = final[['Name', 'Serv', 'Well', 'Diff']].sort_values('Diff', ascending=False)
            st.dataframe(display_df, use_container_width=True)
            
            csv = display_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Final Report", csv, "Reconciliation_Report.csv", "text/csv")
        else:
            st.warning("No valid data found in Servtracker file.")

    except Exception as e:
        st.error(f"Error: {e}")
