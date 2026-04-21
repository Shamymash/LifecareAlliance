import streamlit as st
import pandas as pd
import re

st.set_index_config = {"page_title": "Data Matcher", "layout": "wide"}
st.title("📊 Servtracker vs. Wellsky Matcher")

def clean_key(text):
    if pd.isna(text): return ""
    return re.sub(r'[^a-z]', '', str(text).lower())

col1, col2 = st.columns(2)
with col1:
    serv_file = st.file_uploader("1. Upload Servtracker", type=['xlsx'])
with col2:
    well_file = st.file_uploader("2. Upload Wellsky", type=['xls', 'csv'])

if serv_file and well_file:
    try:
        # 1. SERVTRACKER
        df_s_raw = pd.read_excel(serv_file)
        s_data = df_s_raw.iloc[5:].copy()
        s_list = []
        for _, row in s_data.iterrows():
            name = str(row.iloc[0])
            if "," in name and "Total" not in name:
                val = pd.to_numeric(row.iloc[108], errors='coerce') or 0
                if val > 0:
                    s_list.append({'Name': name, 'Key': clean_key(name), 'Serv': val})
        df_s = pd.DataFrame(s_list)

        # 2. WELLSKY (Targeting specific layout found in your CSV)
        try:
            # Wellsky files often have different headers; read without them first
            well_df = pd.read_csv(well_file, header=None, encoding='latin1', on_bad_lines='skip')
        except:
            well_file.seek(0)
            well_df = pd.read_excel(well_file, header=None)

        w_list = []
        current_key = None

        for _, row in well_df.iterrows():
            # A. Find Name: ID is in Col 1, Last Name in Col 4, First Name in Col 9
            client_id = str(row.iloc[1])
            if client_id.isdigit() and len(client_id) > 5:
                last_name = str(row.iloc[4])
                first_name = str(row.iloc[9])
                current_key = clean_key(last_name + first_name)

            # B. Find Sub Total: It's in the row where Col 17 says 'Sub Total:'
            # The actual units are in Col 19
            row_text = str(row.iloc[17])
            if "Sub Total" in row_text and current_key:
                try:
                    units = float(str(row.iloc[19]).replace(',', ''))
                    w_list.append({'Key': current_key, 'Well': units})
                    current_key = None 
                except: continue

        df_w = pd.DataFrame(w_list).groupby('Key').sum().reset_index() if w_list else pd.DataFrame(columns=['Key', 'Well'])

        # 3. MERGE
        if not df_s.empty:
            final = pd.merge(df_s, df_w, on='Key', how='left').fillna(0)
            final['Diff'] = final['Serv'] - final['Well']
            
            st.success(f"Successfully matched {len(df_w)} clients from Wellsky.")
            st.dataframe(final[['Name', 'Serv', 'Well', 'Diff']], use_container_width=True)
            
            csv = final.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Results", csv, "Match_Results.csv", "text/csv")
        
    except Exception as e:
        st.error(f"Error: {e}")
