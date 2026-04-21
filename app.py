import streamlit as st
import pandas as pd
import re
import difflib
import io

st.set_page_config(page_title="Healthcare Data Reconciler", layout="wide")

# --- 1. THE KEY GENERATOR (The "Secret Sauce") ---
def get_clean_key(last, first):
    """Standardizes names: removes suffixes, spaces, and non-alphas"""
    def clean(text):
        if pd.isna(text): return ""
        text = str(text).lower()
        # Remove common suffixes that cause mismatches (jr, sr, etc.)
        text = re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', text)
        # Keep only letters
        return re.sub(r'[^a-z]', '', text)
    
    # Only take the first word of the first name (ignores middle initials)
    first_name = str(first).split()[0] if first and not pd.isna(first) else ""
    return clean(last) + clean(first_name)

# --- 2. WELLSKY SCANNER (Stateful logic) ---
def scan_wellsky(file):
    # Read the file without headers as it is non-tabular
    if file.name.lower().endswith('.csv'):
        df = pd.read_csv(file, header=None, encoding="latin1")
    else:
        df = pd.read_excel(file, header=None)

    records = []
    current_key = None
    
    for _, row in df.iterrows():
        # Check for Name Row (usually contains Client ID in col 1 and Last Name in col 5)
        # Based on snippet: Col 5 = Last, Col 9 = First
        last_name = str(row.iloc[5]).strip() if len(row) > 5 else ""
        first_name = str(row.iloc[9]).strip() if len(row) > 9 else ""
        
        # Identify if this is a name row (names should be alphabetic and not 'Last Name' header)
        if last_name and last_name != "nan" and last_name != "Last Name" and any(c.isalpha() for c in last_name):
            current_key = get_clean_key(last_name, first_name)
        
        # Look for "Sub Total:" in the row
        row_str = " ".join([str(x).lower() for x in row.values if pd.notna(x)])
        if "sub total:" in row_str and current_key:
            # The units are usually in the columns following 'Sub Total:'
            # We look for the first valid numeric value after the 'Sub Total' string
            for val in row.values:
                try:
                    clean_val = re.sub(r'[^\d.]', '', str(val))
                    if clean_val and clean_val != '.':
                        units = float(clean_val)
                        if 0 < units < 1000: # Filter out IDs or Currency
                            records.append({"Key": current_key, "Well": units})
                            current_key = None # Reset for next client
                            break
                except:
                    continue
                    
    if not records: return pd.DataFrame(columns=["Key", "Well"])
    # Group by key in case of duplicate entries
    return pd.DataFrame(records).groupby("Key", as_index=False).sum()

# --- 3. SERVTRACKER PROCESSOR ---
def process_servtracker(file):
    if file.name.lower().endswith(".csv"):
        df = pd.read_csv(file, header=None, encoding="latin1")
    else:
        df = pd.read_excel(file, header=None)
    
    # Find the 'Totals' column by scanning the first 10 rows
    totals_col = None
    for row_idx in range(min(10, len(df))):
        row_values = [str(x) for x in df.iloc[row_idx]]
        if 'Totals' in row_values:
            totals_col = row_values.index('Totals')
            break
    
    if totals_col is None:
        st.error("Could not find 'Totals' column in Servtracker file.")
        return pd.DataFrame()

    records = []
    # Start from row 5 as per instructions
    for _, row in df.iloc[5:].iterrows():
        full_name = str(row.iloc[0]).strip()
        if "," not in full_name or "total" in full_name.lower() or full_name == "nan":
            continue
        
        try:
            val = pd.to_numeric(row.iloc[totals_col], errors="coerce")
            if pd.notna(val) and val > 0:
                parts = full_name.split(",")
                last = parts[0].strip()
                first = parts[1].strip() if len(parts) > 1 else ""
                records.append({
                    "Name": full_name,
                    "Key": get_clean_key(last, first),
                    "Serv": float(val)
                })
        except:
            continue
            
    return pd.DataFrame(records)

# --- 4. MAIN UI ---
st.title("📊 Servtracker vs. WellSky Reconciliation")
st.markdown("Upload both reports to identify discrepancies in monthly service units.")

col1, col2 = st.columns(2)
with col1:
    serv_file = st.file_uploader("1. Servtracker File (Source A)", type=["xls", "xlsx", "csv"])
with col2:
    well_file = st.file_uploader("2. WellSky File (Source B)", type=["xls", "xlsx", "csv"])

if serv_file and well_file:
    with st.spinner("Processing files..."):
        df_s = process_servtracker(serv_file)
        df_w = scan_wellsky(well_file)

    if not df_s.empty and not df_w.empty:
        # Initial Exact Key Match
        final = pd.merge(df_s, df_w, on="Key", how="left").fillna(0)
        
        # Fuzzy Match Logic for Unmatched Records
        unmatched_idx = final[final["Well"] == 0].index
        used_w_keys = final[final["Well"] > 0]["Key"].tolist()
        avail_w = df_w[~df_w["Key"].isin(used_w_keys)]
        
        if not avail_w.empty and len(unmatched_idx) > 0:
            w_keys = avail_w["Key"].tolist()
            for idx in unmatched_idx:
                s_key = final.at[idx, "Key"]
                matches = difflib.get_close_matches(s_key, w_keys, n=1, cutoff=0.8)
                if matches:
                    match_key = matches[0]
                    match_val = avail_w[avail_w["Key"] == match_key]["Well"].values[0]
                    final.at[idx, "Well"] = match_val
                    w_keys.remove(match_key) # Don't reuse the same WellSky record

        final["Diff"] = final["Serv"] - final["Well"]
        discrepancies = final[final["Diff"] != 0].copy()
        
        # Metrics Dashboard
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Servtracker Clients", len(df_s))
        m2.metric("Perfect Matches", len(df_s) - len(discrepancies))
        m3.metric("Discrepancies", len(discrepancies), delta_color="inverse")

        # Display Table
        st.subheader("Discrepancy Report")
        if not discrepancies.empty:
            # Highlight differences
            st.dataframe(
                discrepancies[["Name", "Serv", "Well", "Diff"]]
                .sort_values("Diff", ascending=False),
                use_container_width=True
            )
        else:
            st.success("✅ All units match perfectly!")

        # Download Button
        csv_buffer = io.StringIO()
        final.to_csv(csv_buffer, index=False)
        st.download_button(
            label="📥 Download Final Reconciliation Report",
            data=csv_buffer.getvalue(),
            file_name="Reconciliation_Results.csv",
            mime="text/csv",
        )
    else:
        st.warning("Please ensure both files contain valid client data.")
