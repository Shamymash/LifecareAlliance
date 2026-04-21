import streamlit as st
import pandas as pd
import re
import difflib

st.set_page_config(page_title="Reconciliation Tool", layout="wide")
st.title("📊 Servtracker vs. WellSky Reconciliation")

def clean_key(last, first):
    """Deep cleans names to remove suffixes and special characters"""
    def sanitize(text):
        text = str(text).lower()
        # Remove common suffixes
        text = re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', text)
        # Remove everything except letters
        return re.sub(r'[^a-z]', '', text)
    
    return sanitize(last) + sanitize(first)

def process_servtracker(file):
    df = pd.read_csv(file, header=None, encoding="latin1") if file.name.endswith('.csv') else pd.read_excel(file, header=None)
    
    # 1. Find Totals column
    totals_idx = 108 # Default
    for i, val in enumerate(df.iloc[4]):
        if 'Totals' in str(val):
            totals_idx = i
            break
            
    records = []
    for _, row in df.iloc[5:].iterrows():
        full_name = str(row.iloc[0]).strip()
        if "," not in full_name or "total" in full_name.lower():
            continue
            
        # Parse "Last, [Suffix], First"
        parts = [p.strip() for p in full_name.split(",")]
        last = parts[0]
        first = parts[-1].split()[0] # Get just the first word of the first name part
        
        units = pd.to_numeric(row.iloc[totals_idx], errors="coerce")
        if pd.notna(units) and units > 0:
            records.append({
                "Name": full_name,
                "Key": clean_key(last, first),
                "Serv": float(units)
            })
    return pd.DataFrame(records)

def process_wellsky(file):
    df = pd.read_csv(file, header=None, encoding="latin1") if file.name.endswith('.csv') else pd.read_excel(file, header=None)
    
    records = []
    current_key = None
    
    # Layout: Col 1=ID, Col 5=Last, Col 10=First, Col 17=Label, Col 19=Units
    for _, row in df.iterrows():
        # Identify Client Row
        client_id = str(row.iloc[1]).replace('.0', '')
        if client_id.isdigit() and len(client_id) >= 7:
            last = str(row.iloc[5])
            first = str(row.iloc[10])
            current_key = clean_key(last, first)
            
        # Identify Units Row
        label = str(row.iloc[17])
        if "sub total" in label.lower() and current_key:
            units = pd.to_numeric(row.iloc[19], errors="coerce")
            if pd.notna(units):
                records.append({"Key": current_key, "Well": float(units)})
                
    if not records: return pd.DataFrame(columns=["Key", "Well"])
    return pd.DataFrame(records).groupby("Key", as_index=False).sum()

# --- UI ---
up_s = st.file_uploader("Upload Servtracker Report", type=["csv", "xlsx"])
up_w = st.file_uploader("Upload WellSky Report", type=["csv", "xlsx"])

if up_s and up_w:
    df_s = process_servtracker(up_s)
    df_w = process_wellsky(up_w)
    
    if not df_s.empty:
        # 1. Exact Match
        final = pd.merge(df_s, df_w, on="Key", how="left").fillna(0)
        final["Match Type"] = final["Well"].apply(lambda x: "Exact" if x > 0 else "None")
        
        # 2. Fuzzy Match for leftovers
        unmatched_idx = final[final["Well"] == 0].index
        if len(unmatched_idx) > 0:
            w_keys = df_w["Key"].tolist()
            for idx in unmatched_idx:
                s_key = final.at[idx, "Key"]
                matches = difflib.get_close_matches(s_key, w_keys, n=1, cutoff=0.8)
                if matches:
                    matched_units = df_w[df_w["Key"] == matches[0]]["Well"].values[0]
                    final.at[idx, "Well"] = matched_units
                    final.at[idx, "Match Type"] = "Fuzzy"
        
        final["Diff"] = final["Serv"] - final["Well"]
        
        # Dashboard
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Clients", len(df_s))
        c2.metric("Successful Matches", (final["Well"] > 0).sum())
        c3.metric("Discrepancies", (final["Diff"] != 0).sum())
        
        st.dataframe(final[["Name", "Serv", "Well", "Diff", "Match Type"]].sort_values("Diff", ascending=False), use_container_width=True)
        st.download_button("Download Results", final.to_csv(index=False), "Reconciliation.csv")
