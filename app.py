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
        serv_final = serv_data[[serv_data.columns[0], serv_data.columns[108]]].copy()
        serv_final.columns = ['Client Name', 'Servtracker']
        serv_final = serv_final[serv_final['Client Name'].str.contains(',', na=False)]
        serv_final['MatchKey'] = serv_final['Client Name'].apply(clean_key)
        serv_final['Servtracker'] = pd.to_numeric(serv_final['Servtracker'], errors='coerce').fillna(0)

        # --- 2. PROCESS WELLSKY (Line-by-Line Logic) ---
        well_bytes = well_file.read()
        try:
            content = well_bytes.decode('utf-8')
        except:
            content = well_bytes.decode('latin1')
            
        lines = content.splitlines()
        wellsky_list = []
        current_client_key = None
        
        for line in lines:
            # Skip empty lines
            if not line.strip(): continue
            
            # Use a regex to see if this is a Client Header row 
            # (Looking for the ID pattern like "1234567")
            if re.search(r'\d{6,}', line) and "," in line:
                # Extract the name part (usually everything between the ID and the next comma)
                # This is a safe way to grab "LastName, FirstName"
                name_match = re.search(r'([A-Za-z\s-]+,\s*[A-Za-z\s-]+)', line)
                if name_match:
                    current_client_key = clean_key(name_match.group(1))

            # Look for the Sub Total line to grab the units
            if "Sub Total" in line and current_client_key:
                # Extract the last number in the line (the total units)
                nums = re.findall(r'(\d+\.?\d*)', line)
                if nums:
                    unit_val = float(nums[-1])
                    wellsky_list.append({'MatchKey': current_client_key, 'Wellsky': unit_val})
                    # We keep the key until we find a new client or a subtotal

        # Create the Wellsky DataFrame
        if wellsky_list:
            df_well_processed = pd.DataFrame(wellsky_list).groupby('MatchKey').sum().reset_index()
        else:
            # Create an empty DF with the correct columns to avoid the 'MatchKey' error
            df_well_processed = pd.DataFrame(columns=['MatchKey', 'Wellsky'])

        # --- 3. MERGE ---
        final_report = pd.merge(serv_final, df_well_processed, on='MatchKey', how='left')
        final_report['Wellsky'] = final_report['Wellsky'].fillna(0)
        final_report['Difference'] = final_report['Servtracker'] - final_report['Wellsky']

        st.success(f"Matched {len(df_well_processed)} clients from Wellsky.")
        st.dataframe(final_report[['Client Name', 'Servtracker', 'Wellsky', 'Difference']], use_container_width=True)
        
        csv = final_report.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Results", csv, "Comparison.csv", "text/csv")

    except Exception as e:
        st.error(f"Error: {e}")
