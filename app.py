import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Data Matcher", layout="wide")
st.title("📊 Servtracker vs. Wellsky Matcher")

def clean_key(text):
    if pd.isna(text) or text == "": return ""
    return re.sub(r'[^a-z]', '', str(text).lower())

col1, col2 = st.columns(2)
with col1:
    serv_file = st.file_uploader("1. Upload Servtracker", type=['xlsx'])
with col2:
    well_file = st.file_uploader("2. Upload Wellsky", type=['xls', 'csv'])

if serv_file and well_file:
    try:
        # --- 1. SERVTRACKER: Dynamic Column Search ---
        df_s_raw = pd.read_excel(serv_file)
        # Find the column that contains 'Totals' or has the units
        # We'll look for the first row that looks like data
        s_list = []
        for _, row in df_s_raw.iterrows():
            row_list = [str(x) for x in row.values]
            name = row_list[0]
            if "," in name and "Total" not in name:
                # Instead of index 108, find the LAST numeric value in the row
                nums = [pd.to_numeric(x, errors='coerce') for x in row.values if pd.notna(x)]
                valid_nums = [n for n in nums if n is not None and 0 < n < 500]
                if valid_nums:
                    s_list.append({'Name': name, 'Key': clean_key(name), 'Serv': valid_nums[-1]})
        df_s = pd.DataFrame(s_list)

        # --- 2. WELLSKY: Flexible Scanner ---
        try:
            # Try HTML first (common Wellsky format)
            well_df = pd.read_html(well_file)[0]
        except:
            well_file.seek(0)
            # Fallback to CSV/Excel
            try:
                well_df = pd.read_excel(well_file, header=None)
            except:
                well_file.seek(0)
                well_df = pd.read_csv(well_file, header=None, encoding='latin1', on_bad_lines='skip')

        w_list = []
        current_key = None

        for _, row in well_df.iterrows():
            row_items = [str(x).strip() for x in row.values]
            row_str = " ".join(row_items)

            # A. Find Name: Look for a row with an ID (digits) and text
            if any(x.isdigit() and len(x) > 5 for x in row_items):
                # Join any text parts that look like names (usually cols 4 and 9)
                text_parts = [x for x in row_items if x.isalpha() and len(x) > 1]
                if len(text_parts) >= 2:
                    current_key = clean_key("".join(text_parts[:3]))

            # B. Find Total: Look for 'Sub Total' or 'Total' and grab the number next to it
            if "total" in row_str.lower() and current_key:
                nums = []
                for x in row_items:
                    clean_n = re.sub(r'[^\d.]', '', x)
                    if clean_n and clean_n != '.':
                        try:
                            nums.append(float(clean_n))
                        except: continue
                if nums:
                    w_list.append({'Key': current_key, 'Well': nums[-1]})
                    current_key = None

        df_w = pd.DataFrame(w_list).groupby('Key').sum().reset_index() if w_list else pd.DataFrame(columns=['Key', 'Well'])

        # --- 3. MERGE ---
        if not df_s.empty:
            final = pd.merge(df_s, df_w, on='Key', how='left').fillna(0)
            final['Diff'] = final['Serv'] - final['Well']
            
            st.success(f"Matched {len(df_w)} clients.")
            st.dataframe(final[['Name', 'Serv', 'Well', 'Diff']].sort_values('Diff', ascending=False), use_container_width=True)
            
            csv = final.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Results", csv, "Match_Results.csv", "text/csv")
        
    except Exception as e:
        st.error(f"Error Details: {e}")
