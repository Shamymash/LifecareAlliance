import streamlit as st
import pandas as pd
import re
import difflib # <-- Built-in Python library for Fuzzy Matching

st.set_page_config(page_title="Data Matcher", layout="wide")
st.title("📊 Servtracker vs. WellSky Matcher")

# --- 1. KEY GENERATION LOGIC ---
def clean_servtracker_key(name):
    """Strips Jr/Sr/III, handles multiple commas, and grabs the core name"""
    if pd.isna(name) or not name: return ""
    name = str(name).lower()
    if "," in name:
        parts = name.split(",")
        
        # parts[0] is Last Name, parts[-1] is First Name (bypasses suffixes stuck in the middle)
        last_clean = re.sub(r'[^a-z ]', '', parts[0])
        last_words = [w for w in last_clean.split() if w not in ['jr', 'sr', 'i', 'ii', 'iii', 'iv']]
        last = "".join(last_words)
        
        first_clean = re.sub(r'[^a-z ]', '', parts[-1])
        first = first_clean.split()[0] if first_clean.split() else ""
        
        return last + first
    return re.sub(r'[^a-z]', '', name)

def build_wellsky_key(last_val, first_val):
    """Applies the same suffix-stripping rules to WellSky"""
    last_clean = re.sub(r'[^a-z ]', '', str(last_val).lower())
    last_words = [w for w in last_clean.split() if w not in ['jr', 'sr', 'i', 'ii', 'iii', 'iv']]
    last = "".join(last_words)
    
    first_clean = re.sub(r'[^a-z ]', '', str(first_val).lower())
    first = first_clean.split()[0] if first_clean.split() else ""
    
    return last + first

# --- 2. PARSERS ---
def process_servtracker(file):
    if file.name.lower().endswith(".csv"):
        df = pd.read_csv(file, header=None, encoding="latin1", on_bad_lines="skip")
    else:
        df = pd.read_excel(file, header=None)

    records = []
    
    # Dynamically find which column holds the "Totals" (handles format changes)
    totals_col_idx = 108 # Fallback 
    for row_idx in range(min(10, len(df))):
        for i, val in enumerate(df.iloc[row_idx]):
            if 'Totals' in str(val):
                totals_col_idx = i
                break
                
    for _, row in df.iloc[5:].iterrows():
        name = str(row.iloc[0]).strip()
        if "," not in name or "total" in name.lower():
            continue
        try:
            units = pd.to_numeric(row.iloc[totals_col_idx], errors="coerce")
            if pd.notna(units) and units > 0:
                records.append({
                    "Name": name,
                    "Key": clean_servtracker_key(name),
                    "Serv": float(units)
                })
        except:
            pass
    return pd.DataFrame(records)

def process_wellsky(file):
    if file.name.lower().endswith(".csv"):
        df = pd.read_csv(file, header=None, encoding="latin1", on_bad_lines="skip")
    else:
        df = pd.read_excel(file, header=None)

    records = []
    current_key = None

    for _, row in df.iterrows():
        cells = [str(x).strip() for x in row.values if pd.notna(x) and str(x).strip() not in ('', 'nan')]
        
        if any(c.replace('.', '').isdigit() and len(c.replace('.', '')) >= 7 for c in cells):
            words = [c for c in cells if c.replace('-', '').replace(' ', '').isalpha() and len(c) > 1 and c.lower() not in ['client', 'id', 'last', 'first', 'name', 'mi', 'address', 'residential']]
            if len(words) >= 2:
                current_key = build_wellsky_key(words[0], words[1])

        row_str = " ".join(cells).lower()
        if "sub total" in row_str and current_key:
            nums = []
            for c in cells:
                num_str = re.sub(r'[^\d.]', '', c)
                if num_str and num_str != '.':
                    try:
                        v = float(num_str)
                        if 0 < v < 1000: nums.append(v)
                    except: pass
            
            if nums:
                records.append({"Key": current_key, "Well": nums[0]})
                current_key = None
    
    if records:
        return pd.DataFrame(records).groupby("Key", as_index=False).sum()
    return pd.DataFrame(columns=["Key", "Well"])

# --- 3. MAIN UI ---
col1, col2 = st.columns(2)
with col1:
    serv_file = st.file_uploader("1. Upload Servtracker", type=["xls", "xlsx", "csv"])
with col2:
    well_file = st.file_uploader("2. Upload WellSky", type=["xls", "xlsx", "csv"])

if serv_file and well_file:
    with st.spinner("Processing files and finding matches..."):
        try:
            df_s = process_servtracker(serv_file)
            df_w = process_wellsky(well_file)

            if not df_s.empty:
                # 1. Exact Matching
                final = pd.merge(df_s, df_w, on="Key", how="left").fillna(0)
                final["Match Type"] = "Exact Match"

                # 2. Fuzzy Matching (Catching typos and hyphens for the leftovers)
                unmatched_s_indices = final[final["Well"] == 0].index
                used_well_keys = final[final["Well"] > 0]["Key"].tolist()
                unused_w = df_w[~df_w["Key"].isin(used_well_keys)]

                if not unused_w.empty and len(unmatched_s_indices) > 0:
                    well_keys = unused_w["Key"].tolist()
                    for idx in unmatched_s_indices:
                        serv_key = final.at[idx, "Key"]
                        # Looks for an 85% or higher match
                        matches = difflib.get_close_matches(serv_key, well_keys, n=1, cutoff=0.85)
                        if matches:
                            best_match = matches[0]
                            matched_units = unused_w[unused_w["Key"] == best_match]["Well"].values[0]
                            
                            final.at[idx, "Well"] = matched_units
                            final.at[idx, "Match Type"] = f"Fuzzy Match"
                            
                            well_keys.remove(best_match)
                            unused_w = unused_w[unused_w["Key"] != best_match]

                final.loc[final["Well"] == 0, "Match Type"] = "No Match"
                final["Diff"] = final["Serv"] - final["Well"]

                matches = (final["Well"] > 0).sum()
                discrepancies = (final["Diff"] != 0).sum()
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Servtracker Clients", len(df_s))
                c2.metric("Total Matches (Exact + Fuzzy)", matches)
                c3.metric("True Discrepancies", discrepancies)

                if matches > 0:
                    st.success(f"Success! Matched {matches} out of {len(df_s)} clients.")
                else:
                    st.error("0 matches. Please verify Wellsky format.")

                display_df = final[["Name", "Serv", "Well", "Diff", "Match Type"]].sort_values(by="Diff", ascending=False)
                st.dataframe(display_df, use_container_width=True)

                csv = display_df.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download Report", csv, "Reconciliation_Final.csv", "text/csv")
            else:
                st.error("No Servtracker data found.")
        except Exception as e:
            st.error(f"Error: {e}")
