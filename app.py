import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Data Reconciliation Tool", layout="wide")
st.title("📊 Servtracker vs. Wellsky Reconciliation")

def make_key(text):
    """Standardizes names into a simple key (e.g., 'adamschr')"""
    if pd.isna(text) or text == "": return ""
    text = str(text).lower()
    # Remove all non-letters
    clean = re.sub(r'[^a-z]', '', text)
    return clean

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
        
        # Start data from row 5
        serv_data = df_serv.iloc[5:].copy()
        # Col 0: Name, Col 108: Units
        serv_final = serv_data[[serv_data.columns[0], serv_data.columns[108]]].copy()
        serv_final.columns = ['Client Name', 'Servtracker']
        serv_final = serv_final[serv_final['Client Name'].str.contains(',', na=False)]
        
        # Create the MatchKey
        serv_final['MatchKey'] = serv_final['Client Name'].apply(make_key)
        serv_final['Servtracker'] = pd.to_numeric(serv_final['Servtracker'], errors='coerce').fillna(0)

        # --- 2. PROCESS WELLSKY (The 'Deep Scan' Method) ---
        # We will try to read the file as HTML first (standard for Wellsky XLS)
        try:
            well_df = pd.read_html(well_file)[0]
        except:
            well_file.seek(0)
            well_df = pd.read_csv(well_file, header=None, sep=None, engine='python', encoding='latin1')

        well_records = []
        current_name_key = None
        
        # Iterate through every row in the Wellsky file
        for index, row in well_df.iterrows():
            row_list = [str(x) for x in row.values]
            row_text = " ".join(row_list)

            # A: Find a name row
            # Wellsky client lines usually have a long ID (6-10 digits) and a comma
            if re.search(r'\d{6,}', row_text) and "," in row_text:
                # Find the column that actually contains the comma (the name)
                for cell in row_list:
                    if "," in cell and not any(kw in cell for kw in ["Total", "Report", "Date"]):
                        current_name_key = make_key(cell)
                        break
            
            # B: Find a total row
            if "Total" in row_text and current_name_key:
                # Extract all numbers from the row
                nums = re.findall(r'(\d+\.\d+|\d+)', row_text)
                if nums:
                    # Usually the unit total is the last number on the 'Sub Total' line
                    try:
                        val = float(nums[-1])
                        # Filter out numbers that are too big to be units (like IDs or years)
                        if 0 < val < 1000:
                            well_records.append({'MatchKey': current_name_key, 'Wellsky': val})
                    except: pass

        if well_records:
            well_summary = pd.DataFrame(well_records).groupby('MatchKey').sum().reset_index()
        else:
            well_summary = pd.DataFrame(columns=['MatchKey', 'Wellsky'])

        # --- 3. MERGE ---
        # Join on MatchKey
        final = pd.merge(serv_final, well_summary, on='MatchKey', how='left')
        final['Wellsky'] = final['Wellsky'].fillna(0)
        final['Difference'] = final['Servtracker'] - final['Wellsky']

        # Sorting: People with differences first
        final = final.sort_values(by='Difference', ascending=False)

        st.success(f"Matched {len(well_summary)} unique clients from Wellsky.")
        st.dataframe(final[['Client Name', 'Servtracker', 'Wellsky', 'Difference']], use_container_width=True)
        
        # --- 4. DEBUG SECTION (In case of 0s) ---
        if len(well_summary) == 0:
            st.warning("⚠️ No data was found in the Wellsky file. This usually means the file format is protected or different than expected.")
            st.write("First 5 rows of Wellsky file for diagnosis:")
            st.write(well_df.head())

        csv = final.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Results", csv, "Reconciliation.csv", "text/csv")

    except Exception as e:
        st.error(f"Critical Error: {e}")
