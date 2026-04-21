import streamlit as st
import pandas as pd
import re
from bs4 import BeautifulSoup

st.set_page_config(page_title="Data Matcher", layout="wide")
st.title("📊 Servtracker vs. Wellsky Matcher")

def clean_key(text):
    """Standardizes names: 'Adams, Thomas' -> 'adamsthomas'"""
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
        # Standard Servtracker offset: names start around row 5
        serv_data = df_serv_raw.iloc[5:].copy()
        
        s_list = []
        for _, row in serv_data.iterrows():
            name = str(row.iloc[0])
            if "," in name and "Total" not in name:
                # Column 108 is the typical Servtracker 'Grand Total' column
                val = pd.to_numeric(row.iloc[108], errors='coerce') or 0
                if val > 0:
                    s_list.append({'Name': name, 'Key': clean_key(name), 'Serv': val})
        
        df_s = pd.DataFrame(s_list) if s_list else pd.DataFrame(columns=['Name', 'Key', 'Serv'])

        # 2. PROCESS WELLSKY (The HTML-Aware Scanner)
        well_content = well_file.read()
        # Use BeautifulSoup to strip HTML tags and find clean text
        soup = BeautifulSoup(well_content, "html.parser")
        text_content = soup.get_text(separator='|') # Use pipe as a delimiter
        lines = text_content.splitlines()
        
        w_list = []
        current_key = None
        
        for line in lines:
            # A. Identify a name (Looks for an ID number and a comma)
            if "," in line and re.search(r'\d{5,}', line):
                name_match = re.search(r'([A-Za-z\s\'-]+,\s*[A-Za-z\s\'-]+)', line)
                if name_match:
                    current_key = clean_key(name_match.group(1))

            # B. Identify the units (Look for "Total" and get the last number)
            if "total" in line.lower() and current_key:
                nums = re.findall(r'(\d+\.\d+|\d+)', line.replace(',', ''))
                if nums:
                    val = float(nums[-1])
                    if 0 < val < 1000: # Standard units filter
                        w_list.append({'Key': current_key, 'Well': val})
                        current_key = None # Reset for next client

        df_w = pd.DataFrame(w_list)
        if not df_w.empty:
            df_w = df_w.groupby('Key').sum().reset_index()
        else:
            df_w = pd.DataFrame(columns=['Key', 'Well'])

        # 3. MERGE (Safe Merge)
        if not df_s.empty:
            final = pd.merge(df_s, df_w, on='Key', how='left').fillna(0)
            final['Diff'] = final['Serv'] - final['Well']
            
            st.success(f"Matched {len(df_w)} people from Wellsky!")
            st.dataframe(final[['Name', 'Serv', 'Well', 'Diff']], use_container_width=True)
            
            csv = final.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Results", csv, "Match_Results.csv", "text/csv")
        else:
            st.warning("No client names found in Servtracker file. Check your file format.")

    except Exception as e:
        st.error(f"Error: {e}")

# IMPORTANT: You need to add 'beautifulsoup4' to your requirements.txt
