import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Data Matcher", layout="wide")
st.title("📊 Servtracker vs. Wellsky Matcher")

def clean_key(text):
    """Turns 'Adams, Thomas B' into 'adamsthomas'"""
    if pd.isna(text) or not text: return ""
    text = str(text).lower()
    # If there is a comma, we assume 'Last, First'
    if "," in text:
        parts = text.split(",")
        last = re.sub(r'[^a-z]', '', parts[0])
        first = re.sub(r'[^a-z]', '', parts[1].strip().split()[0]) # First word only
        return last + first
    # Otherwise just strip everything non-alpha
    return re.sub(r'[^a-z]', '', text)

col1, col2 = st.columns(2)
with col1:
    serv_file = st.file_uploader("1. Upload Servtracker", type=['xlsx'])
with col2:
    well_file = st.file_uploader("2. Upload Wellsky", type=['xls', 'xlsx', 'csv'])

if serv_file and well_file:
    try:
        # --- 1. SERVTRACKER ---
        df_s_raw = pd.read_excel(serv_file)
        s_list = []
        for _, row in df_s_raw.iloc[5:].iterrows():
            name = str(row.iloc[0]).strip()
            if "," in name and "total" not in name.lower():
                val = pd.to_numeric(row.iloc[108], errors='coerce') or 0
                if val > 0:
                    s_list.append({'Name': name, 'Key': clean_key(name), 'Serv': val})
        df_s = pd.DataFrame(s_list)

        # --- 2. WELLSKY ---
        try:
            well_df = pd.read_csv(well_file, header=None, encoding='latin1')
        except:
            well_file.seek(0)
            well_df = pd.read_excel(well_file, header=None)

        w_list = []
        current_key = None

        for _, row in well_df.iterrows():
            row_vals = [str(x).strip() for x in row.values]
            row_text = " ".join(row_vals).lower()

            # A. Look for Name: Check if there's a 7-9 digit ID in the row
            ids = [c for c in row_vals if c.isdigit() and len(c) >= 7]
            if ids:
                # Based on your file: Last Name is at Index 6, First Name is at Index 11
                last = row_vals[6] if len(row_vals) > 6 else ""
                first = row_vals[11] if len(row_vals) > 11 else ""
                if last and first:
                    current_key = re.sub(r'[^a-z]', '', (last + first).lower())

            # B. Look for Units: "Sub Total" is in Column 18, Units are in Column 20
            if "sub total" in row_text and current_key:
                try:
                    # In your exact file, the units are 2 columns over from "Sub Total"
                    units_cell = row_vals[20] if len(row_vals) > 20 else ""
                    units_clean = re.sub(r'[^\d.]', '', units_cell)
                    if units_clean:
                        w_list.append({'Key': current_key, 'Well': float(units_clean)})
                except: pass

        df_w = pd.DataFrame(w_list).groupby('Key').sum().reset_index() if w_list else pd.DataFrame(columns=['Key', 'Well'])

        # --- 3. RECONCILE ---
        if not df_s.empty:
            final = pd.merge(df_s, df_w, on='Key', how='left').fillna(0)
            final['Diff'] = final['Serv'] - final['Well']
            
            matches = len(final[final['Well'] > 0])
            st.success(f"Matched {matches} out of {len(df_s)} clients.")
            
            # Show the ones with differences first
            st.dataframe(final[['Name', 'Serv', 'Well', 'Diff']].sort_values('Diff', ascending=False), use_container_width=True)
            
            csv = final.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Report", csv, "Reconciliation.csv", "text/csv")
        else:
            st.error("Servtracker file appears empty or formatted incorrectly.")

    except Exception as e:
        st.error(f"Error: {e}")
