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
        # Remove suffixes and extra descriptors often found in Servtracker
        text = re.sub(r'\b(jr|sr|ii|iii|iv|v|inc|jr\.|sr\.)\b', '', text)
        return re.sub(r'[^a-z]', '', text)
    return sanitize(last) + sanitize(first)

# --- 2. THE SERVTRACKER SCANNER ---
def scan_servtracker(file):
    # Support for xls, xlsx, and csv
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

        # Step A: Find Client Name via Client ID pattern
        id_match = [c for c in cells if re.match(r'^\d{7,10}(\.0)?$', c)]
        if id_match:
            # Filter out numbers and common labels to find the names
            words = [c for c in cells if c.replace('-', '').isalpha() and len(c) > 1 and c.lower() not in ['client', 'id', 'mi', 'residential', 'address']]
            if len(words) >= 2:
                current_key = get_clean_key(words[0], words[1])

        # Step B: Find Units via "Sub Total"
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
                # Usually units is the first number in the subtotal row
                records.append({"Key": current_key, "Well Units": nums[0]})
                current_key = None

    if not records: return pd.DataFrame(columns=["Key", "Well Units"])
    return pd.DataFrame(records).groupby("Key", as_index=False).sum()

# --- 4. UI ---
st.info("The app now accepts .csv, .xlsx, and .xls files.")
col1, col2 = st.columns(2)
with col1:
    # ADDED 'xls' TO TYPE LIST HERE
    file_s = st.file_uploader("1. Servtracker File", type=["csv", "xlsx", "xls"])
with col2:
    # ADDED 'xls' TO TYPE LIST HERE
    file_w = st.file_uploader("2. WellSky File", type=["csv", "xlsx", "xls"])

if file_s and file_w:
    with st.spinner("Analyzing data..."):
        df_s = scan_servtracker(file_s)
        df_w = scan_wellsky(file_w)

        if df_s.empty:
            st.error("Servtracker file looks empty or formatted incorrectly.")
        else:
            final = pd.merge(df_s, df_w, on="Key", how="left").fillna(0)
            
            # Fuzzy Match Logic
            unmatched = final[final["Well Units"] == 0].index
            if len(unmatched) > 0 and not df_w.empty:
                well_keys = df_w["Key"].tolist()
                for i in unmatched:
                    s_key = final.at[i, "Key"]
                    match = difflib.get_close_matches(s_key, well_keys, n=1, cutoff=0.85)
                    if match:
                        units = df_w[df_w["Key"] == match[0]]["Well Units"].values[0]
                        final.at[i, "Well Units"] = units
                        final.at[i, "Match Type"] = "Fuzzy Match"
            
            final["Diff"] = final["Serv Units"] - final["Well Units"]
            final.loc[final["Match Type"].isna(), "Match Type"] = "Exact Match"
            final.loc[final["Well Units"] == 0, "Match Type"] = "No Match"

            # Results Display
            c1, c2, c3 = st.columns(3)
            c1.metric("Servtracker Clients", len(df_s))
            c2.metric("Matches Found", (final["Well Units"] > 0).sum())
            c3.metric("Discrepancies", (final["Diff"] != 0).sum())

            st.dataframe(final[["Full Name", "Serv Units", "Well Units", "Diff", "Match Type"]].sort_values("Diff", ascending=False), use_container_width=True)
            st.download_button("📥 Download Report", final.to_csv(index=False), "Full_Reconciliation.csv")
