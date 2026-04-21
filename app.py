import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Data Matcher", layout="wide")
st.title("📊 Servtracker vs. WellSky Matcher")

# --- 1. KEY GENERATION LOGIC ---
def clean_servtracker_key(name):
    """Converts 'Adams, Thomas B.' into 'adamsthomas'"""
    if pd.isna(name) or not name: return ""
    name = str(name).lower()
    if "," in name:
        parts = name.split(",")
        last = re.sub(r'[^a-z]', '', parts[0])
        # Grabs the first word of the first name, dropping middle initials
        first = re.sub(r'[^a-z]', '', parts[1].strip().split()[0]) 
        return last + first
    return re.sub(r'[^a-z]', '', name)

def build_wellsky_key(last, first):
    """Converts 'Adams' and 'Thomas' into 'adamsthomas'"""
    last = re.sub(r'[^a-z]', '', str(last).lower())
    first = re.sub(r'[^a-z]', '', str(first).lower())
    return last + first

# --- 2. PARSERS ---
def process_servtracker(file):
    df = pd.read_excel(file)
    records = []
    # Servtracker data starts around row 5
    for _, row in df.iloc[5:].iterrows():
        name = str(row.iloc[0]).strip()
        if "," not in name or "total" in name.lower():
            continue
        units = pd.to_numeric(row.iloc[108], errors="coerce")
        if pd.notna(units) and units > 0:
            records.append({
                "Name": name,
                "Key": clean_servtracker_key(name),
                "Serv": float(units)
            })
    return pd.DataFrame(records)

def process_wellsky(file):
    if file.name.lower().endswith(".csv"):
        df = pd.read_csv(file, header=None, encoding="latin1", on_bad_lines="skip")
    else:
        df = pd.read_excel(file, header=None)

    records = []
    current_key = None

    for _, row in df.iterrows():
        # Drop empty cells to make searching easy
        cells = [str(x).strip() for x in row.values if pd.notna(x) and str(x).strip() not in ('', 'nan')]
        
        # A. Look for Client Name (Triggers when it sees a 7+ digit ID)
        if any(c.isdigit() and len(c) >= 7 for c in cells):
            # Find all words that look like names (ignores IDs, single letters, and headers)
            words = [c for c in cells if c.isalpha() and len(c) > 1 and c.lower() not in ['client', 'id', 'last', 'first', 'name', 'mi', 'address', 'residential']]
            if len(words) >= 2:
                # The first two valid words are Last Name and First Name
                current_key = build_wellsky_key(words[0], words[1])

        # B. Look for Units (Triggers on "Sub Total")
        row_str = " ".join(cells).lower()
        if "sub total" in row_str and current_key:
            nums = []
            for c in cells:
                # Extract numbers from cells
                num_str = re.sub(r'[^\d.]', '', c)
                if num_str and num_str != '.':
                    try:
                        v = float(num_str)
                        if 0 < v < 500: nums.append(v)
                    except: pass
            
            if nums:
                # The first number found after 'Sub Total' is the units
                records.append({"Key": current_key, "Well": nums[0]})
                current_key = None # Reset for next person
    
    if records:
        return pd.DataFrame(records).groupby("Key", as_index=False).sum()
    return pd.DataFrame(columns=["Key", "Well"])

# --- 3. MAIN UI ---
col1, col2 = st.columns(2)
with col1:
    serv_file = st.file_uploader("1. Upload Servtracker", type=["xlsx"])
with col2:
    well_file = st.file_uploader("2. Upload WellSky", type=["xls", "xlsx", "csv"])

if serv_file and well_file:
    with st.spinner("Processing files..."):
        try:
            df_s = process_servtracker(serv_file)
            df_w = process_wellsky(well_file)

            if not df_s.empty:
                final = pd.merge(df_s, df_w, on="Key", how="left").fillna(0)
                final["Diff"] = final["Serv"] - final["Well"]

                matches = (final["Well"] > 0).sum()
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Servtracker Clients", len(df_s))
                c2.metric("WellSky Matches", matches)
                c3.metric("Discrepancies", (final["Diff"] != 0).sum())

                if matches > 0:
                    st.success(f"Success! Found {matches} matches.")
                else:
                    st.error("0 matches. Please verify Wellsky format.")

                display_df = final[["Name", "Serv", "Well", "Diff"]].sort_values(by="Diff", ascending=False)
                st.dataframe(display_df, use_container_width=True)

                csv = display_df.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download Report", csv, "Reconciliation.csv", "text/csv")
            else:
                st.error("No Servtracker data found.")
        except Exception as e:
            st.error(f"Error: {e}")
