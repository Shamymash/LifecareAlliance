import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Data Reconciliation Tool", layout="wide")
st.title("📊 Servtracker vs. Wellsky Reconciliation")

def make_key(text):
    """Standardizes names: 'Adams, Thomas' -> 'adamsthomas'"""
    if pd.isna(text) or text == "": return ""
    return re.sub(r'[^a-z]', '', str(text).lower())

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
        
        # Servtracker data usually starts at Row 5
        serv_data = df_serv.iloc[5:].copy()
        serv_final = serv_data[[serv_data.columns[0], serv_data.columns[108]]].copy()
        serv_final.columns = ['Client Name', 'Servtracker']
        
        # Filter for rows that have a comma (actual people)
        serv_final = serv_final[serv_final['Client Name'].str.contains(',', na=False)]
        serv_final['MatchKey'] = serv_final['Client Name'].apply(make_key)
        serv_final['Servtracker'] = pd.to_numeric(serv_final['Servtracker'], errors='coerce').fillna(0)

        # --- 2. PROCESS WELLSKY (Line-by-Line "Text Scanner") ---
        # We read the file as raw text to avoid "Expected X fields" errors
        well_bytes = well_file.read()
        try:
            content = well_bytes.decode('utf-8')
        except:
            content = well_bytes.decode('latin1')
            
        lines = content.splitlines()
        well_records = []
        current_name_key = None
        
        for line in lines:
            # Skip empty lines
            if not line.strip(): continue
            
            # A: Identify the Client Name Row
            # Wellsky lines with names usually have a comma and a Client ID (long number)
            # Example: "123456, Adams, Thomas"
            if "," in line and re.search(r'\d{5,}', line):
                # Clean the line and find the part that looks like "LastName, FirstName"
                # We strip out HTML tags if it's an HTML-Excel export
                clean_line = re.sub('<[^<]+?>', '', line) 
                parts = clean_line.split(',')
                if len(parts) >= 2:
                    # Look for the segment that contains the name
                    for i in range(len(parts)-1):
                        potential_name = parts[i] + parts[i+1]
                        if any(c.isalpha() for c in potential_name):
                            current_name_key = make_key(potential_name)
                            break

            # B: Identify the Units Row
            # Look for 'Total' and grab the numbers. 
            # Wellsky subtotal lines are often near the name.
            if "Total" in line and current_name_key:
                # Remove HTML tags and extra characters
                clean_line = re.sub('<[^<]+?>', '', line).replace(',', '')
                # Find all numbers (including decimals)
                nums = re.findall(r'(\d+\.\d+|\d+)', clean_line)
                if nums:
                    try:
                        val = float(nums[-1]) # Usually the last number is the total
                        if 0 < val < 500: # Sanity check to avoid IDs or Dates
                            well_records.append({'MatchKey': current_name_key, 'Wellsky': val})
                            # We reset the name key after finding the total for that person
                            current_name_key = None 
                    except: pass

        # Convert the list of found data into a table
        if well_records:
            well_summary = pd.DataFrame(well_records).groupby('MatchKey').sum().reset_index()
        else:
            well_summary = pd.DataFrame(columns=['MatchKey', 'Wellsky'])

        # --- 3. MERGE & SHOW RESULTS ---
        final = pd.merge(serv_final, well_summary, on='MatchKey', how='left')
        final['Wellsky'] = final['Wellsky'].fillna(0)
        final['Difference'] = final['Servtracker'] - final['Wellsky']

        # Filter out the "Grand Total" rows if they were caught by mistake
        final = final[~final['Client Name'].str.contains('Total', case=False, na=False)]
        
        st.success(f"Matched {len(well_summary)} clients from Wellsky.")
        st.dataframe(final[['Client Name', 'Servtracker', 'Wellsky', 'Difference']], use_container_width=True)
        
        csv = final[['Client Name', 'Servtracker', 'Wellsky', 'Difference']].to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Reconciliation Report", csv, "Reconciliation.csv", "text/csv")

    except Exception as e:
        st.error(f"Something went wrong: {e}")
