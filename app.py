import streamlit as st
import pandas as pd
import re
import difflib

st.set_page_config(page_title="Data Matcher Pro", layout="wide")
st.title("📊 Servtracker vs WellSky Reconciliation")

# =========================================================
# 1. NAME STANDARDIZATION
# =========================================================
def get_clean_key(last, first):
    def clean(text):
        text = str(text).lower()

        # remove suffixes
        text = re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', text)

        # keep only letters
        text = re.sub(r'[^a-z]', '', text)

        return text

    first_word = str(first).split()[0] if first else ""
    return clean(last) + clean(first_word)


# =========================================================
# 2. SERVTRACKER READER
# =========================================================
def process_servtracker(file):
    if file.name.lower().endswith(".csv"):
        df = pd.read_csv(file, header=None, encoding="latin1")
    else:
        df = pd.read_excel(file, header=None)

    totals_col = None

    # find Totals column in first few rows
    for row_idx in range(min(10, len(df))):
        row_vals = [str(x).strip() for x in df.iloc[row_idx]]

        for i, val in enumerate(row_vals):
            if val.lower() == "totals":
                totals_col = i
                break

        if totals_col is not None:
            break

    if totals_col is None:
        totals_col = df.shape[1] - 1

    records = []

    for _, row in df.iloc[5:].iterrows():
        name = str(row.iloc[0]).strip()

        if "," not in name:
            continue

        if "total" in name.lower():
            continue

        try:
            parts = name.split(",")

            last = parts[0].strip()
            first = parts[1].strip()

            units = pd.to_numeric(row.iloc[totals_col], errors="coerce")

            if pd.notna(units) and units > 0:
                records.append({
                    "Name": name,
                    "Key": get_clean_key(last, first),
                    "Serv": float(units)
                })

        except:
            continue

    return pd.DataFrame(records)


# =========================================================
# 3. WELLSKY STAIRCASE PARSER
# =========================================================
def scan_wellsky(file):
    if file.name.lower().endswith(".csv"):
        df = pd.read_csv(file, header=None, encoding="latin1")
    else:
        df = pd.read_excel(file, header=None)

    records = []
    current_key = None

    for _, row in df.iterrows():
        cells = [str(x).strip() for x in row.values if pd.notna(x)]
        row_text = " ".join(cells).lower()

        # ---------------------------
        # STEP 1: detect name row
        # ---------------------------
        for cell in cells:
            if "," in cell and any(c.isalpha() for c in cell):
                if "sub total" not in cell.lower():
                    parts = cell.split(",")

                    if len(parts) >= 2:
                        last = parts[0].strip()
                        first = parts[1].strip()

                        current_key = get_clean_key(last, first)
                        break

        # ---------------------------
        # STEP 2: detect subtotal row
        # ---------------------------
        if current_key and "sub total" in row_text:
            nums = []

            for cell in cells:
                clean_num = re.sub(r"[^\d.]", "", cell)

                if clean_num and clean_num != ".":
                    try:
                        val = float(clean_num)

                        if 0 < val < 1000:
                            nums.append(val)

                    except:
                        pass

            if nums:
                records.append({
                    "Key": current_key,
                    "Well": nums[-1]
                })

                current_key = None

    if not records:
        return pd.DataFrame(columns=["Key", "Well"])

    return (
        pd.DataFrame(records)
        .groupby("Key", as_index=False)
        .sum()
    )


# =========================================================
# 4. RECONCILIATION
# =========================================================
def reconcile(df_s, df_w):
    final = pd.merge(df_s, df_w, on="Key", how="left").fillna(0)

    unmatched = final[final["Well"] == 0].index

    if not df_w.empty and len(unmatched) > 0:
        w_keys = df_w["Key"].tolist()

        for idx in unmatched:
            s_key = final.at[idx, "Key"]

            match = difflib.get_close_matches(
                s_key,
                w_keys,
                n=1,
                cutoff=0.8
            )

            if match:
                match_key = match[0]

                units = df_w.loc[
                    df_w["Key"] == match_key,
                    "Well"
                ].values[0]

                final.at[idx, "Well"] = units

    final["Diff"] = final["Serv"] - final["Well"]

    return final


# =========================================================
# 5. STREAMLIT UI
# =========================================================
col1, col2 = st.columns(2)

with col1:
    serv_file = st.file_uploader(
        "1. Upload Servtracker",
        type=["csv", "xls", "xlsx"]
    )

with col2:
    well_file = st.file_uploader(
        "2. Upload WellSky",
        type=["csv", "xls", "xlsx"]
    )

if serv_file and well_file:
    with st.spinner("Reconciling reports..."):
        df_s = process_servtracker(serv_file)
        df_w = scan_wellsky(well_file)

        if df_s.empty:
            st.error("Servtracker file could not be parsed.")
            st.stop()

        final = reconcile(df_s, df_w)

        discrepancies = final[final["Diff"] != 0]
        perfect_matches = len(final) - len(discrepancies)

        c1, c2, c3 = st.columns(3)

        c1.metric("Total Clients", len(final))
        c2.metric("Perfect Matches", perfect_matches)
        c3.metric("Discrepancies", len(discrepancies))

        st.subheader("Discrepancy Report")

        if discrepancies.empty:
            st.success("Perfect match — no discrepancies.")
        else:
            st.dataframe(
                discrepancies[
                    ["Name", "Serv", "Well", "Diff"]
                ].sort_values("Diff", ascending=False),
                use_container_width=True
            )

        csv = final.to_csv(index=False).encode("utf-8")

        st.download_button(
            "📥 Download Final Report",
            csv,
            "reconciliation_report.csv",
            "text/csv"
        )
