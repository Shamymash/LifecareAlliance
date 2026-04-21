import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Data Matcher", layout="wide")
st.title("📊 Servtracker vs. Wellsky Matcher")

def clean_key(text):
    """Turns 'Adams, Thomas ' into 'adamsthomas'"""
    if pd.isna(text): return ""
    return re.sub(r'[^a-z]', '', str(text).lower())

col1, col2 = st.columns(2)
with col1:
    serv_file = st.file_uploader("Upload Servtracker (Excel)", type=['xlsx'])
with col2:
    well_file = st.file_uploader("Upload Wellsky (XLS/CSV)", type=['xls', 'csv'])

if serv_file and well_file:
    try:
        # 1. PROCESS SERVTRACKER
        df_serv_raw = pd.read_excel(serv_file)
        serv_data = df_serv_raw.iloc[5:].copy()
        s_list = []
        for _, row in serv_data.iterrows():
            name = str(row.iloc[0])
            if "," in name and "Total" not in name:
                val = pd.to_numeric(row.iloc[108], errors='coerce') or 0
                if val > 0:
                    s_list.append({'Name': name, 'Key': clean_key(name), 'Serv': val})
        df_s = pd.DataFrame(s_list) if s_list else pd.DataFrame(columns=['Name', 'Key', 'Serv'])

        # 2. PROCESS WELLSKY (The "Table Search" Method)
        # We try to read the file as an HTML table (standard Wellsky format)
        try:
            # This handles the "Expected X fields" error by using an HTML parser
            tables = pd.read_html(well_file)
            well_df = tables[0]
        except:
            # Fallback for true CSVs
            well_file.seek(0)
            well_df = pd.read_csv(well_file, header=None, on_bad_lines='skip', encoding='latin1')

        w_list = []
        current_name = None
        
        # We iterate through the table to find the Name -> Sub Total relationship
        for _, row in well_df.iterrows():
            row_str = " ".join(row.astype(str))
            
            # A. Find Name: Looking for a row that has a comma and isn't a Total row
            # Usually column 1 has ID, columns 5/10 have Name
            if "," in row_str and "Total" not in row_str:
                # Look for the cell that actually contains the comma (the name)
                for cell in row:
                    cell_s = str(cell)
                    if "," in cell_s and len(cell_s) > 3:
                        current_name = cell_s
                        break
            
            # B. Find Units: Looking for a row that says "Total" or "Sub Total"
            if "Total" in row_str and current_name:
                # Find all numbers in this row
                nums = []
                for cell in row:
                    try:
                        n = float(str(cell).replace(',', ''))
                        if 0 < n < 500: nums.append(n)
                    except: continue
                
                if nums:
                    # Usually the unit total is the last numeric value on the subtotal line
                    w_list.append({'Key': clean_key(current_name), 'Well': nums[-1]})
                    current_name = None # Reset for next person

        df_w = pd.DataFrame(w_list).groupby('Key').sum().reset_index() if w_list else pd.DataFrame(columns=['Key', 'Well'])

        # 3. MERGE & RESULTS
        if not df_s.empty:
            final = pd.merge(df_s, df_w, on='Key', how='left').fillna(0)
            final['Diff'] = final['Serv'] - final['Well']
            
            # Success Message
            if not df_w.empty:
                st.success(f"Matched {len(df_w)} people from Wellsky!")
            else:
                st.warning("⚠️ Connected to files, but found 0 matching units in Wellsky. See Debug view below.")

            st.dataframe(final[['Name', 'Serv', 'Well', 'Diff']], use_container_width=True)
            
            # Download
            csv = final.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Results", csv, "Match_Results.csv", "text/csv")
            
            # DEBUG VIEW (Hidden by default)
            with st.expander("Debug: See Raw Wellsky Data"):
                st.write("This is what the script 'sees' in the Wellsky file:")
                st.write(well_df.head(20))
        else:
            st.error("No names found in Servtracker. Check if you uploaded the right file.")

    except Exception as e:
        st.error(f"Error: {e}")
