import streamlit as st
import pandas as pd
import numpy as np
import math
import io
import os

st.set_page_config(page_title="Estimator Tool (Streamlit)", layout="wide")

# ---------------------------
# Configuration
# ---------------------------
DEFAULT_CSV_FILENAME = "estimator_data.csv"

REQUIRED_COLUMNS = [
    "Platform Capability",
    "Category",
    "Complexity",
    "Estimated Build Days"
]

# Phases (global sliders); values are fractions (0..1) in the math
PHASES = ["Plan", "Analyse", "Design", "Build", "UAT", "Deploy"]
DEFAULT_PHASES = {  # starting suggestions (fractions)
    "Plan": 0.15,
    "Analyse": 0.10,
    "Design": 0.15,
    "Build": 0.35,
    "UAT": 0.15,
    "Deploy": 0.10
}
# UI min/max (fractions) for each phase if file doesn't provide *_Min/*_Max
DEFAULT_MIN = {
    "Plan": 0.10, "Analyse": 0.05, "Design": 0.10, "Build": 0.30, "UAT": 0.10, "Deploy": 0.05
}
DEFAULT_MAX = {
    "Plan": 0.20, "Analyse": 0.15, "Design": 0.20, "Build": 0.40, "UAT": 0.20, "Deploy": 0.15
}

# Embedded default CSV so the app runs even if no file exists
DEFAULT_CSV = """Platform Capability,Category,Complexity,Estimated Build Days,Plan_Min,Plan_Max,Analyse_Min,Analyse_Max,Design_Min,Design_Max,Build_Min,Build_Max,UAT_Min,UAT_Max,Deploy_Min,Deploy_Max
Voice,Voicebot - NLU,Simple,10,0.10,0.20,0.10,0.20,0.10,0.25,0.35,0.40,0.10,0.20,0.10,0.20
Voice,Voicebot - NLU,Medium,16,0.10,0.20,0.10,0.20,0.12,0.25,0.35,0.42,0.08,0.20,0.08,0.18
Voice,Voicebot - NLU,Complex,24,0.10,0.25,0.12,0.22,0.15,0.28,0.35,0.45,0.08,0.18,0.05,0.15
Voice,IVR,Medium,18,0.10,0.20,0.08,0.18,0.10,0.20,0.35,0.40,0.12,0.22,0.10,0.20
Chat,Chatbot - FAQ,Simple,8,0.08,0.18,0.08,0.18,0.12,0.22,0.35,0.40,0.15,0.25,0.07,0.15
Chat,Agent Assist,Complex,20,0.10,0.25,0.10,0.22,0.12,0.25,0.35,0.45,0.12,0.22,0.06,0.15
Email,Auto Triage,Simple,6,0.08,0.18,0.08,0.18,0.10,0.20,0.35,0.40,0.15,0.25,0.10,0.20
Email,Auto Triage,Medium,10,0.08,0.20,0.08,0.20,0.12,0.22,0.35,0.42,0.12,0.22,0.08,0.18
Social,Care Routing,Medium,12,0.10,0.20,0.10,0.20,0.10,0.20,0.35,0.42,0.10,0.20,0.10,0.20
"""

# ---------------------------
# Helpers
# ---------------------------
def ensure_required(df: pd.DataFrame) -> bool:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        st.error(f"Missing required columns: {missing}")
        return False
    return True

def get_phase_limits(df_slice: pd.DataFrame):
    """Return min/max slider limits for each phase (fractions 0..1).
       Prefer *_Min/*_Max columns if present for the selected items; else defaults.
    """
    limits = {}
    for ph in PHASES:
        min_col = f"{ph}_Min"
        max_col = f"{ph}_Max"
        if min_col in df_slice.columns and max_col in df_slice.columns and not df_slice.empty:
            limits[ph] = (float(df_slice[min_col].min()), float(df_slice[max_col].max()))
        else:
            limits[ph] = (DEFAULT_MIN[ph], DEFAULT_MAX[ph])
    return limits

def normalize_to_100(phase_dict: dict) -> dict:
    total = sum(phase_dict.values())
    if total == 0:
        return phase_dict
    return {k: (v / total) for k, v in phase_dict.items()}

def percent_slider(label, min_frac, max_frac, default_frac):
    """Show a slider in percentage 0..100 but return a fraction 0..1."""
    min_pct = int(round(min_frac * 100))
    max_pct = int(round(max_frac * 100))
    default_pct = int(round(default_frac * 100))
    val_pct = st.slider(label, min_value=min_pct, max_value=max_pct, value=default_pct, step=1, format="%d%%")
    return val_pct / 100.0

@st.cache_data
def read_csv_bytes(file_bytes: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(file_bytes))

@st.cache_data
def read_csv_path(path: str) -> pd.DataFrame:
    return pd.read_csv(path)

def get_excel_writer(buf: io.BytesIO):
    """Return a Pandas ExcelWriter using xlsxwriter if available, else openpyxl."""
    try:
        import xlsxwriter  # noqa: F401
        return pd.ExcelWriter(buf, engine="xlsxwriter")
    except Exception:
        return pd.ExcelWriter(buf, engine="openpyxl")

# ---------------------------
# Data load
# ---------------------------
st.sidebar.title("Data Source")
uploaded = st.sidebar.file_uploader("Upload CSV to override default", type=["csv"])

df = None
if uploaded is not None:
    try:
        df = read_csv_bytes(uploaded.getvalue())
        st.sidebar.success("Using uploaded CSV.")
    except Exception as e:
        st.sidebar.error(f"Could not read uploaded file: {e}")

if df is None:
    # Try local CSV
    if os.path.exists(DEFAULT_CSV_FILENAME):
        try:
            df = read_csv_path(DEFAULT_CSV_FILENAME)
            st.sidebar.info(f"Using local '{DEFAULT_CSV_FILENAME}'.")
        except Exception as e:
            st.sidebar.error(f"Could not read '{DEFAULT_CSV_FILENAME}': {e}")
    # Fallback to embedded CSV
    if df is None:
        df = pd.read_csv(io.StringIO(DEFAULT_CSV))
        st.sidebar.warning("No CSV found. Using embedded sample data.")

if not ensure_required(df):
    st.stop()

# Derive selection key for joining & cart uniqueness
df["SelectionKey"] = (
    df["Platform Capability"].astype(str) + " | " +
    df["Category"].astype(str) + " | " +
    df["Complexity"].astype(str)
)

# ---------------------------
# UI – selection & cart
# ---------------------------
st.title("Estimator Tool (Python • Streamlit)")
st.caption("Pick multiple features (Capability → Category → Complexity), set per-item quantities, tune phase allocations, add fixed 5% contingency, and export.")

c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.0, 0.8])
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

sel_row = df[(df["Platform Capability"] == chosen_cap) &
             (df["Category"] == chosen_cat) &
             (df["Complexity"] == chosen_cpx)]
if sel_row.empty:
    st.error("No matching row in your data for the chosen combination.")
    st.stop()

base_days = float(sel_row["Estimated Build Days"].iloc[0])
st.markdown(f"**Estimated Build Days (per unit):** {base_days}")

# Cart state
if "cart" not in st.session_state:
    st.session_state.cart = pd.DataFrame(
        columns=["SelectionKey", "Platform Capability", "Category",
                 "Complexity", "Estimated Build Days", "Quantity"]
    )

if st.button("➕ Add to Estimate"):
    key = sel_row["SelectionKey"].iloc[0]
    existing = st.session_state.cart.index[st.session_state.cart["SelectionKey"] == key].tolist()
    if existing:
        idx = existing[0]
        st.session_state.cart.at[idx, "Quantity"] = int(st.session_state.cart.at[idx, "Quantity"]) + int(chosen_qty)
    else:
        st.session_state.cart = pd.concat([
            st.session_state.cart,
            pd.DataFrame([{
                "SelectionKey": key,
                "Platform Capability": chosen_cap,
                "Category": chosen_cat,
                "Complexity": chosen_cpx,
                "Estimated Build Days": base_days,
                "Quantity": int(chosen_qty)
            }])
        ], ignore_index=True)

st.subheader("Selected Items")
if st.session_state.cart.empty:
    st.info("Your estimate is empty. Add items above.")
else:
    edited = st.data_editor(
        st.session_state.cart,
        key="cart_editor",
        num_rows="fixed",
        column_config={
            "Estimated Build Days": st.column_config.NumberColumn(format="%.2f", step=1.0),
            "Quantity": st.column_config.NumberColumn(min_value=1, step=1),
        }
    )
    st.session_state.cart = edited

# ---------------------------
# Phase sliders (global)
# ---------------------------
st.subheader("Phase Allocation (Percent of Total Implementation)")

# Limits from selected items if cart not empty; otherwise use current selection
df_for_limits = sel_row if st.session_state.cart.empty else df.merge(
    st.session_state.cart[["SelectionKey"]], on="SelectionKey", how="inner"
).drop_duplicates(subset=["SelectionKey"])

limits = get_phase_limits(df_for_limits)

phase_values = {}
cols = st.columns(len(PHASES))
for i, ph in enumerate(PHASES):
    with cols[i]:
        min_v, max_v = limits[ph]  # fractions
        default_v = min(max(DEFAULT_PHASES[ph], min_v), max_v)
        phase_values[ph] = percent_slider(f"{ph} %", min_v, max_v, default_v)

l1, l2 = st.columns(2)
with l1:
    normalize = st.toggle("Normalize phases to 100%", value=True,
                          help="Scales all phases so they sum to 100%.")
with l2:
    contingency = 0.05
    st.write("**Contingency:** Fixed at 5%")

if normalize:
    phase_values = normalize_to_100(phase_values)

# ---------------------------
# Calculations
# ---------------------------
if st.session_state.cart.empty:
    cart_df = pd.DataFrame([{
        "SelectionKey": sel_row["SelectionKey"].iloc[0],
        "Platform Capability": chosen_cap,
        "Category": chosen_cat,
        "Complexity": chosen_cpx,
        "Estimated Build Days": base_days,
        "Quantity": int(chosen_qty)
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

# Add fixed contingency and round up (ceiling)
total_impl_days_with_cont = total_impl_days * (1 + contingency)
project_timeline = math.ceil(total_impl_days_with_cont)

# ---------------------------
# Display
# ---------------------------
st.markdown("---")
m1, m2, m3 = st.columns(3)
with m1:
    st.metric("Total Build Effort (days)", f"{total_build_days:.2f}")
with m2:
    st.metric("Total Implementation (days)", f"{total_impl_days:.2f}")
with m3:
    st.metric("Project Timeline (incl. fixed 5% contingency)", f"{project_timeline} days")

st.markdown("### Table 1 — Items & Build Effort")
st.dataframe(cart_df[["Platform Capability","Category","Complexity","Estimated Build Days","Quantity","Build Effort Days"]])

st.markdown("### Table 2 — Implementation Breakdown by Phase")
disp_df = breakdown_df.copy()
disp_df["Percent"] = (disp_df["Percent"]*100).round(2).astype(str) + "%"
disp_df["Days"] = disp_df["Days"].round(2)
st.dataframe(disp_df)

st.markdown(f"**Sum of phase days:** {breakdown_df['Days'].sum():.2f} (should equal Total Implementation)")

# ---------------------------
# Export
# ---------------------------
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
            "Value": [total_build_days, total_impl_days, 0.05, project_timeline]
        })
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
    st.download_button("Download Excel Workbook", data=buf.getvalue(),
                       file_name="estimate_export.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.caption("Upload a CSV from the sidebar or place 'estimator_data.csv' next to app.py. Optional *_Min/*_Max columns constrain phase slider ranges per selection. Contingency fixed at 5%.")
