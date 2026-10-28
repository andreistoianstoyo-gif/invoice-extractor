"""Genereaza 4 facturi fictive (PDF) si sample_results.json cu valorile asteptate.

Rulare:
    python -m pip install -r requirements-dev.txt
    python generate_sample_invoices.py

Toate numele, codurile fiscale si adresele sunt inventate.
"""
import json
import unicodedata
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT_DIR = Path(__file__).parent / "sample_invoices"

# --- Datele celor 4 facturi -------------------------------------------------
# line_items = (descriere, cantitate, pret unitar). Totalurile se calculeaza singure,
# cu o exceptie: factura 4 are un total gresit pus intentionat (total_override).
INVOICES = [
    {
        "file": "invoice_01_en.pdf", "lang": "en", "layout": "A", "accent": "#1F5FA8",
        "date_format": "%d %b %Y",
        "supplier_name": "Brightfield Office Supplies Ltd",
        "supplier_address": "14 Example Road, Sampletown, UK",
        "supplier_tax_id": "GB000000001",
        "customer_name": "Sample Customer Ltd", "customer_address": "1 Demo Street, Testville",
        "invoice_number": "BF-2026-0412",
        "invoice_date": date(2026, 9, 3), "due_date": date(2026, 10, 3),
        "currency": "GBP", "vat_rate": 20,
        "line_items": [
            ("A4 copy paper (box of 5 reams)", 5, 24.50),
            ("Ink cartridge, black", 4, 31.25),
            ("Desk organiser", 2, 18.00),
        ],
    },
    {
        "file": "invoice_02_en.pdf", "lang": "en", "layout": "B", "accent": "#555555",
        "date_format": "%d/%m/%Y",
        "supplier_name": "Harbor & Pine Consulting Ltd",
        "supplier_address": "7 Fictional Quay, Exampleport, Ireland",
        "supplier_tax_id": "IE0000001A",
        "customer_name": "Sample Customer Ltd", "customer_address": "1 Demo Street, Testville",
        "invoice_number": "HP-1087",
        "invoice_date": date(2026, 8, 21), "due_date": date(2026, 9, 20),
        "currency": "EUR", "vat_rate": 23,
        "line_items": [
            ("Data audit workshop (days)", 2, 850.00),
            ("Report preparation", 1, 450.00),
        ],
    },
    {
        "file": "invoice_03_ro.pdf", "lang": "ro", "layout": "A", "accent": "#2E7D32",
        "date_format": "%d.%m.%Y",
        "supplier_name": "Alfa Tehnic Servicii SRL",
        "supplier_address": "Str. Exemplu 10, Oraș Fictiv, România",
        "supplier_tax_id": "RO00000001",
        "customer_name": "Client Exemplu SRL", "customer_address": "Str. Test 5, Oraș Demo",
        "invoice_number": "ATS-00231",
        "invoice_date": date(2026, 10, 2), "due_date": date(2026, 10, 16),
        "currency": "RON", "vat_rate": 21,
        "line_items": [
            ("Mentenanță echipamente", 1, 1200.00),
            ("Piese de schimb", 6, 85.00),
            ("Transport", 1, 90.00),
        ],
    },
    {
        "file": "invoice_04_ro.pdf", "lang": "ro", "layout": "B", "accent": "#8E3B00",
        "date_format": "%d.%m.%Y",
        "supplier_name": "Delta Print Grup SRL",
        "supplier_address": "Bd. Imaginar 22, Oraș Fictiv, România",
        "supplier_tax_id": "RO00000002",
        "customer_name": "Client Exemplu SRL", "customer_address": "Str. Test 5, Oraș Demo",
        "invoice_number": "DP-7714",
        "invoice_date": date(2026, 9, 15), "due_date": date(2026, 9, 29),
        "currency": "RON", "vat_rate": 21,
        "line_items": [
            ("Flyere A5 (bucăți)", 2000, 0.45),
            ("Bannere", 3, 150.00),
        ],
        "total_override": 1663.50,  # corect ar fi 1633.50 -> in demo apare statusul CHECK
    },
]

LABELS = {
    "en": {
        "title": "INVOICE", "supplier": "From", "customer": "Bill to",
        "number": "Invoice no.", "date": "Invoice date", "due": "Due date",
        "desc": "Description", "qty": "Qty", "unit": "Unit price", "amount": "Amount",
        "subtotal": "Subtotal", "vat": "VAT {rate}%", "total": "Total due",
        "tax_id": "VAT no.",
    },
    "ro": {
        "title": "FACTURĂ FISCALĂ", "supplier": "Furnizor", "customer": "Client",
        "number": "Nr. factură", "date": "Data emiterii", "due": "Scadență",
        "desc": "Denumire", "qty": "Cant.", "unit": "Preț unitar", "amount": "Valoare",
        "subtotal": "Total fără TVA", "vat": "TVA {rate}%", "total": "Total de plată",
        "tax_id": "CUI",
    },
}

FONT, FONT_BOLD, UNICODE_OK = "Helvetica", "Helvetica-Bold", False

FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
]


def setup_fonts():
    """Cauta un font cu diacritice. Daca nu gaseste, foloseste Helvetica fara diacritice."""
    global FONT, FONT_BOLD, UNICODE_OK
    for regular, bold in FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            pdfmetrics.registerFont(TTFont("Body", regular))
            pdfmetrics.registerFont(TTFont("Body-Bold", bold))
            FONT, FONT_BOLD, UNICODE_OK = "Body", "Body-Bold", True
            return


def t(text):
    """Scoate diacriticele doar daca fontul nu le poate afisa."""
    if UNICODE_OK:
        return text
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def money(value, lang):
    text = f"{value:,.2f}"                      # 1,234.50
    if lang == "ro":                             # 1.234,50
        text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return text


def number(value):
    return str(int(value)) if float(value).is_integer() else str(value)


def amounts(inv):
    """Calculeaza liniile si totalurile unei facturi."""
    items = []
    for description, qty, unit_price in inv["line_items"]:
        items.append({
            "description": description,
            "quantity": float(qty),
            "unit_price": float(unit_price),
            "line_total": round(qty * unit_price, 2),
        })
    subtotal = round(sum(item["line_total"] for item in items), 2)
    vat = round(subtotal * inv["vat_rate"] / 100, 2)
    total = inv.get("total_override", round(subtotal + vat, 2))
    return items, subtotal, vat, total


def expected_result(inv):
    """Ce ar trebui sa extraga modelul din PDF (folosit in modul demo)."""
    items, subtotal, vat, total = amounts(inv)
    return {
        "source_file": inv["file"],
        "supplier_name": inv["supplier_name"],
        "supplier_tax_id": inv["supplier_tax_id"],
        "invoice_number": inv["invoice_number"],
        "invoice_date": inv["invoice_date"].isoformat(),
        "due_date": inv["due_date"].isoformat(),
        "currency": inv["currency"],
        "subtotal": subtotal,
        "vat_amount": vat,
        "total": total,
        "line_items": items,
    }


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont(FONT, 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(20 * mm, 12 * mm, t("SAMPLE INVOICE - FICTIONAL DATA, FOR DEMO ONLY"))
    canvas.restoreState()


def build_pdf(inv, path):
    lang = inv["lang"]
    L = LABELS[lang]
    accent = colors.HexColor(inv["accent"])
    items, subtotal, vat, total = amounts(inv)
    fmt_date = lambda d: d.strftime(inv["date_format"])

    body = ParagraphStyle("body", fontName=FONT, fontSize=9, leading=12)
    bold = ParagraphStyle("bold", parent=body, fontName=FONT_BOLD)
    right = ParagraphStyle("right", parent=body, alignment=TA_RIGHT)
    right_bold = ParagraphStyle("right_bold", parent=right, fontName=FONT_BOLD)
    big = ParagraphStyle("big", parent=bold, fontSize=18, leading=22, textColor=accent)
    big_right = ParagraphStyle("big_right", parent=big, alignment=TA_RIGHT)
    name_style = ParagraphStyle("name", parent=bold, fontSize=13, leading=16)

    supplier_block = [
        Paragraph(t(inv["supplier_name"]), name_style),
        Paragraph(t(inv["supplier_address"]), body),
        Paragraph(f"{L['tax_id']}: {inv['supplier_tax_id']}", body),
    ]
    meta_block = [
        Paragraph(f"{t(L['number'])}: <b>{inv['invoice_number']}</b>", body),
        Paragraph(f"{t(L['date'])}: {fmt_date(inv['invoice_date'])}", body),
        Paragraph(f"{t(L['due'])}: {fmt_date(inv['due_date'])}", body),
    ]
    customer_block = [
        Paragraph(t(L["customer"]), bold),
        Paragraph(t(inv["customer_name"]), body),
        Paragraph(t(inv["customer_address"]), body),
    ]

    story = []
    usable = 170 * mm

    if inv["layout"] == "A":
        head = Table(
            [[supplier_block, [Paragraph(t(L["title"]), big_right)] + [
                Paragraph(p.text, right) for p in meta_block]]],
            colWidths=[usable * 0.55, usable * 0.45],
        )
        head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story += [head, Spacer(1, 10 * mm), *customer_block, Spacer(1, 8 * mm)]

        rows = [[Paragraph(t(L[k]), ParagraphStyle("h", parent=bold, textColor=colors.white))
                 for k in ("desc", "qty", "unit", "amount")]]
        for item in items:
            rows.append([
                Paragraph(t(item["description"]), body),
                Paragraph(number(item["quantity"]), right),
                Paragraph(money(item["unit_price"], lang), right),
                Paragraph(money(item["line_total"], lang), right),
            ])
        table = Table(rows, colWidths=[80 * mm, 20 * mm, 35 * mm, 35 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), accent),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story += [table, Spacer(1, 6 * mm)]

        totals = Table([
            [Paragraph(t(L["subtotal"]), body), Paragraph(f"{money(subtotal, lang)} {inv['currency']}", right)],
            [Paragraph(t(L["vat"].format(rate=inv["vat_rate"])), body), Paragraph(f"{money(vat, lang)} {inv['currency']}", right)],
            [Paragraph(t(L["total"]), bold), Paragraph(f"{money(total, lang)} {inv['currency']}", right_bold)],
        ], colWidths=[40 * mm, 40 * mm], hAlign="RIGHT")
        totals.setStyle(TableStyle([("LINEABOVE", (0, 2), (-1, 2), 1, accent)]))
        story.append(totals)

    else:  # layout B: fara grila, titlul la dreapta, totaluri sub linie
        story += [Paragraph(t(L["title"]), big_right), Spacer(1, 4 * mm)]
        head = Table([[supplier_block, meta_block]], colWidths=[usable * 0.55, usable * 0.45])
        head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story += [head, Spacer(1, 8 * mm), *customer_block, Spacer(1, 10 * mm)]

        rows = [[Paragraph(t(L["desc"]), bold), Paragraph(t(L["qty"]), right_bold),
                 Paragraph(t(L["unit"]), right_bold), Paragraph(t(L["amount"]), right_bold)]]
        for item in items:
            rows.append([
                Paragraph(t(item["description"]), body),
                Paragraph(number(item["quantity"]), right),
                Paragraph(money(item["unit_price"], lang), right),
                Paragraph(money(item["line_total"], lang), right),
            ])
        table = Table(rows, colWidths=[85 * mm, 20 * mm, 32 * mm, 33 * mm])
        table.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, 0), 1, accent),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story += [table, Spacer(1, 6 * mm)]

        totals = Table([
            [Paragraph(t(L["subtotal"]), body), Paragraph(money(subtotal, lang), right)],
            [Paragraph(t(L["vat"].format(rate=inv["vat_rate"])), body), Paragraph(money(vat, lang), right)],
            [Paragraph(f"{t(L['total'])} ({inv['currency']})", bold), Paragraph(money(total, lang), right_bold)],
        ], colWidths=[60 * mm, 35 * mm], hAlign="RIGHT")
        totals.setStyle(TableStyle([("LINEABOVE", (0, 2), (-1, 2), 1, accent)]))
        story.append(totals)

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=20 * mm, bottomMargin=20 * mm, title=inv["invoice_number"])
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def main():
    setup_fonts()
    if not UNICODE_OK:
        print("Nu am gasit un font cu diacritice, folosesc Helvetica (diacriticele sunt scoase).")
    OUT_DIR.mkdir(exist_ok=True)

    expected = []
    for inv in INVOICES:
        build_pdf(inv, OUT_DIR / inv["file"])
        expected.append(expected_result(inv))
        print("created", inv["file"])

    json_path = OUT_DIR / "sample_results.json"
    json_path.write_text(json.dumps(expected, indent=2, ensure_ascii=False), encoding="utf-8")
    print("created", json_path.name)


if __name__ == "__main__":
    main()
