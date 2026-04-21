import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Data Matcher", layout="wide")
st.title("📊 Servtracker vs. Wellsky Matcher")

def clean_key(text):
    """Strips everything but letters for matching: 'Adams, Thomas' -> 'adamsthomas'"""
    if pd.isna(text) or text == "": return ""
    # Only keep letters (remove spaces, commas, periods, etc.)
    return re.sub(r'[^a-z]', '', str(text).lower())

col1, col2 = st.columns(2)
with col1:
    serv_file = st.file_uploader("1. Upload Servtracker", type=['xlsx'])
with col2:
    well_file = st.file_uploader("2. Upload Wellsky", type=['xls', 'csv'])

if serv_file and well_file:
    try:
        # --- 1. PROCESS SERVTRACKER ---
        df_s_raw = pd.read_excel(serv_file)
        s_list = []
        # We look for the Name in Col 0 and Units in Col 108
        for _, row in df_s_raw.iloc[5:].iterrows():
            name = str(row.iloc[0])
            if "," in name and "Total" not in name:
                try:
                    # Servtracker totals are usually in Col 108 for this specific report
                    val = pd.to_numeric(row.iloc[108], errors='coerce') or 0
                    if val > 0:
                        s_list.append({'Name': name, 'Key': clean_key(name), 'Serv': val})
                except: continue
        df_s = pd.DataFrame(s_list)

        # --- 2. PROCESS WELLSKY (Updated with Exact Coordinates) ---
        try:
            # Wellsky exports usually read best with these settings
            well_df = pd.read_csv(well_file, header=None, encoding='latin1', on_bad_lines='skip')
        except:
            well_file.seek(0)
            well_df = pd.read_excel(well_file, header=None)

        w_list = []
        current_key = None

        for _, row in well_df.iterrows():
            # Convert row to list for easy indexing
            row_vals = [str(x).strip() for x in row.values]
            
            # A. Find the Name Row: Client ID is at Index 2
            # We look for a row where Index 2 is a numeric ID
            client_id = row_vals[2] if len(row_vals) > 2 else ""
            if client_id.isdigit() and len(client_id) >= 7:
                # Based on your file: Last Name is at Index 6, First Name is at Index 11
                last_name = row_vals[6] if len(row_vals) > 6 else ""
                first_name = row_vals[11] if len(row_vals) > 11 else ""
                current_key = clean_key(last_name + first_name)

            # B. Find the Units: "Sub Total:" text is at Index 18, Units are at Index 20
            row_text = row_vals[18] if len(row_vals) > 18 else ""
            if "Sub Total:" in row_text and current_key:
                try:
                    units_raw = row_vals[20] if len(row_vals) > 20 else "0"
                    units_clean = re.sub(r'[^\d.]', '', units_raw)
                    if units_clean:
                        w_list.append({'Key': current_key, 'Well': float(units_clean)})
                except: pass

        # Group Wellsky by key (in case a person has multiple service types)
        if w_list:
            df_w = pd.DataFrame(w_list).groupby('Key').sum().reset_index()
        else:
            df_w = pd.DataFrame(columns=['Key', 'Well'])

        # --- 3. MERGE & COMPARE ---
        if not df_s.empty:
            final = pd.merge(df_s, df_w, on='Key', how='left').fillna(0)
            final['Diff'] = final['Serv'] - final['Well']
            
            # Display results
            st.success(f"Processed {len(df_s)} Servtracker records and found {len(df_w)} matches in Wellsky.")
            
            # Sort by differences (discrepancies first)
            display_df = final[['Name', 'Serv', 'Well', 'Diff']].sort_values(by="Diff", ascending=False)
            st.dataframe(display_df, use_container_width=True)
            
            # Download
            csv = display_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Reconciliation Report", csv, "Reconciliation.csv", "text/csv")
            
        else:
            st.error("No names found in Servtracker file. Ensure column 0 contains 'Last, First' names.")

    except Exception as e:
        st.error(f"Error during processing: {e}")
