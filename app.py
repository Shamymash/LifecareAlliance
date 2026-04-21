import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Data Reconciliation Tool", layout="wide")
st.title("📊 Servtracker vs. Wellsky Reconciliation")

def clean_key(name):
    """Standardizes names: removes everything but letters and makes lowercase."""
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
        
        # Servtracker columns: 0 is Name, 108 is units
        serv_data = df_serv.iloc[5:].copy()
        serv_final = serv_data[[serv_data.columns[0], serv_data.columns[108]]].copy()
        serv_final.columns = ['Client Name', 'Servtracker']
        serv_final = serv_final[serv_final['Client Name'].str.contains(',', na=False)]
        serv_final['MatchKey'] = serv_final['Client Name'].apply(clean_key)
        serv_final['Servtracker'] = pd.to_numeric(serv_final['Servtracker'], errors='coerce').fillna(0)

        # --- 2. PROCESS WELLSKY (Robust Scanner) ---
        well_bytes = well_file.read()
        try:
            content = well_bytes.decode('utf-8')
        except:
            content = well_bytes.decode('latin1')
            
        lines = content.splitlines()
        wellsky_list = []
        current_name = None
        
        for line in lines:
            clean_line = line.strip()
            if not clean_line: continue
            
            # Look for a Client Name (Usually contains a comma and is near a long ID)
            # Example: "1234567, Doe, John" or "Doe, John"
            if "," in clean_line and any(char.isdigit() for char in clean_line):
                # Try to extract the name pattern "LastName, FirstName"
                match = re.search(r'([A-Za-z\s\'-]+,\s*[A-Za-z\s\'-]+)', clean_line)
                if match:
                    current_name = match.group(1)

            # Look for the units line (Look for "Total" or "Sub Total" case-insensitive)
            if ("total" in clean_line.lower()) and current_name:
                # Find all numbers (including decimals) in the line
                # Wellsky totals usually look like: "Sub Total: 20.00" or just "... 20"
                nums = re.findall(r'(\d+\.\d+|\d+)', clean_line)
                if nums:
                    # We take the number that looks most like a 'unit' count
                    # Usually it's the last number on the Sub Total line
                    unit_val = float(nums[-1])
                    
                    # Only count it if it's a reasonable number (not a year or ID)
                    if unit_val < 500: 
                        wellsky_list.append({
                            'MatchKey': clean_key(current_name),
                            'Wellsky': unit_val
                        })
                        # Optional: Clear name after finding total to prevent double-counting
                        current_name = None

        if wellsky_list:
            df_well_processed = pd.DataFrame(wellsky_list).groupby('MatchKey').sum().reset_index()
        else:
            df_well_processed = pd.DataFrame(columns=['MatchKey', 'Wellsky'])

        # --- 3. MERGE & RESULTS ---
        final_report = pd.merge(serv_final, df_well_processed, on='MatchKey', how='left')
        final_report['Wellsky'] = final_report['Wellsky'].fillna(0)
        final_report['Difference'] = final_report['Servtracker'] - final_report['Wellsky']

        # Sort by those with the biggest differences
        final_report = final_report.sort_values(by="Difference", ascending=False)

        st.success(f"Success! Found {len(df_well_processed)} clients in Wellsky.")
        
        # Display the table
        st.dataframe(final_report[['Client Name', 'Servtracker', 'Wellsky', 'Difference']], use_container_width=True)
        
        # Download Button
        csv = final_report[['Client Name', 'Servtracker', 'Wellsky', 'Difference']].to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Final Report", csv, "Reconciliation_Report.csv", "text/csv")

    except Exception as e:
        st.error(f"An error occurred: {e}")
