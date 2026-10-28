"""Construieste fisierul Excel (2 foi) din cele doua tabele Pandas."""
from datetime import datetime
from io import BytesIO

import pandas as pd
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

MONEY_COLUMNS = {"subtotal", "vat_amount", "total", "unit_price", "line_total"}


def _format_sheet(sheet):
    sheet.freeze_panes = "A2"  # primul rand ramane vizibil la scroll

    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for index, column in enumerate(sheet.columns, start=1):
        header = column[0].value

        # latimea coloanei = cea mai lunga valoare + putin spatiu
        longest = 0
        for cell in column:
            if cell.value is None:
                continue
            length = 10 if isinstance(cell.value, datetime) else len(str(cell.value))
            longest = max(longest, length)
        sheet.column_dimensions[get_column_letter(index)].width = min(max(longest + 2, 10), 50)

        for cell in column[1:]:
            if header in MONEY_COLUMNS:
                cell.number_format = "#,##0.00"
            elif isinstance(cell.value, datetime):
                cell.number_format = "YYYY-MM-DD"  # data fara ora


def to_excel_bytes(invoices, line_items):
    """Returneaza continutul fisierului .xlsx (bytes), gata pentru st.download_button."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl", datetime_format="YYYY-MM-DD") as writer:
        invoices.to_excel(writer, sheet_name="Invoices", index=False)
        line_items.to_excel(writer, sheet_name="Line items", index=False)
        _format_sheet(writer.sheets["Invoices"])
        _format_sheet(writer.sheets["Line items"])
    return buffer.getvalue()
