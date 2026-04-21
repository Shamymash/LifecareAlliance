import streamlit as st
import pandas as pd
import re
import difflib

st.set_page_config(page_title="Universal Reconciler", layout="wide")
st.title("📊 Universal Servtracker vs. WellSky Matcher")

# --- 1. THE "CLEANER" (Handles Jr, Sr, III, Hyphens) ---
def get_clean_key(last, first):
    def sanitize(text):
        text = str(text).lower()
        # Remove suffixes: Jr, Sr, II, III, IV, V
        text = re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', text)
        # Keep only letters
        return re.sub(r'[^a-z]', '', text)
    return sanitize(last) + sanitize(first)

# --- 2. THE SERVTRACKER SCANNER ---
def scan_servtracker(file):
    df = pd.read_csv(file, header=None, encoding="latin1") if file.name.endswith('.csv') else pd.read_excel(file, header=None)
    
    # Find the 'Totals' column index by searching the header row
    totals_col = None
    for row_idx in range(10): # Check first 10 rows for header
        row_vals = [str(x).strip() for x in df.iloc[row_idx]]
        if 'Totals' in row_vals:
            totals_col = row_vals.index('Totals')
            start_row = row_idx + 1
            break
    
    if totals_col is None: totals_col = df.shape[1] - 1 # Fallback to last column
    
    records = []
    for _, row in df.iloc[5:].iterrows():
        full_name = str(row.iloc[0]).strip()
        if "," not in full_name or "total" in full_name.lower(): continue
        
        # Split Name: "Last, First" or "Last, Suffix, First"
        parts = [p.strip() for p in full_name.split(",")]
        last_name = parts[0]
        first_name = parts[-1].split()[0] # Grabs just "John" from "John A"
        
        units = pd.to_numeric(row.iloc[totals_col], errors="coerce")
        if pd.notna(units) and units > 0:
            records.append({
                "Full Name": full_name,
                "Key": get_clean_key(last_name, first_name),
                "Serv Units": float(units)
            })
    return pd.DataFrame(records)

# --- 3. THE WELLSKY SCANNER (Universal Version) ---
def scan_wellsky(file):
    df = pd.read_csv(file, header=None, encoding="latin1") if file.name.endswith('.csv') else pd.read_excel(file, header=None)
    
    records = []
    current_key = None
    
    for _, row in df.iterrows():
        # Convert row to list of strings
        cells = [str(x).strip() for x in row.values]
        row_str = " ".join(cells).lower()

        # STEP A: Look for Name Row (Contains a Client ID)
        # Looks for any 7-10 digit number
        id_match = [c for c in cells if re.match(r'^\d{7,10}(\.0)?$', c)]
        if id_match:
            # Once we find an ID, the next two "word" cells are usually Last and First name
            words = [c for c in cells if c.isalpha() and len(c) > 1 and c.lower() not in ['client', 'id', 'mi']]
            if len(words) >= 2:
                current_key = get_clean_key(words[0], words[1])

        # STEP B: Look for Units Row (Contains "Sub Total")
        if "sub total" in row_str and current_key:
            # Find the first number in this row that isn't the total cost (usually the middle number)
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
                current_key = None # Reset for next client

    if not records: return pd.DataFrame(columns=["Key", "Well Units"])
    return pd.DataFrame(records).groupby("Key", as_index=False).sum()

# --- 4. STREAMLIT UI ---
st.info("Upload both files below. The app will automatically scan for names and units.")
col1, col2 = st.columns(2)
with col1:
    file_s = st.file_uploader("1. Servtracker File", type=["csv", "xlsx"])
with col2:
    file_w = st.file_uploader("2. WellSky File", type=["csv", "xlsx"])

if file_s and file_w:
    with st.spinner("Reconciling..."):
        df_s = scan_servtracker(file_s)
        df_w = scan_wellsky(file_w)

        if df_s.empty:
            st.error("Could not find any clients in the Servtracker file.")
        else:
            # Merge
            final = pd.merge(df_s, df_w, on="Key", how="left").fillna(0)
            
            # Fuzzy Match for the leftovers (the "45 discrepancies")
            unmatched = final[final["Well Units"] == 0].index
            if len(unmatched) > 0 and not df_w.empty:
                well_keys = df_w["Key"].tolist()
                for i in unmatched:
                    s_key = final.at[i, "Key"]
                    # Find a match that is 85% similar
                    match = difflib.get_close_matches(s_key, well_keys, n=1, cutoff=0.85)
                    if match:
                        units = df_w[df_w["Key"] == match[0]]["Well Units"].values[0]
                        final.at[i, "Well Units"] = units
                        final.at[i, "Match Type"] = "Fuzzy Match"
                    else:
                        final.at[i, "Match Type"] = "No Match Found"

            final["Diff"] = final["Serv Units"] - final["Well Units"]
            final.loc[final["Match Type"].isna(), "Match Type"] = "Exact Match"

            # Display Stats
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Servtracker Clients", len(df_s))
            c2.metric("Total Matches", (final["Well Units"] > 0).sum())
            c3.metric("True Discrepancies", (final["Diff"] != 0).sum())

            # Detailed Table
            st.dataframe(final[["Full Name", "Serv Units", "Well Units", "Diff", "Match Type"]].sort_values("Diff", ascending=False), use_container_width=True)
            
            # Download
            st.download_button("📥 Download Reconciliation Report", final.to_csv(index=False), "Reconciliation_Report.csv")
