import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Data Matcher", layout="wide")
st.title("📊 Servtracker vs. Wellsky Matcher")

def clean_key(text):
    """Turns 'Adams, Thomas ' into 'adamsthomas'"""
    if pd.isna(text): return ""
    # Standardize: lowercase and remove anything that isn't a letter
    return re.sub(r'[^a-z]', '', str(text).lower())

col1, col2 = st.columns(2)
with col1:
    serv_file = st.file_uploader("1. Upload Servtracker (Excel)", type=['xlsx'])
with col2:
    well_file = st.file_uploader("2. Upload Wellsky (XLS/CSV)", type=['xls', 'csv'])

if serv_file and well_file:
    try:
        # --- 1. PROCESS SERVTRACKER ---
        df_serv_raw = pd.read_excel(serv_file)
        # Assuming names start after row 5. 
        # Column 0 = Names, Column 108 = Units (Servtracker 'Totals')
        serv_data = df_serv_raw.iloc[5:].copy()
        
        s_list = []
        for _, row in serv_data.iterrows():
            name = str(row.iloc[0])
            if "," in name and "Total" not in name:
                # Column 108 is the typical location for totals in this report
                val = pd.to_numeric(row.iloc[108], errors='coerce') or 0
                if val > 0:
                    s_list.append({'Name': name, 'Key': clean_key(name), 'Serv': val})
        
        df_s = pd.DataFrame(s_list) if s_list else pd.DataFrame(columns=['Name', 'Key', 'Serv'])

        # --- 2. PROCESS WELLSKY (Robust Table Search) ---
        try:
            # Wellsky files are usually HTML tables disguised as .xls
            tables = pd.read_html(well_file)
            well_df = tables[0]
        except:
            # Fallback if it's a real CSV or text file
            well_file.seek(0)
            well_df = pd.read_csv(well_file, header=None, on_bad_lines='skip', encoding='latin1')

        w_list = []
        current_name_key = None
        
        # We go row by row looking for a name, then the units for that name
        for _, row in well_df.iterrows():
            # FIXED: This line ensures everything is a string before joining
            row_items = [str(x) for x in row.values]
            row_str = " ".join(row_items)
            
            # A. Find a potential Name (Usually has a comma and a long ID number)
            if "," in row_str and any(len(str(x)) > 5 and str(x).isdigit() for x in row.values):
                # Hunt for the specific cell that has the "Last, First" name
                for cell in row_items:
                    if "," in cell and len(cell) > 3 and "Total" not in cell:
                        current_name_key = clean_key(cell)
                        break
            
            # B. Find the Units (Look for 'Total' or 'Sub Total')
            if "total" in row_str.lower() and current_name_key:
                # Look through the numbers in this row for the total
                nums = []
                for cell in row_items:
                    try:
                        # Clean the cell of any non-numeric junk except decimals
                        clean_num = re.sub(r'[^\d.]', '', cell)
                        if clean_num:
                            n = float(clean_num)
                            # Most unit totals are between 1 and 200
                            if 0 < n < 500: nums.append(n)
                    except: continue
                
                if nums:
                    # In Wellsky, the last number in a total row is usually the sum
                    w_list.append({'Key': current_name_key, 'Well': nums[-1]})
                    current_name_key = None # Reset for next person

        # Clean up Wellsky results
        if w_list:
            df_w = pd.DataFrame(w_list).groupby('Key').sum().reset_index()
        else:
            df_w = pd.DataFrame(columns=['Key', 'Well'])

        # --- 3. MERGE & COMPARE ---
        if not df_s.empty:
            final = pd.merge(df_s, df_w, on='Key', how='left').fillna(0)
            final['Diff'] = final['Serv'] - final['Well']
            
            # Show a success message if we found data
            if not df_w.empty:
                st.success(f"Matched {len(df_w)} clients from the Wellsky file.")
            else:
                st.warning("⚠️ Files uploaded, but no units were found in the Wellsky file. Check the 'Debug' section below.")

            # Display Table (Sort by those with differences)
            display_df = final[['Name', 'Serv', 'Well', 'Diff']].sort_values(by="Diff", ascending=False)
            st.dataframe(display_df, use_container_width=True)
            
            # Download Results
            csv = display_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Results", csv, "Reconciliation.csv", "text/csv")
            
            # Hidden Debug View
            with st.expander("Debug Mode: Raw Wellsky Data"):
                st.write("This shows the first 20 rows of your Wellsky file so we can see where the columns are:")
                st.write(well_df.head(20))
        else:
            st.error("No names found in Servtracker file. Ensure it is the 'Accumulative Monthly' report.")

    except Exception as e:
        st.error(f"Something went wrong: {e}")
