import streamlit as st
import pandas as pd
import re
import io

st.set_page_config(page_title="Data Reconciliation Tool", layout="wide")

# --- CSS for better styling ---
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white; }
    </style>
    """, unsafe_allow_html=True)

st.title("📊 Servtracker vs. Wellsky Reconciliation")
st.info("Upload the Servtracker Excel file and the Wellsky .xls/CSV file to compare units.")

def clean_key(name):
    """Creates a standardized key: only lowercase letters, no spaces/dashes."""
    if pd.isna(name): return ""
    return re.sub(r'[^a-zA-Z]', '', str(name)).lower()

# --- File Uploaders ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Servtracker File")
    serv_file = st.file_uploader("Upload Accumulative Monthly (Excel)", type=['xlsx'])

with col2:
    st.subheader("2. Wellsky File")
    well_file = st.file_uploader("Upload Consumer Services List (.xls or .csv)", type=['xls', 'csv'])

if serv_file and well_file:
    try:
        with st.spinner('Processing data...'):
            # --- PROCESS SERVTRACKER ---
            # Load the Excel file and find the specific sheet
            serv_xlsx = pd.ExcelFile(serv_file)
            sheet_name = "rptAccumulativeMonthly" if "rptAccumulativeMonthly" in serv_xlsx.sheet_names else serv_xlsx.sheet_names[0]
            df_serv_raw = pd.read_excel(serv_file, sheet_name=sheet_name)
            
            # Start from row 5 where data usually begins
            serv_data = df_serv_raw.iloc[5:].copy()
            # Column 0 = Name, Column 108 = Totals (Servtracker column 'DG' usually)
            serv_final = serv_data[[serv_data.columns[0], serv_data.columns[108]]].copy()
            serv_final.columns = ['Client Name', 'Servtracker']
            
            # Filter for rows that actually have a client name (contain a comma)
            serv_final = serv_final[serv_final['Client Name'].str.contains(',', na=False)]
            serv_final['MatchKey'] = serv_final['Client Name'].apply(clean_key)
            serv_final['Servtracker'] = pd.to_numeric(serv_final['Servtracker'], errors='coerce').fillna(0)

            # --- PROCESS WELLSKY ---
            # Wellsky .xls is usually an HTML table. We try that first.
            try:
                # Read_html returns a list of tables
                well_tables = pd.read_html(well_file)
                df_well = well_tables[0]
            except Exception:
                # Fallback if it's a real CSV
                well_file.seek(0)
                df_well = pd.read_csv(well_file, header=None, sep=None, engine='python', encoding='latin1')

            wellsky_list = []
            current_key = None

            for i in range(len(df_well)):
                row = df_well.iloc[i]
                
                # Check for Client Header (usually has ID in index 1)
                id_val = str(row.iloc[1])
                if len(id_val) > 5 and id_val != "nan":
                    # Extract Last (index 5) and First (index 10)
                    last = str(row.iloc[5]) if len(row) > 5 else ""
                    first = str(row.iloc[10]) if len(row) > 10 else ""
                    current_key = clean_key(f"{last}{first}")

                # Check for 'Sub Total' row
                row_string = " ".join([str(x) for x in row.values])
                if "Sub Total" in row_string and current_key:
                    # Search row for the numeric unit value (usually column index 19)
                    # We look for the first number > 0 in that row
                    units = 0
                    for val in row.values:
                        try:
                            v = float(val)
                            if v > 0:
                                units = v
                                break
                        except: continue
                    wellsky_list.append({'MatchKey': current_key, 'Wellsky': units})

            df_well_processed = pd.DataFrame(wellsky_list).groupby('MatchKey').sum().reset_index()

            # --- MERGE & COMPARE ---
            final_report = pd.merge(serv_final, df_well_processed, on='MatchKey', how='left')
            final_report['Wellsky'] = final_report['Wellsky'].fillna(0)
            final_report['Difference'] = final_report['Servtracker'] - final_report['Wellsky']

            # Clean up display
            display_df = final_report[['Client Name', 'Servtracker', 'Wellsky', 'Difference']]
            
            st.success("Analysis Complete!")
            st.dataframe(display_df, use_container_width=True, height=500)

            # --- DOWNLOAD BUTTON ---
            csv = display_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Results as CSV",
                data=csv,
                file_name="Reconciliation_Report.csv",
                mime="text/csv",
            )

    except Exception as e:
        st.error(f"Error processing files: {e}")
        st.warning("Tip: Make sure the Wellsky file is the 'Consumer Services List Report' and Servtracker is the 'Accumulative Monthly' report.")
else:
    st.write("Waiting for both files to be uploaded...")
