import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Data Reconciliation Tool", layout="wide")

st.title("📊 Servtracker vs. Wellsky Reconciliation")

def clean_key(name):
    if pd.isna(name): return ""
    return re.sub(r'[^a-zA-Z]', '', str(name)).lower()

col1, col2 = st.columns(2)

with col1:
    serv_file = st.file_uploader("Upload Servtracker (Excel)", type=['xlsx'])
with col2:
    well_file = st.file_uploader("Upload Wellsky (XLS/CSV)", type=['xls', 'csv'])

if serv_file and well_file:
    try:
        # --- 1. PROCESS SERVTRACKER ---
        serv_xlsx = pd.ExcelFile(serv_file)
        sheet = "rptAccumulativeMonthly" if "rptAccumulativeMonthly" in serv_xlsx.sheet_names else serv_xlsx.sheet_names[0]
        df_serv = pd.read_excel(serv_file, sheet_name=sheet)
        
        serv_data = df_serv.iloc[5:].copy()
        # Column 0 = Name, Column 108 = Units
        serv_final = serv_data[[serv_data.columns[0], serv_data.columns[108]]].copy()
        serv_final.columns = ['Client Name', 'Servtracker']
        serv_final = serv_final[serv_final['Client Name'].str.contains(',', na=False)]
        serv_final['MatchKey'] = serv_final['Client Name'].apply(clean_key)
        serv_final['Servtracker'] = pd.to_numeric(serv_final['Servtracker'], errors='coerce').fillna(0)

        # --- 2. PROCESS WELLSKY (RAW TEXT SCANNER) ---
        # This bypasses "tokenizing" and "expected fields" errors by reading raw lines
        well_bytes = well_file.read()
        try:
            content = well_bytes.decode('utf-8')
        except:
            content = well_bytes.decode('latin1')
            
        lines = content.splitlines()
        wellsky_list = []
        current_key = None
        
        for line in lines:
            # Split by common delimiters (Tab, Comma, or multiple spaces)
            parts = re.split(r'\t|,| {2,}', line)
            parts = [p.strip().replace('"', '') for p in parts if p.strip()]

            # 1. Identify Client Header (Usually has a 9-digit or long ID)
            # We look for a line where a part looks like a long number (ID)
            for i, p in enumerate(parts):
                if p.isdigit() and len(p) >= 6:
                    # In Wellsky, name usually follows shortly after ID or is in the same row
                    # We'll grab the longest strings in the row as potential names
                    names = [x for x in parts if len(x) > 2 and not x.isdigit() and "Total" not in x]
                    if len(names) >= 2:
                        current_key = clean_key("".join(names[:2])) # Combines First/Last
                    break

            # 2. Identify Sub Total Row
            if "Sub Total" in line and current_key:
                # Find the numbers in this line
                nums = re.findall(r'\d+\.\d+|\d+', line)
                if nums:
                    # Usually the units are the first or last number in the Sub Total line
                    val = float(nums[-1]) # Grabbing the last number
                    wellsky_list.append({'MatchKey': current_key, 'Wellsky': val})
                    current_key = None # Reset for next client

        df_well_processed = pd.DataFrame(wellsky_list).groupby('MatchKey').sum().reset_index()

        # --- 3. MERGE ---
        final_report = pd.merge(serv_final, df_well_processed, on='MatchKey', how='left')
        final_report['Wellsky'] = final_report['Wellsky'].fillna(0)
        final_report['Difference'] = final_report['Servtracker'] - final_report['Wellsky']

        st.success("Analysis Complete!")
        st.dataframe(final_report[['Client Name', 'Servtracker', 'Wellsky', 'Difference']], use_container_width=True)
        
        csv = final_report.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Results", csv, "Comparison.csv", "text/csv")

    except Exception as e:
        st.error(f"Error: {e}")
