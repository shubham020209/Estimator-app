import streamlit as st
import pandas as pd
import numpy as np
import math
import io
import os

st.set_page_config(page_title="Estimator Tool", layout="wide")

# =========================================
# Fixed data source (no upload)
# =========================================
# The app will look for this file in the current working directory.
# If you prefer an absolute path, set DEFAULT_EXCEL_PATH accordingly.
DEFAULT_EXCEL_PATH = "Estimator File.xlsx"

# If your file lives elsewhere, you can add a fallback:
FALLBACK_EXCEL_PATH = "/mnt/data/Estimator File.xlsx"

# =========================================
# Config / Schema
# =========================================
REQUIRED_POSITIONS = {
    # 0-based positions mapped to logical names
    1: "Platform Capability",   # Column B
    2: "Category",              # Column C
    3: "Definition",            # Column D (assumed)
    4: "Complexity",            # Column E
    5: "Estimated Build Days"   # Column F
}

PHASES = ["Plan", "Analyse", "Design", "Build", "UAT", "Deploy"]

DEFAULT_PHASES = {  # initial suggestions (fractions)
    "Plan": 0.15,
    "Analyse": 0.10,
    "Design": 0.15,
    "Build": 0.35,
    "UAT": 0.15,
    "Deploy": 0.10,
}

# UI min/max (fractions). If your Excel includes *_Min/*_Max columns for phases,
# they’ll be used automatically; otherwise these defaults apply.
DEFAULT_MIN = {
    "Plan": 0.10, "Analyse": 0.05, "Design": 0.10, "Build": 0.30, "UAT": 0.10, "Deploy": 0.05
}
DEFAULT_MAX = {
    "Plan": 0.20, "Analyse": 0.15, "Design": 0.20, "Build": 0.40, "UAT": 0.20, "Deploy": 0.15
}

FIXED_CONTINGENCY = 0.05  # 5%

# =========================================
# Helpers
# =========================================
def load_fixed_excel() -> pd.DataFrame:
    """Load the fixed Excel file, selecting needed columns by position."""
    path = DEFAULT_EXCEL_PATH if os.path.exists(DEFAULT_EXCEL_PATH) else FALLBACK_EXCEL_PATH
    if not os.path.exists(path):
        st.error(f"Could not find the fixed Excel file. Expected at '{DEFAULT_EXCEL_PATH}'"
                 f"{' or ' + FALLBACK_EXCEL_PATH if FALLBACK_EXCEL_PATH else ''}.")
        st.stop()

    df_raw = pd.read_excel(path, header=0)  # read with first row as headers (ignored for mapping)
    # Ensure enough columns
    max_needed_idx = max(REQUIRED_POSITIONS.keys())
    if df_raw.shape[1] <= max_needed_idx:
        st.error("The Excel file does not have the expected number of columns (A..F).")
        st.stop()

    # Map by position
    new_cols = {}
    for pos, name in REQUIRED_POSITIONS.items():
        new_cols[name] = df_raw.iloc[:, pos]

    df = pd.DataFrame(new_cols)

    # Optional phase min/max columns (if present in your workbook—by header names)
    # Example expected headers: Plan_Min, Plan_Max, Analyse_Min, Analyse_Max, ...
    for ph in PHASES:
        min_col = f"{ph}_Min"
        max_col = f"{ph}_Max"
        if min_col in df_raw.columns and max_col in df_raw.columns:
            df[min_col] = df_raw[min_col]
            df[max_col] = df_raw[max_col]

    # Basic validation
    for col in ["Platform Capability", "Category", "Complexity", "Estimated Build Days"]:
        if col not in df.columns:
            st.error(f"Missing required column: {col}")
            st.stop()

    # Ensure numeric type for build days
    df["Estimated Build Days"] = pd.to_numeric(df["Estimated Build Days"], errors="coerce")
    df = df.dropna(subset=["Estimated Build Days"])

    # Derive selection key
    df["SelectionKey"] = (
        df["Platform Capability"].astype(str) + " | " +
        df["Category"].astype(str) + " | " +
        df["Complexity"].astype(str)
    )

    return df

def get_phase_limits(df_slice: pd.DataFrame):
    """Return min/max slider limits for each phase (fractions 0..1).
       Prefer *_Min/*_Max columns if present for the selected items; else defaults.
    """
    limits = {}
    for ph in PHASES:
        min_col = f"{ph}_Min"
        max_col = f"{ph}_Max"
        if min_col in df_slice.columns and max_col in df_slice.columns and not df_slice.empty:
            # take overall min/max across selected items
            try:
                limits[ph] = (float(df_slice[min_col].min()), float(df_slice[max_col].max()))
            except Exception:
                limits[ph] = (DEFAULT_MIN[ph], DEFAULT_MAX[ph])
        else:
            limits[ph] = (DEFAULT_MIN[ph], DEFAULT_MAX[ph])
    return limits

def normalize_to_100(phase_dict: dict) -> dict:
    total = sum(phase_dict.values())
    if total == 0:
        return phase_dict
    return {k: (v / total) for k, v in phase_dict.items()}

def percent_slider(label: str, min_frac: float, max_frac: float, default_frac: float) -> float:
    """Show a slider in percentage 0..100 but return a fraction 0..1."""
    min_pct = int(round(min_frac * 100))
    max_pct = int(round(max_frac * 100))
    default_pct = int(round(default_frac * 100))
    val_pct = st.slider(label, min_value=min_pct, max_value=max_pct,
                        value=default_pct, step=1, format="%d%%")
    return val_pct / 100.0

def get_excel_writer(buf: io.BytesIO):
    """Return a Pandas ExcelWriter using xlsxwriter if available, else openpyxl."""
    try:
        import xlsxwriter  # noqa: F401
        return pd.ExcelWriter(buf, engine="xlsxwriter")
    except Exception:
        return pd.ExcelWriter(buf, engine="openpyxl")

# =========================================
# Load data (fixed file)
# =========================================
df = load_fixed_excel()

# =========================================
# UI – selection & cart
# =========================================
st.title("Estimator Tool (Python • Streamlit)")
st.caption("Fixed data source. Select features, set per-item quantities, tune phase allocations, add fixed 5% contingency, and export.")

c1, c2, c3, c4, c5 = st.columns([1.2, 1.2, 1.0, 0.8, 0.6])
with c1:
    chosen_cap = st.selectbox("Platform Capability", sorted(df["Platform Capability"].dropna().unique()))
f_cat = df[df["Platform Capability"] == chosen_cap]
with c2:
    chosen_cat = st.selectbox("Category", sorted(f_cat["Category"].dropna().unique()))
f_cpx = f_cat[f_cat["Category"] == chosen_cat]
with c3:
    chosen_cpx = st.selectbox("Complexity", sorted(f_cpx["Complexity"].dropna().unique()))
with c4:
    chosen_qty = st.number_input("Quantity", min_value=1, value=1, step=1)
with c5:
    # Pull definition (complexity-dependent) for the selected row
    sel_row_tmp = f_cpx[f_cpx["Complexity"] == chosen_cpx]
    definition_text = ""
    if not sel_row_tmp.empty and "Definition" in sel_row_tmp.columns:
        definition_text = str(sel_row_tmp["Definition"].iloc[0] or "")
    with st.popover("ℹ️ Definition"):
        if definition_text.strip():
            st.write(definition_text)
        else:
            st.write("No definition available for this selection.")

# Validate selected row
sel_row = df[(df["Platform Capability"] == chosen_cap) &
             (df["Category"] == chosen_cat) &
             (df["Complexity"] == chosen_cpx)]
if sel_row.empty:
    st.error("No matching row in the Excel for the chosen combination.")
    st.stop()

base_days = float(sel_row["Estimated Build Days"].iloc[0])
st.markdown(f"**Estimated Build Days (per unit):** {base_days}")

# Cart state
if "cart" not in st.session_state:
    st.session_state.cart = pd.DataFrame(
        columns=["SelectionKey", "Platform Capability", "Category",
                 "Complexity", "Estimated Build Days", "Quantity", "Definition"]
    )

if st.button("➕ Add to Estimate"):
    key = sel_row["SelectionKey"].iloc[0]
    existing = st.session_state.cart.index[st.session_state.cart["SelectionKey"] == key].tolist()
    # definition from this selected row (if present)
    defn = ""
    if "Definition" in sel_row.columns:
        defn = str(sel_row["Definition"].iloc[0] or "")

    if existing:
        idx = existing[0]
        st.session_state.cart.at[idx, "Quantity"] = int(st.session_state.cart.at[idx, "Quantity"]) + int(chosen_qty)
        # keep definition as-is (or refresh from latest selection, either is fine)
    else:
        st.session_state.cart = pd.concat([
            st.session_state.cart,
            pd.DataFrame([{
                "SelectionKey": key,
                "Platform Capability": chosen_cap,
                "Category": chosen_cat,
                "Complexity": chosen_cpx,
                "Estimated Build Days": base_days,
                "Quantity": int(chosen_qty),
                "Definition": defn
            }])
        ], ignore_index=True)

st.subheader("Selected Items")
if st.session_state.cart.empty:
    st.info("Your estimate is empty. Add items above.")
else:
    # Include definition in the table (read-only text)
    edited = st.data_editor(
        st.session_state.cart,
        key="cart_editor",
        num_rows="fixed",
        column_config={
            "Estimated Build Days": st.column_config.NumberColumn(format="%.2f", step=1.0),
            "Quantity": st.column_config.NumberColumn(min_value=1, step=1),
            "Definition": st.column_config.TextColumn(help="Complexity-dependent feature definition")
        }
    )
    st.session_state.cart = edited

# =========================================
# Phase sliders (global)
# =========================================
st.subheader("Phase Allocation (Percent of Total Implementation)")

# Use selected items for slider limits; if cart empty, use the current selection
df_for_limits = sel_row if st.session_state.cart.empty else df.merge(
    st.session_state.cart[["SelectionKey"]], on="SelectionKey", how="inner"
).drop_duplicates(subset=["SelectionKey"])

limits = get_phase_limits(df_for_limits)

phase_values = {}
cols = st.columns(len(PHASES))
for i, ph in enumerate(PHASES):
    with cols[i]:
        min_v, max_v = limits[ph]  # fractions 0..1
        default_v = min(max(DEFAULT_PHASES[ph], min_v), max_v)
        phase_values[ph] = percent_slider(f"{ph} %", min_v, max_v, default_v)

left, right = st.columns(2)
with left:
    normalize = st.toggle("Normalize phases to 100%", value=True,
                          help="Scales all phases so they sum to 100%.")
with right:
    st.write(f"**Contingency:** Fixed at {int(FIXED_CONTINGENCY*100)}%")

if normalize:
    phase_values = normalize_to_100(phase_values)

# =========================================
# Calculations
# =========================================
if st.session_state.cart.empty:
    cart_df = pd.DataFrame([{
        "SelectionKey": sel_row["SelectionKey"].iloc[0],
        "Platform Capability": chosen_cap,
        "Category": chosen_cat,
        "Complexity": chosen_cpx,
        "Estimated Build Days": base_days,
        "Quantity": int(chosen_qty),
        "Definition": definition_text
    }])
else:
    cart_df = st.session_state.cart.copy()

cart_df["Build Effort Days"] = cart_df["Estimated Build Days"] * cart_df["Quantity"]
total_build_days = float(cart_df["Build Effort Days"].sum())

build_pct = phase_values["Build"]
if build_pct <= 0:
    st.error("Build % must be greater than 0 to compute total implementation days.")
    st.stop()

# Total Implementation = Build Effort / Build%
total_impl_days = total_build_days / build_pct

# Phase breakdown
breakdown = []
for ph in PHASES:
    pct = phase_values[ph]
    days = total_impl_days * pct
    breakdown.append({"Phase": ph, "Percent": pct, "Days": days})
breakdown_df = pd.DataFrame(breakdown)

# Fixed contingency and round up (ceiling)
total_impl_days_with_cont = total_impl_days * (1 + FIXED_CONTINGENCY)
project_timeline = math.ceil(total_impl_days_with_cont)

# =========================================
# Display
# =========================================
st.markdown("---")
m1, m2, m3 = st.columns(3)
with m1:
    st.metric("Total Build Effort (days)", f"{total_build_days:.2f}")
with m2:
    st.metric("Total Implementation (days)", f"{total_impl_days:.2f}")
with m3:
    st.metric("Project Timeline (incl. fixed 5% contingency)", f"{project_timeline} days")

st.markdown("### Table 1 — Items & Build Effort")
st.dataframe(cart_df[[
    "Platform Capability","Category","Complexity","Estimated Build Days","Quantity","Build Effort Days","Definition"
]])

st.markdown("### Table 2 — Implementation Breakdown by Phase")
disp_df = breakdown_df.copy()
disp_df["Percent"] = (disp_df["Percent"]*100).round(2).astype(str) + "%"
disp_df["Days"] = disp_df["Days"].round(2)
st.dataframe(disp_df)

st.markdown(f"**Sum of phase days:** {breakdown_df['Days'].sum():.2f} (should equal Total Implementation)")

# =========================================
# Export
# =========================================
st.markdown("### Export")
c_exp1, c_exp2 = st.columns(2)
with c_exp1:
    csv = cart_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download Items CSV", data=csv, file_name="estimate_items.csv", mime="text/csv")

with c_exp2:
    buf = io.BytesIO()
    with get_excel_writer(buf) as writer:
        cart_df.to_excel(writer, sheet_name="Items", index=False)
        bd = breakdown_df.copy()
        bd.to_excel(writer, sheet_name="Implementation", index=False)
        summary_df = pd.DataFrame({
            "Metric": ["Total Build Days","Total Impl Days","Contingency %","Project Timeline (days)"],
            "Value": [total_build_days, total_impl_days, FIXED_CONTINGENCY, project_timeline]
        })
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
    st.download_button("Download Excel Workbook", data=buf.getvalue(),
                       file_name="estimate_export.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.caption("Data is loaded from a extimator excel. Definition is complexity-dependent and shown via the ℹ️ popover and in the Items table.")
