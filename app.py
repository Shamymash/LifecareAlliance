import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Data Matcher", layout="wide")

st.title("📊 Servtracker vs. Wellsky Reconciliation")
st.markdown("Upload both files below to find the differences.")

def clean_key(name):
    if pd.isna(name): return ""
    # Strips everything but letters and lowers it for a perfect match
    return re.sub(r'[^a-zA-Z]', '', str(name)).lower()

col1, col2 = st.columns(2)

with col1:
    serv_file = st.file_uploader("Upload Servtracker (Excel)", type=['xlsx'])
with col2:
    well_file = st.file_uploader("Upload Wellsky (CSV/XLS)", type=['csv', 'xls'])

if serv_file and well_file:
    try:
        # 1. Process Servtracker
        df_serv_raw = pd.read_excel(serv_file, sheet_name=None)
        # Find the right sheet
        sheet_name = "rptAccumulativeMonthly" if "rptAccumulativeMonthly" in df_serv_raw else list(df_serv_raw.keys())[0]
        df_serv = df_serv_raw[sheet_name]
        
        # Extract name and total units (adjusting for row offset)
        serv_processed = df_serv.iloc[5:].copy() 
        serv_data = serv_processed[[serv_processed.columns[0], serv_processed.columns[108]]].copy()
        serv_data.columns = ['Client Name', 'Servtracker']
        serv_data = serv_data[serv_data['Client Name'].str.contains(',', na=False)]
        serv_data['MatchKey'] = serv_data['Client Name'].apply(clean_key)

        # 2. Process Wellsky
        # Using encoding='latin1' because Wellsky exports often have special characters
        df_well = pd.read_csv(well_file, header=None, encoding='latin1')
        
        wellsky_list = []
        current_key = None
        
        for _, row in df_well.iterrows():
            # If Column 1 looks like a long ID, it's a new client header
            if len(str(row[1])) > 5:
                current_key = clean_key(f"{row[5]}{row[10]}") # Last + First
            
            # If Column 17 has 'Sub Total', grab the units from Column 19
            if "Sub Total" in str(row[17]) and current_key:
                val = pd.to_numeric(row[19], errors='coerce') or 0
                wellsky_list.append({'MatchKey': current_key, 'Wellsky': val})
        
        df_well_final = pd.DataFrame(wellsky_list).groupby('MatchKey').sum().reset_index()

        # 3. Merge and Compare
        final = pd.merge(serv_data, df_well_final, on='MatchKey', how='left')
        final['Wellsky'] = final['Wellsky'].fillna(0)
        final['Difference'] = final['Servtracker'] - final['Wellsky']
        
        # Display Results
        st.success("Matching Complete!")
        output_df = final[['Client Name', 'Servtracker', 'Wellsky', 'Difference']]
        st.dataframe(output_df, use_container_width=True)

        # 4. Download Button
        csv = output_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Results as CSV", csv, "Reconciliation_Result.csv", "text/csv")

    except Exception as e:
        st.error(f"Error processing files: {e}")
