import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="Data Matcher", layout="wide")
st.title("📊 Servtracker vs WellSky Matcher")
st.caption("Robust reconciliation tool with flexible parsing and safer matching")


def clean_key(text: str) -> str:
    """Normalize names so formatting differences still match."""
    if pd.isna(text) or text is None:
        return ""
    text = str(text).lower()
    text = re.sub(r"[^a-z ]", " ", text)
    parts = sorted([p for p in text.split() if p])
    return "".join(parts)



def extract_name_from_cell(cell: str):
    """Extract name from formats like 'Last, First' or 'First Last'."""
    if not cell or cell == "nan":
        return None

    cell = str(cell).strip()

    if "," in cell:
        parts = [p.strip() for p in cell.split(",")]
        if len(parts) >= 2:
            return parts[0], parts[1]

    words = re.findall(r"[A-Za-z]+", cell)
    if len(words) >= 2:
        return words[-1], words[0]

    return None



def process_servtracker(file):
    df_raw = pd.read_excel(file)
    records = []

    for _, row in df_raw.iloc[5:].iterrows():
        try:
            name = str(row.iloc[0]).strip()
            if "," not in name or "total" in name.lower():
                continue

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



def read_wellsky_file(file):
    """Try multiple read methods for maximum compatibility."""
    filename = file.name.lower()

    if filename.endswith(".csv"):
        file.seek(0)
        return pd.read_csv(file, header=None, encoding="latin1", on_bad_lines="skip")

    try:
        file.seek(0)
        return pd.read_excel(file, header=None)
    except Exception:
        file.seek(0)
        return pd.read_csv(file, header=None, encoding="latin1", on_bad_lines="skip")



def process_wellsky(file):
    df = read_wellsky_file(file)

    records = []
    current_key = None

    for _, row in df.iterrows():
        row_vals = [str(x).strip() for x in row.values if str(x).strip() != "nan"]
        row_text = " | ".join(row_vals)

        # Find patient/client name anywhere in row
        for cell in row_vals:
            extracted = extract_name_from_cell(cell)
            if extracted:
                last_name, first_name = extracted
                current_key = clean_key(f"{last_name} {first_name}")
                break

        # Find subtotal / units anywhere in row
        if current_key and "sub total" in row_text.lower():
            nums = re.findall(r"\d+\.?\d*", row_text)
            if nums:
                units = float(nums[-1])
                records.append({
                    "Key": current_key,
                    "Well": units
                })

    if not records:
        return pd.DataFrame(columns=["Key", "Well"])

    return pd.DataFrame(records).groupby("Key", as_index=False).sum()



def reconcile(serv_df, well_df):
    final = pd.merge(serv_df, well_df, on="Key", how="left").fillna(0)
    final["Diff"] = final["Serv"] - final["Well"]

    return final[["Name", "Serv", "Well", "Diff"]].sort_values(
        by="Diff", ascending=False
    )


col1, col2 = st.columns(2)

with col1:
    serv_file = st.file_uploader(
        "1. Upload Servtracker Report",
        type=["xlsx"],
        key="serv"
    )

with col2:
    well_file = st.file_uploader(
        "2. Upload WellSky Report",
        type=["xls", "xlsx", "csv"],
        key="well"
    )


if serv_file and well_file:
    try:
        with st.spinner("Processing files..."):
            df_serv = process_servtracker(serv_file)
            df_well = process_wellsky(well_file)

            if df_serv.empty:
                st.error("No valid records found in Servtracker file.")
                st.stop()

            result = reconcile(df_serv, df_well)

        matched = (result["Well"] > 0).sum()
        discrepancies = (result["Diff"] != 0).sum()

        c1, c2, c3 = st.columns(3)
        c1.metric("Servtracker Records", len(df_serv))
        c2.metric("WellSky Matches", matched)
        c3.metric("Discrepancies", discrepancies)

        st.success("Reconciliation completed successfully")
        st.dataframe(result, use_container_width=True)

        csv_data = result.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Download Reconciliation Report",
            data=csv_data,
            file_name="reconciliation_report.csv",
            mime="text/csv"
        )

    except Exception as e:
        st.error(f"Processing failed: {str(e)}")
