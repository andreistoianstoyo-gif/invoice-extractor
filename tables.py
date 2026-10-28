"""Partea de Pandas: construieste tabelele din rezultatele extrase si valideaza totalurile."""
import pandas as pd

TOLERANCE = 0.02  # diferenta acceptata la verificarea subtotal + TVA = total

INVOICE_COLUMNS = [
    "source_file", "supplier_name", "supplier_tax_id", "invoice_number",
    "invoice_date", "due_date", "currency", "subtotal", "vat_amount", "total",
]
LINE_COLUMNS = [
    "source_file", "invoice_number", "description", "quantity", "unit_price", "line_total",
]
DATE_COLUMNS = ["invoice_date", "due_date"]
NUMBER_COLUMNS = ["subtotal", "vat_amount", "total"]
LINE_NUMBER_COLUMNS = ["quantity", "unit_price", "line_total"]


def clean_types(df):
    """Date -> datetime, sume -> numere. Valorile invalide devin NaT/NaN, nu erori."""
    df = df.copy()
    for col in DATE_COLUMNS:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in NUMBER_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def add_check(df):
    """Adauga coloana 'check': OK / CHECK (suma nu se potriveste) / MISSING (lipseste o valoare)."""
    df = df.copy()
    difference = (df["subtotal"] + df["vat_amount"] - df["total"]).abs()
    missing = df[NUMBER_COLUMNS].isna().any(axis=1)

    df["check"] = "OK"
    df.loc[difference > TOLERANCE, "check"] = "CHECK"
    df.loc[missing, "check"] = "MISSING"  # MISSING are prioritate fata de CHECK
    return df


def build_tables(results):
    """results = lista de dictionare (cate unul per factura). Returneaza (invoices, line_items)."""
    invoice_rows = []
    line_rows = []

    for result in results:
        invoice_rows.append({col: result.get(col) for col in INVOICE_COLUMNS})
        for item in result.get("line_items") or []:
            line_rows.append({
                "source_file": result.get("source_file"),
                "invoice_number": result.get("invoice_number"),
                "description": item.get("description"),
                "quantity": item.get("quantity"),
                "unit_price": item.get("unit_price"),
                "line_total": item.get("line_total"),
            })

    invoices = clean_types(pd.DataFrame(invoice_rows, columns=INVOICE_COLUMNS))
    invoices = add_check(invoices)

    line_items = pd.DataFrame(line_rows, columns=LINE_COLUMNS)
    for col in LINE_NUMBER_COLUMNS:
        line_items[col] = pd.to_numeric(line_items[col], errors="coerce")

    return invoices, line_items


def totals_text(df):
    """Suma totala pe moneda, ca text: '2,644.50 EUR | 340.20 GBP'."""
    totals = df.groupby("currency")["total"].sum()
    if totals.empty:
        return "-"
    return " | ".join(f"{value:,.2f} {currency}" for currency, value in totals.items())
