import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="Data Matcher", layout="wide")
st.title("📊 Servtracker vs WellSky Matcher")

def clean_key(text: str) -> str:
    """Normalize names: lowercase, remove non-alphas, sort parts to handle 'Last, First' vs 'First Last'."""
    if pd.isna(text) or text is None:
        return ""
    text = str(text).lower()
    text = re.sub(r"[^a-z ]", " ", text)
    parts = sorted([p for p in text.split() if p])
    return "".join(parts)

def process_servtracker(file):
    df_raw = pd.read_excel(file)
    records = []
    # Servtracker usually starts data on row 6 (index 5)
    for _, row in df_raw.iloc[5:].iterrows():
        try:
            name = str(row.iloc[0]).strip()
            # Skip totals or headers
            if "," not in name or "total" in name.lower():
                continue

            # Units are in column 109 (index 108)
            units = pd.to_numeric(row.iloc[108], errors="coerce")
            if pd.notna(units) and units > 0:
                records.append({
                    "Name": name,
                    "Key": clean_key(name),
                    "Serv": float(units)
                })
        except Exception:
            continue
    return pd.DataFrame(records)

def process_wellsky(file):
    # Determine file type and read
    if file.name.lower().endswith(".csv"):
        df = pd.read_csv(file, header=None, encoding="latin1")
    else:
        df = pd.read_excel(file, header=None)

    records = []
    current_key = None

    for _, row in df.iterrows():
        # Get raw values as list for index-based access
        vals = [str(x).strip() for x in row.values]
        row_text = " ".join(vals).lower()

        # 1. Look for Name Row (Identify by a numeric Client ID in Col index 2)
        client_id = vals[2] if len(vals) > 2 else ""
        if client_id.isdigit() and len(client_id) >= 7:
            # Coordinates from your specific file structure:
            last = vals[6] if len(vals) > 6 else ""
            first = vals[11] if len(vals) > 11 else ""
            mi = vals[19] if len(vals) > 19 else ""
            
            # Combine to match Servtracker's "Last, First MI" format
            full_name = f"{last} {first} {mi}"
            current_key = clean_key(full_name)

        # 2. Look for Sub Total Row (Units are in Col index 20)
        if current_key and "sub total:" in row_text:
            try:
                units_val = vals[20] if len(vals) > 20 else "0"
                units = float(re.sub(r"[^\d.]", "", units_val))
                if units > 0:
                    records.append({"Key": current_key, "Well": units})
            except:
                continue

    if not records:
        return pd.DataFrame(columns=["Key", "Well"])

    # Sum up units if a client appears multiple times
    return pd.DataFrame(records).groupby("Key", as_index=False).sum()

def reconcile(serv_df, well_df):
    final = pd.merge(serv_df, well_df, on="Key", how="left").fillna(0)
    final["Diff"] = final["Serv"] - final["Well"]
    return final[["Name", "Serv", "Well", "Diff"]].sort_values(by="Diff", ascending=False)

# UI Logic
col1, col2 = st.columns(2)
with col1:
    serv_file = st.file_uploader("1. Upload Servtracker (.xlsx)", type=["xlsx"])
with col2:
    well_file = st.file_uploader("2. Upload WellSky (.csv or .xls)", type=["xls", "xlsx", "csv"])

if serv_file and well_file:
    with st.spinner("Reconciling..."):
        df_serv = process_servtracker(serv_file)
        df_well = process_wellsky(well_file)

        if not df_serv.empty:
            result = reconcile(df_serv, df_well)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Servtracker Clients", len(df_serv))
            c2.metric("WellSky Matches", (result["Well"] > 0).sum())
            c3.metric("Discrepancies", (result["Diff"] != 0).sum())

            st.dataframe(result, use_container_width=True)
            
            csv_data = result.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Download Report", data=csv_data, file_name="reconciliation.csv")
        else:
            st.error("Could not find data in Servtracker file. Check column 109.")
