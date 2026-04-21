import streamlit as st
import pandas as pd
import re
import io

st.set_page_config(page_title="Data Matcher", layout="wide")
st.title("📊 Servtracker vs. Wellsky Matcher")

def clean_key(text):
    """Turns 'Adams, Thomas ' into 'adamsthomas'"""
    if pd.isna(text): return ""
    return re.sub(r'[^a-z]', '', str(text).lower())

def extract_number(text):
    """Finds the last number in a line (the total)."""
    nums = re.findall(r'(\d+\.\d+|\d+)', str(text).replace(',', ''))
    return float(nums[-1]) if nums else 0.0

col1, col2 = st.columns(2)
with col1:
    serv_file = st.file_uploader("Upload Servtracker (Excel)", type=['xlsx'])
with col2:
    well_file = st.file_uploader("Upload Wellsky (XLS/CSV)", type=['xls', 'csv'])

if serv_file and well_file:
    try:
        # 1. PROCESS SERVTRACKER
        serv_df = pd.read_excel(serv_file)
        # Search for the row containing 'Name' and 'Totals'
        serv_data = serv_df.iloc[5:].copy() # Standard offset
        # Assume Col 0 is Name, Col 108 is Units
        s_results = []
        for _, row in serv_data.iterrows():
            name = str(row.iloc[0])
            if "," in name and not "Total" in name:
                units = pd.to_numeric(row.iloc[108], errors='coerce') or 0
                s_results.append({'Name': name, 'Key': clean_key(name), 'Serv': units})
        df_s = pd.DataFrame(s_results)

        # 2. PROCESS WELLSKY (The 'Scanner' Method)
        # Read file as raw text to avoid formatting errors
        raw_bytes = well_file.read()
        try:
            text = raw_bytes.decode('utf-8')
        except:
            text = raw_bytes.decode('latin1')
        
        # Strip out HTML tags (Wellsky XLS files are usually HTML)
        clean_text = re.sub(r'<[^>]+>', ' ', text)
        lines = clean_text.splitlines()
        
        well_data = []
        current_key = None
        
        for line in lines:
            line = line.strip()
            if not line: continue

            # A. Find a Name (Look for a long ID number + a comma)
            if re.search(r'\d{5,}', line) and "," in line:
                # Get the name (text around the comma)
                name_match = re.search(r'([A-Za-z\s\'-]+,\s*[A-Za-z\s\'-]+)', line)
                if name_match:
                    current_key = clean_key(name_match.group(1))
            
            # B. Find a Total (Look for 'Total' or 'Sub Total' near a name)
            if ("total" in line.lower()) and current_key:
                val = extract_number(line)
                if val > 0 and val < 1000: # Sanity check
                    well_data.append({'Key': current_key, 'Well': val})
                    current_key = None # Found it, reset for next person

        df_w = pd.DataFrame(well_data).groupby('Key').sum().reset_index()

        # 3. MERGE
        if not df_w.empty:
            final = pd.merge(df_s, df_w, on='Key', how='left').fillna(0)
            final['Diff'] = final['Serv'] - final['Well']
            
            st.success(f"Matched {len(df_w)} people from Wellsky!")
            st.dataframe(final[['Name', 'Serv', 'Well', 'Diff']], use_container_width=True)
            
            csv = final[['Name', 'Serv', 'Well', 'Diff']].to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Results", csv, "Match_Results.csv", "text/csv")
        else:
            st.error("Could not find any data in the Wellsky file. Check if it's the 'Consumer Services List' report.")

    except Exception as e:
        st.error(f"Error: {e}")
