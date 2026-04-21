import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Data Matcher", layout="wide")
st.title("📊 Servtracker vs. Wellsky Matcher")

def clean_key(text):
    """Standardizes names: 'Adams, Thomas' -> 'adamsthomas'"""
    if pd.isna(text) or text == "": return ""
    return re.sub(r'[^a-z]', '', str(text).lower())

col1, col2 = st.columns(2)
with col1:
    serv_file = st.file_uploader("1. Upload Servtracker (Excel)", type=['xlsx'])
with col2:
    well_file = st.file_uploader("2. Upload Wellsky (XLS/CSV)", type=['xls', 'csv'])

if serv_file and well_file:
    try:
        # --- 1. PROCESS SERVTRACKER ---
        df_serv_raw = pd.read_excel(serv_file)
        # Servtracker data offset: Names usually in col 0, units in col 108
        serv_data = df_serv_raw.iloc[5:].copy()
        
        s_list = []
        for _, row in serv_data.iterrows():
            name = str(row.iloc[0])
            if "," in name and "Total" not in name:
                # Attempt to find units in column 108 (Standard for this report)
                try:
                    val = pd.to_numeric(row.iloc[108], errors='coerce') or 0
                    if val > 0:
                        s_list.append({'Name': name, 'Key': clean_key(name), 'Serv': val})
                except: continue
        
        df_s = pd.DataFrame(s_list) if s_list else pd.DataFrame(columns=['Name', 'Key', 'Serv'])

        # --- 2. PROCESS WELLSKY (The Binary-Safe Scanner) ---
        # We try to read the file as an Excel file first
        try:
            # engine='xlrd' is usually needed for old .xls files
            well_df = pd.read_excel(well_file)
        except:
            # Fallback for HTML-based or CSV Wellsky files
            try:
                well_file.seek(0)
                well_df = pd.read_html(well_file)[0]
            except:
                well_file.seek(0)
                well_df = pd.read_csv(well_file, header=None, on_bad_lines='skip', encoding='latin1')

        w_list = []
        current_name_key = None
        
        for _, row in well_df.iterrows():
            # Convert row to strings safely
            row_items = [str(x).strip() for x in row.values]
            row_str = " ".join(row_items)
            
            # A. Look for Client Name Row
            # Wellsky names are usually in a row with a long ID number (e.g. 1234567)
            if "," in row_str and any(len(x) >= 6 and x.isdigit() for x in row_items):
                for cell in row_items:
                    if "," in cell and len(cell) > 3 and "Total" not in cell:
                        current_name_key = clean_key(cell)
                        break
            
            # B. Look for Units (Sub Total)
            # This looks for any row that contains 'Total' and has the units
            if "total" in row_str.lower() and current_name_key:
                # Find all numbers in the row
                nums = []
                for cell in row_items:
                    # Remove non-numeric chars but keep decimals
                    clean_num = re.sub(r'[^\d.]', '', cell)
                    if clean_num and clean_num != '.':
                        try:
                            n = float(clean_num)
                            # Unit totals are usually small whole numbers (e.g. 2.0, 20.0)
                            if 0 < n < 500: nums.append(n)
                        except: continue
                
                if nums:
                    # In Wellsky, the units are typically the LAST number in the total row
                    w_list.append({'Key': current_name_key, 'Well': nums[-1]})
                    current_name_key = None # Reset for next client

        df_w = pd.DataFrame(w_list).groupby('Key').sum().reset_index() if w_list else pd.DataFrame(columns=['Key', 'Well'])

        # --- 3. MERGE & COMPARE ---
        if not df_s.empty:
            final = pd.merge(df_s, df_w, on='Key', how='left').fillna(0)
            final['Diff'] = final['Serv'] - final['Well']
            
            # Clean up display
            display_df = final[['Name', 'Serv', 'Well', 'Diff']].sort_values(by="Diff", ascending=False)
            
            if not df_w.empty:
                st.success(f"Matched {len(df_w)} clients from Wellsky!")
            else:
                st.warning("⚠️ Files read, but 0 matches found. See Debug below.")

            st.dataframe(display_df, use_container_width=True)
            
            # Download
            csv = display_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Reconciliation Report", csv, "Reconciliation.csv", "text/csv")
            
            # DEBUG
            with st.expander("Debug: Raw Wellsky Data"):
                st.write(well_df.head(20))
        else:
            st.error("Servtracker file appears empty or wrong format.")

    except Exception as e:
        st.error(f"Error: {e}")
