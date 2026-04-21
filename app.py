import streamlit as st
import pandas as pd
import re
import difflib

st.set_page_config(page_title="Data Matcher Pro", layout="wide")
st.title("📊 Servtracker vs. WellSky Final Reconciliation")

# --- 1. THE KEY GENERATOR (The "Secret Sauce") ---
def get_clean_key(last, first):
    """Standardizes names: removes suffixes, spaces, and non-alphas"""
    def clean(text):
        text = str(text).lower()
        # Remove common suffixes that cause mismatches
        text = re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', text)
        # Keep only letters
        return re.sub(r'[^a-z]', '', text)
    
    # Only take the first word of the first name (ignores middle initials)
    first_name = str(first).split()[0] if first else ""
    return clean(last) + clean(first_name)

# --- 2. IMPROVED WELLSKY SCANNER ---
def scan_wellsky(file):
    if file.name.lower().endswith('.csv'):
        df = pd.read_csv(file, header=None, encoding="latin1")
    else:
        df = pd.read_excel(file, header=None)

    records = []
    for _, row in df.iterrows():
        cells = [str(x).strip() for x in row.values if pd.notna(x)]
        
        # Look for the name cell (must have a comma)
        full_name = None
        for c in cells:
            if "," in c and any(ch.isalpha() for ch in c):
                if "total" not in c.lower() and "residential" not in c.lower():
                    full_name = c
                    break
        
        if not full_name:
            continue

        # Extract numeric values (Units) from the same row
        nums = []
        for c in cells:
            clean_n = re.sub(r'[^\d.]', '', c)
            if clean_n and clean_n != '.':
                try:
                    val = float(clean_n)
                    if 0 < val < 1000: # Ignore IDs or huge numbers
                        nums.append(val)
                except: pass

        if nums:
            parts = full_name.split(",")
            if len(parts) >= 2:
                last = parts[0].strip()
                # Handle cases like "Sr, Bobby" or "Bobby A"
                first_part = parts[-1].strip() 
                
                records.append({
                    "Key": get_clean_key(last, first_part),
                    "Well": nums[-1] # Take the last number (usually the Sub Total)
                })

    if not records: return pd.DataFrame(columns=["Key", "Well"])
    return pd.DataFrame(records).groupby("Key", as_index=False).sum()

# --- 3. SERVTRACKER PROCESSOR ---
def process_servtracker(file):
    if file.name.lower().endswith(".csv"):
        df = pd.read_csv(file, header=None, encoding="latin1")
    else:
        df = pd.read_excel(file, header=None)
    
    # Find the 'Totals' column
    totals_col = 108
    for row_idx in range(min(10, len(df))):
        for i, val in enumerate(df.iloc[row_idx]):
            if 'Totals' in str(val):
                totals_col = i
                break
    
    records = []
    for _, row in df.iloc[5:].iterrows():
        name = str(row.iloc[0]).strip()
        if "," not in name or "total" in name.lower(): continue
        
        try:
            val = pd.to_numeric(row.iloc[totals_col], errors="coerce")
            if pd.notna(val) and val > 0:
                parts = name.split(",")
                records.append({
                    "Name": name,
                    "Key": get_clean_key(parts[0], parts[1]),
                    "Serv": float(val)
                })
        except: pass
    return pd.DataFrame(records)

# --- 4. MAIN UI ---
col1, col2 = st.columns(2)
with col1:
    serv_file = st.file_uploader("1. Servtracker File", type=["xls", "xlsx", "csv"])
with col2:
    well_file = st.file_uploader("2. WellSky File", type=["xls", "xlsx", "csv"])

if serv_file and well_file:
    df_s = process_servtracker(serv_file)
    df_w = scan_wellsky(well_file)

    if not df_s.empty:
        # Initial Match
        final = pd.merge(df_s, df_w, on="Key", how="left").fillna(0)
        
        # Fuzzy Match for remaining 0s
        unmatched_s = final[final["Well"] == 0].index
        used_w_keys = final[final["Well"] > 0]["Key"].tolist()
        avail_w = df_w[~df_w["Key"].isin(used_w_keys)]
        
        if not avail_w.empty and len(unmatched_s) > 0:
            w_keys = avail_w["Key"].tolist()
            for idx in unmatched_s:
                s_key = final.at[idx, "Key"]
                matches = difflib.get_close_matches(s_key, w_keys, n=1, cutoff=0.8)
                if matches:
                    match_key = matches[0]
                    match_val = avail_w[avail_w["Key"] == match_key]["Well"].values[0]
                    final.at[idx, "Well"] = match_val
                    w_keys.remove(match_key)

        final["Diff"] = final["Serv"] - final["Well"]
        
        # Statistics
        discrepancies = final[final["Diff"] != 0]
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Clients", len(df_s))
        c2.metric("Discrepancies Found", len(discrepancies))
        c3.metric("Perfect Matches", len(df_s) - len(discrepancies))

        st.subheader("Discrepancy Report")
        if not discrepancies.empty:
            st.dataframe(discrepancies[["Name", "Serv", "Well", "Diff"]].sort_values("Diff", ascending=False))
        else:
            st.success("Perfect Match! No discrepancies found.")

        csv = final.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Final Report", csv, "Reconciliation_Results.csv")
