import streamlit as st
import pandas as pd
import re
import difflib
import io

st.set_page_config(page_title="Data Matcher Pro", layout="wide")
st.title("📊 Servtracker vs. WellSky Final Reconciliation")

# --- 1. THE KEY GENERATOR (The "Secret Sauce") ---
def get_clean_key(last, first):
    """Standardizes names: removes suffixes, spaces, and non-alphas"""
    def clean(text):
        if pd.isna(text): return ""
        text = str(text).lower()
        # Aggressively remove suffixes
        text = re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', text)
        # Keep only letters (removes spaces, hyphens, periods)
        return re.sub(r'[^a-z]', '', text)
    
    # Only use the first word of the first name field (ignores middle initials)
    first_name = str(first).strip().split()[0] if first and not pd.isna(first) else ""
    return clean(last) + clean(first_name)

# --- 2. UPDATED WELLSKY SCANNER (Minimum Value Logic) ---
def scan_wellsky(file):
    if file.name.lower().endswith('.csv'):
        df = pd.read_csv(file, header=None, encoding="latin1")
    else:
        df = pd.read_excel(file, header=None)

    records = []
    current_key = None
    
    for _, row in df.iterrows():
        # Identify Name Row: Col 1 = ID, Col 5 = Last, Col 9 = First
        last_val = str(row.iloc[5]).strip() if len(row) > 5 else ""
        first_val = str(row.iloc[10]).strip() if len(row) > 10 else ""
        id_val = str(row.iloc[1]).strip() if len(row) > 1 else ""
        
        # Check if row contains a client (ID is numeric and Last Name exists)
        is_name_row = id_val.replace('.0','').isdigit() and last_val.lower() not in ["nan", "last name", ""]
        
        if is_name_row:
            current_key = get_clean_key(last_val, first_val)
            
        # Identify a 'Sub Total Row'
        row_content = " ".join([str(x).lower() for x in row.values if pd.notna(x)])
        if "sub total:" in row_content and current_key:
            nums = []
            # Scan all columns in the row to find numeric values
            for val in row.values:
                try:
                    num_str = re.sub(r'[^\d.]', '', str(val))
                    if num_str and num_str != '.':
                        num_val = float(num_str)
                        # Range check to avoid IDs (usually 10 digits) or empty cells
                        if 0 < num_val < 1000:
                            nums.append(num_val)
                except:
                    continue
            
            if nums:
                # CRITICAL FIX: Units are almost always the smallest number in the subtotal row
                # (e.g., Units: 56, Billed: $451.00 -> 56 is the correct value)
                units = min(nums)
                records.append({"Key": current_key, "Well": units})
                # We don't reset current_key here to allow for multiple service subtotals per person

    if not records: 
        return pd.DataFrame(columns=["Key", "Well"])
    
    # Group and sum in case a client appears multiple times in WellSky
    return pd.DataFrame(records).groupby("Key", as_index=False).sum()

# --- 3. SERVTRACKER PROCESSOR ---
def process_servtracker(file):
    if file.name.lower().endswith(".csv"):
        df = pd.read_csv(file, header=None, encoding="latin1")
    else:
        df = pd.read_excel(file, header=None)
    
    # Find the 'Totals' column dynamically
    totals_col = None
    for row_idx in range(min(15, len(df))):
        vals = [str(v).strip() for v in df.iloc[row_idx]]
        if 'Totals' in vals:
            totals_col = vals.index('Totals')
            break
    
    if totals_col is None:
        st.error("Error: Could not find 'Totals' column in Servtracker report.")
        return pd.DataFrame()

    records = []
    # Data starts at Row 6 (index 5)
    for _, row in df.iloc[5:].iterrows():
        full_name = str(row.iloc[0]).strip()
        if "," not in full_name or "total" in full_name.lower() or full_name == "nan":
            continue
        
        try:
            val = pd.to_numeric(row.iloc[totals_col], errors="coerce")
            if pd.notna(val) and val > 0:
                parts = full_name.split(",")
                last = parts[0].strip()
                first = parts[1].strip()
                records.append({
                    "Name": full_name,
                    "Key": get_clean_key(last, first),
                    "Serv": float(val)
                })
        except:
            continue
            
    return pd.DataFrame(records)

# --- 4. MAIN UI ---
col1, col2 = st.columns(2)
with col1:
    serv_file = st.file_uploader("1. Servtracker File", type=["xls", "xlsx", "csv"])
with col2:
    well_file = st.file_uploader("2. WellSky File", type=["xls", "xlsx", "csv"])

if serv_file and well_file:
    with st.spinner("Reconciling units..."):
        df_s = process_servtracker(serv_file)
        df_w = scan_wellsky(well_file)

    if not df_s.empty and not df_w.empty:
        # Step 1: Exact Match
        final = pd.merge(df_s, df_w, on="Key", how="left").fillna(0)
        
        # Step 2: Fuzzy Match for missing keys
        unmatched_idx = final[final["Well"] == 0].index
        used_well_keys = final[final["Well"] > 0]["Key"].tolist()
        available_well = df_w[~df_w["Key"].isin(used_well_keys)]
        
        if not available_well.empty and len(unmatched_idx) > 0:
            well_keys = available_well["Key"].tolist()
            for idx in unmatched_idx:
                s_key = final.at[idx, "Key"]
                matches = difflib.get_close_matches(s_key, well_keys, n=1, cutoff=0.8)
                if matches:
                    match_key = matches[0]
                    match_val = available_well[available_well["Key"] == match_key]["Well"].values[0]
                    final.at[idx, "Well"] = match_val
                    well_keys.remove(match_key)

        final["Diff"] = final["Serv"] - final["Well"]
        discrepancies = final[final["Diff"] != 0].copy()
        
        # Dashboard
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Servtracker Clients", len(df_s))
        m2.metric("Perfect Matches", len(df_s) - len(discrepancies))
        m3.metric("Discrepancies Found", len(discrepancies), delta_color="inverse")

        st.subheader("Discrepancy Table")
        if not discrepancies.empty:
            st.dataframe(
                discrepancies[["Name", "Serv", "Well", "Diff"]].sort_values("Diff", ascending=False), 
                use_container_width=True
            )
        else:
            st.success("✅ Perfect Match! No discrepancies found.")

        # Download Report
        csv_data = final.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Final Report", csv_data, "Reconciliation_Results.csv", "text/csv")
