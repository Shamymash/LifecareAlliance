import streamlit as st
import pandas as pd
import re
import difflib

st.set_page_config(page_title="Universal Reconciler", layout="wide")
st.title("📊 Universal Servtracker vs. WellSky Matcher")

# --- 1. THE "CLEANER" ---
def get_clean_key(last, first):
    def sanitize(text):
        text = str(text).lower()
        # Remove suffixes and extra descriptors
        text = re.sub(r'\b(jr|sr|ii|iii|iv|v|inc|jr\.|sr\.)\b', '', text)
        return re.sub(r'[^a-z]', '', text)
    return sanitize(last) + sanitize(first)

# --- 2. THE SERVTRACKER SCANNER ---
def scan_servtracker(file):
    if file.name.lower().endswith('.csv'):
        df = pd.read_csv(file, header=None, encoding="latin1")
    else:
        df = pd.read_excel(file, header=None)
    
    totals_col = None
    for row_idx in range(min(15, len(df))):
        row_vals = [str(x).strip() for x in df.iloc[row_idx]]
        if 'Totals' in row_vals:
            totals_col = row_vals.index('Totals')
            break
    
    if totals_col is None: totals_col = df.shape[1] - 1
    
    records = []
    for _, row in df.iloc[5:].iterrows():
        full_name = str(row.iloc[0]).strip()
        if "," not in full_name or "total" in full_name.lower() or full_name == "nan": 
            continue
        
        parts = [p.strip() for p in full_name.split(",")]
        last_name = parts[0]
        first_name = parts[-1].split()[0]
        
        units = pd.to_numeric(row.iloc[totals_col], errors="coerce")
        if pd.notna(units) and units > 0:
            records.append({
                "Full Name": full_name,
                "Key": get_clean_key(last_name, first_name),
                "Serv Units": float(units)
            })
    return pd.DataFrame(records)

# --- 3. THE WELLSKY SCANNER ---
def scan_wellsky(file):
    if file.name.lower().endswith('.csv'):
        df = pd.read_csv(file, header=None, encoding="latin1")
    else:
        df = pd.read_excel(file, header=None)
    
    records = []
    current_key = None
    
    for _, row in df.iterrows():
        cells = [str(x).strip() for x in row.values]
        row_str = " ".join(cells).lower()

        id_match = [c for c in cells if re.match(r'^\d{7,10}(\.0)?$', c)]
        if id_match:
            words = [c for c in cells if c.replace('-', '').isalpha() and len(c) > 1 and c.lower() not in ['client', 'id', 'mi', 'residential', 'address']]
            if len(words) >= 2:
                current_key = get_clean_key(words[0], words[1])

        if "sub total" in row_str and current_key:
            nums = []
            for c in cells:
                clean_n = re.sub(r'[^\d.]', '', c)
                if clean_n and clean_n != '.':
                    try:
                        val = float(clean_n)
                        if 0 < val < 1000: nums.append(val)
                    except: pass
            
            if nums:
                records.append({"Key": current_key, "Well Units": nums[0]})
                current_key = None

    if not records: return pd.DataFrame(columns=["Key", "Well Units"])
    return pd.DataFrame(records).groupby("Key", as_index=False).sum()

# --- 4. UI ---
col1, col2 = st.columns(2)
with col1:
    file_s = st.file_uploader("1. Servtracker File", type=["csv", "xlsx", "xls"])
with col2:
    file_w = st.file_uploader("2. WellSky File", type=["csv", "xlsx", "xls"])

if file_s and file_w:
    with st.spinner("Analyzing data..."):
        df_s = scan_servtracker(file_s)
        df_w = scan_wellsky(file_w)

        if df_s.empty:
            st.error("Servtracker file looks empty or formatted incorrectly.")
        else:
            # Merge files
            final = pd.merge(df_s, df_w, on="Key", how="left").fillna(0)
            
            # FIX: Initialize 'Match Type' immediately to prevent KeyError
            final["Match Type"] = "No Match"
            final.loc[final["Well Units"] > 0, "Match Type"] = "Exact Match"
            
            # Fuzzy Match Logic for the "No Match" ones
            unmatched_indices = final[final["Match Type"] == "No Match"].index
            if len(unmatched_indices) > 0 and not df_w.empty:
                well_keys = df_w["Key"].tolist()
                for i in unmatched_indices:
                    s_key = final.at[i, "Key"]
                    match = difflib.get_close_matches(s_key, well_keys, n=1, cutoff=0.85)
                    if match:
                        units = df_w[df_w["Key"] == match[0]]["Well Units"].values[0]
                        final.at[i, "Well Units"] = units
                        final.at[i, "Match Type"] = "Fuzzy Match"
            
            final["Diff"] = final["Serv Units"] - final["Well Units"]

            # Results Display
            c1, c2, c3 = st.columns(3)
            c1.metric("Servtracker Clients", len(df_s))
            c2.metric("Matches Found", (final["Well Units"] > 0).sum())
            c3.metric("Discrepancies", (final["Diff"] != 0).sum())

            # Show results
            display_cols = ["Full Name", "Serv Units", "Well Units", "Diff", "Match Type"]
            st.dataframe(final[display_cols].sort_values("Diff", ascending=False), use_container_width=True)
            
            # Download button
            csv = final.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Report", csv, "Full_Reconciliation.csv", "text/csv")
