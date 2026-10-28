"""Invoice Data Extractor - interfata Streamlit.

Aici este doar interfata. Apelul catre AI este in extractor.py,
tabelele Pandas in tables.py, iar fisierul Excel in excel_export.py.
"""
import json
import os
from pathlib import Path

import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()  # citeste .env daca exista (doar pentru rulare locala)
except ImportError:
    pass

from excel_export import to_excel_bytes
from tables import add_check, build_tables, clean_types, totals_text

# Extragerea "Live" foloseste API-ul Anthropic si costa bani (cheie API).
# False = aplicatie doar demo, gratuita. True = apare si modul Live
# (atunci ai nevoie de `anthropic` in requirements.txt si de o cheie API).
ENABLE_LIVE = False

st.set_page_config(page_title="Invoice Data Extractor", page_icon="🧾", layout="wide")

SAMPLE_DIR = Path(__file__).parent / "sample_invoices"
MAX_FILES = 10
DEMO = "Demo (sample invoices, no API key needed)"
LIVE = "Live (upload your own invoices)"


@st.cache_data
def load_demo_results():
    path = SAMPLE_DIR / "sample_results.json"
    return json.loads(path.read_text(encoding="utf-8"))


def get_api_key(sidebar_key):
    """Ordinea: cheia din bara laterala, apoi st.secrets, apoi variabila de mediu."""
    if sidebar_key:
        return sidebar_key.strip()
    try:
        secret = st.secrets.get("ANTHROPIC_API_KEY")
        if secret:
            return secret
    except Exception:
        pass  # nu exista fisier de secrets, e normal la rularea locala
    return os.environ.get("ANTHROPIC_API_KEY", "")


def run_extraction(files, api_key):
    """Proceseaza fisierele pe rand. Un fisier cu eroare nu opreste restul."""
    from extractor import ExtractionError, extract_invoice, make_client  # doar in modul Live

    client = make_client(api_key)
    results, errors = [], []
    progress = st.progress(0.0, text="Starting...")

    for number, uploaded in enumerate(files, start=1):
        progress.progress((number - 1) / len(files), text=f"Reading {uploaded.name} ({number}/{len(files)})")
        try:
            data = extract_invoice(client, uploaded.name, uploaded.getvalue())
            data["source_file"] = uploaded.name
            results.append(data)
        except ExtractionError as error:
            errors.append(f"{uploaded.name}: {error}")

    progress.progress(1.0, text="Done")
    return results, errors


# --- Pagina -----------------------------------------------------------------
st.title("🧾 Invoice Data Extractor")
st.write(
    "An AI model reads the key fields from invoices (PDF or image); you review and correct "
    "the table and download a clean Excel file."
)

if ENABLE_LIVE:
    st.sidebar.header("Settings")
    mode = st.sidebar.radio("Mode", [DEMO, LIVE])
else:
    mode = DEMO
    st.sidebar.header("About this demo")
    st.sidebar.write(
        "The results on this page were extracted in advance from 4 fictional sample invoices. "
        "Try editing a value in the table: the totals and the checks update automatically."
    )
    st.sidebar.caption("Want this for your own invoices or documents? Message me on Fiverr.")

if mode == DEMO:
    results = load_demo_results()
    errors = []
    editor_key = "editor_demo"
    st.info(
        "Demo with 4 fictional sample invoices (2 English, 2 Romanian). "
        "The last one has a deliberate arithmetic mismatch, so you can see how the check works."
    )
    expander_label = (
        "Want to try Live mode with these sample files?" if ENABLE_LIVE
        else "View the original sample invoices (PDF)"
    )
    with st.expander(expander_label):
        for pdf in sorted(SAMPLE_DIR.glob("*.pdf")):
            st.download_button(f"Download {pdf.name}", pdf.read_bytes(), file_name=pdf.name,
                               mime="application/pdf", key=f"sample_{pdf.name}")
else:
    sidebar_key = st.sidebar.text_input("Anthropic API key", type="password")
    st.sidebar.caption("Your key is used only for this session and is not stored.")
    api_key = get_api_key(sidebar_key)

    uploaded_files = st.file_uploader(
        "Upload invoices (PDF, PNG, JPG)", type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )
    if len(uploaded_files) > MAX_FILES:
        st.warning(f"Maximum {MAX_FILES} files per run. Only the first {MAX_FILES} will be processed.")
        uploaded_files = uploaded_files[:MAX_FILES]
    if not api_key:
        st.info("Add your Anthropic API key in the sidebar to use Live mode.")

    if st.button("Extract data", type="primary", disabled=not (api_key and uploaded_files)):
        run_results, run_errors = run_extraction(uploaded_files, api_key)
        st.session_state["live_results"] = run_results
        st.session_state["live_errors"] = run_errors
        st.session_state["run_id"] = st.session_state.get("run_id", 0) + 1

    results = st.session_state.get("live_results", [])
    errors = st.session_state.get("live_errors", [])
    editor_key = f"editor_live_{st.session_state.get('run_id', 0)}"

for message in errors:
    st.error(message)

if not results:
    st.stop()

invoices, line_items = build_tables(results)

tab_invoices, tab_lines = st.tabs(["Invoices", "Line items"])

with tab_invoices:
    st.caption("Double-click a cell to correct a value. The numbers and checks below update automatically.")
    edited = st.data_editor(
        invoices,
        key=editor_key,
        hide_index=True,
        use_container_width=True,
        disabled=["source_file", "check"],
        column_config={
            "invoice_date": st.column_config.DateColumn("invoice_date", format="YYYY-MM-DD"),
            "due_date": st.column_config.DateColumn("due_date", format="YYYY-MM-DD"),
            "subtotal": st.column_config.NumberColumn("subtotal", format="%.2f"),
            "vat_amount": st.column_config.NumberColumn("vat_amount", format="%.2f"),
            "total": st.column_config.NumberColumn("total", format="%.2f"),
        },
    )
    # dupa fiecare corectie recalculam verificarea
    edited = add_check(clean_types(edited.drop(columns=["check"])))

    need_review = int((edited["check"] != "OK").sum())
    col1, col2, col3 = st.columns(3)
    col1.metric("Invoices", len(edited))
    col2.metric("Total amount", totals_text(edited))
    col3.metric("Need review", need_review)

    if need_review:
        st.warning(
            f"{need_review} invoice(s) need a check: subtotal + VAT does not match the total, "
            "or a value is missing. Correct them in the table above."
        )
        st.dataframe(
            edited.loc[edited["check"] != "OK", ["source_file", "invoice_number", "subtotal", "vat_amount", "total", "check"]],
            hide_index=True,
            use_container_width=True,
            column_config={
                "subtotal": st.column_config.NumberColumn("subtotal", format="%.2f"),
                "vat_amount": st.column_config.NumberColumn("vat_amount", format="%.2f"),
                "total": st.column_config.NumberColumn("total", format="%.2f"),
            },
        )
    else:
        st.success("All invoices pass the arithmetic check.")

with tab_lines:
    st.dataframe(
        line_items,
        hide_index=True,
        use_container_width=True,
        column_config={
            "unit_price": st.column_config.NumberColumn("unit_price", format="%.2f"),
            "line_total": st.column_config.NumberColumn("line_total", format="%.2f"),
        },
    )

st.download_button(
    "Download Excel",
    data=to_excel_bytes(edited, line_items),
    file_name="invoices.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
st.caption("AI can make mistakes: always review the values before using them.")
