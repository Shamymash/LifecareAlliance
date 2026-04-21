import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Data Matcher", layout="wide")
st.title("📊 Servtracker vs. Wellsky Matcher")

def clean_key(text):
    """Removes all non-letters and makes lowercase: 'Adams, Thomas B.' -> 'adamsthomasb'"""
    if pd.isna(text): return ""
    return re.sub(r'[^a-z]', '', str(text).lower())

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
        # Servtracker: Name in Col 0, Totals in Col 108
        for _, row in df_s_raw.iloc[5:].iterrows():
            name = str(row.iloc[0])
            if "," in name and "Total" not in name:
                val = pd.to_numeric(row.iloc[108], errors='coerce') or 0
                if val > 0:
                    s_list.append({'Name': name, 'Key': clean_key(name), 'Serv': val})
        df_s = pd.DataFrame(s_list)

        # --- 2. WELLSKY (Direct Column Mapping) ---
        # Based on your export: ID=Col2, Last=Col5, First=Col10, MI=Col19, Units=Col20
        try:
            well_df = pd.read_csv(well_file, header=None, encoding='latin1', on_bad_lines='skip')
        except:
            well_file.seek(0)
            well_df = pd.read_excel(well_file, header=None)

        w_list = []
        current_key = None

        for _, row in well_df.iterrows():
            row_vals = [str(x).strip() for x in row.values]
            
            # A. Find the Name Row (Look for the 9-digit ID in Column 2)
            client_id = row_vals[2] if len(row_vals) > 2 else ""
            if client_id.isdigit() and len(client_id) >= 7:
                last_name = row_vals[5] if len(row_vals) > 5 else ""
                first_name = row_vals[10] if len(row_vals) > 10 else ""
                mi = row_vals[19] if len(row_vals) > 19 else ""
                # Create a key using all name parts found on this row
                current_key = clean_key(last_name + first_name + mi)

            # B. Find the Sub Total Row (Look for "Sub Total" in Column 18)
            row_text = row_vals[18] if len(row_vals) > 18 else ""
            if "Sub Total" in row_text and current_key:
                try:
                    # Units are in Column 20
                    units_val = re.sub(r'[^\d.]', '', row_vals[20])
                    if units_val:
                        w_list.append({'Key': current_key, 'Well': float(units_val)})
                except: pass
                # Note: We DON'T reset current_key yet because some reports 
                # list multiple services under one name.

        # Group Wellsky by key to handle multiple service lines for one person
        df_w = pd.DataFrame(w_list).groupby('Key').sum().reset_index() if w_list else pd.DataFrame(columns=['Key', 'Well'])

        # --- 3. MERGE & COMPARE ---
        if not df_s.empty:
            # We use a 'contains' logic for the merge to handle partial name matches
            # But for simplicity and speed, a standard join on the cleaned key is best
            final = pd.merge(df_s, df_w, on='Key', how='left').fillna(0)
            
            # Second attempt: If 'Well' is still 0, try matching without the Middle Initial
            # (Matches 'adamsthomas' to 'adamsthomasb')
            for idx, row in final.iterrows():
                if row['Well'] == 0:
                    # Try a fuzzy lookup in the wellsky data
                    short_key = row['Key']
                    match = df_w[df_w['Key'].str.contains(short_key, na=False)]
                    if not match.empty:
                        final.at[idx, 'Well'] = match.iloc[0]['Well']

            final['Diff'] = final['Serv'] - final['Well']
            st.success(f"Successfully processed {len(df_s)} Servtracker clients and found matches for {len(df_w)} Wellsky entries.")
            
            display_df = final[['Name', 'Serv', 'Well', 'Diff']].sort_values('Diff', ascending=False)
            st.dataframe(display_df, use_container_width=True)
            
            csv = display_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Reconciliation.csv", csv, "Reconciliation.csv", "text/csv")
        else:
            st.error("Could not find names in Servtracker. Check if Col 0 has the names.")

    except Exception as e:
        st.error(f"Analysis Error: {e}")
