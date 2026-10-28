"""Trimite o factura (PDF sau imagine) catre API-ul Anthropic si primeste campurile extrase.

Nimic nu este salvat pe disc si continutul facturilor nu este scris in log.
"""
import base64
import json

import anthropic

MODEL = "claude-haiku-5-5"  # schimba aici modelul daca vrei altul
MAX_TOKENS = 2000
MAX_FILE_MB = 20

TEXT_FIELDS = [
    "supplier_name", "supplier_tax_id", "invoice_number",
    "invoice_date", "due_date", "currency",
]
NUMBER_FIELDS = ["subtotal", "vat_amount", "total"]

PROMPT = """You are a careful invoice data extraction assistant.
Read the attached invoice (it may be in Romanian or English) and return ONLY one JSON object, with no explanation and no markdown fences.

Use exactly these keys:
{
  "supplier_name": string,
  "supplier_tax_id": string (Romanian CUI/CIF or EU VAT number),
  "invoice_number": string,
  "invoice_date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD",
  "currency": ISO code such as EUR, RON, GBP,
  "subtotal": number (total without VAT),
  "vat_amount": number,
  "total": number (total to pay),
  "line_items": [
    {"description": string, "quantity": number, "unit_price": number, "line_total": number}
  ]
}

Rules:
- If a field is not on the invoice, use null. Never guess or invent values.
- Numbers must use a dot as the decimal separator and no thousands separator (write 1234.50, not 1.234,50 and not 1,234.50).
- Dates must be in ISO format YYYY-MM-DD.
- Romanian hints: "Furnizor" = supplier, "CUI" or "CIF" = tax id, "TVA" = VAT, "Scadenta" = due date, "Total de plata" = total to pay, "Total fara TVA" = subtotal.
- Copy the amounts exactly as printed, even if they look inconsistent. Do not fix or recalculate anything."""


class ExtractionError(Exception):
    """Eroare cu un mesaj prietenos, care poate fi aratat direct utilizatorului."""


def make_client(api_key):
    return anthropic.Anthropic(api_key=api_key)


def build_file_block(file_name, file_bytes):
    """PDF-urile merg ca bloc 'document', imaginile ca bloc 'image' (base64)."""
    name = file_name.lower()
    data = base64.standard_b64encode(file_bytes).decode("utf-8")

    if name.endswith(".pdf"):
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
        }

    if name.endswith(".png"):
        media_type = "image/png"
    elif name.endswith((".jpg", ".jpeg")):
        media_type = "image/jpeg"
    else:
        raise ExtractionError("Unsupported file type. Use PDF, PNG or JPG.")

    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }


def parse_json(text):
    """Scoate obiectul JSON din raspuns (chiar daca modelul a pus ```json in jurul lui)."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found")
    return json.loads(text[start:end + 1])


def to_number(value):
    """Transforma orice valoare intr-un float sau None. Repara si '1.234,50' sau '1,234.50'."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(" ", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):  # format 1.234,50
            text = text.replace(".", "").replace(",", ".")
        else:                                  # format 1,234.50
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return None


def normalize(data):
    """Se asigura ca rezultatul are mereu aceleasi chei si tipuri."""
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")

    result = {field: data.get(field) for field in TEXT_FIELDS}
    for field in NUMBER_FIELDS:
        result[field] = to_number(data.get(field))

    items = []
    for item in data.get("line_items") or []:
        if not isinstance(item, dict):
            continue
        items.append({
            "description": item.get("description"),
            "quantity": to_number(item.get("quantity")),
            "unit_price": to_number(item.get("unit_price")),
            "line_total": to_number(item.get("line_total")),
        })
    result["line_items"] = items
    return result


def ask_model(client, file_block):
    """Un singur apel catre API. Erorile tehnice devin mesaje clare."""
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{
                "role": "user",
                "content": [file_block, {"type": "text", "text": PROMPT}],
            }],
        )
    except anthropic.AuthenticationError:
        raise ExtractionError("Invalid API key. Check the key and try again.") from None
    except anthropic.PermissionDeniedError:
        raise ExtractionError("This API key is not allowed to use this model.") from None
    except anthropic.RateLimitError:
        raise ExtractionError("Rate limit reached. Wait a minute and try again.") from None
    except anthropic.APIConnectionError:
        raise ExtractionError("Could not reach the API. Check your internet connection.") from None
    except anthropic.BadRequestError as error:
        if "credit balance" in str(error).lower():
            raise ExtractionError("Your Anthropic account has no credit left.") from None
        raise ExtractionError(
            "The API rejected this file. Is it a valid PDF/image, without a password?"
        ) from None
    except anthropic.APIStatusError as error:
        raise ExtractionError(f"API error ({error.status_code}). Please try again.") from None

    return "".join(block.text for block in response.content if block.type == "text")


def extract_invoice(client, file_name, file_bytes):
    """Extrage datele unei facturi. Incearca de doua ori daca JSON-ul vine stricat."""
    if len(file_bytes) > MAX_FILE_MB * 1024 * 1024:
        raise ExtractionError(f"File is larger than {MAX_FILE_MB} MB.")

    file_block = build_file_block(file_name, file_bytes)

    for _attempt in range(2):
        text = ask_model(client, file_block)
        try:
            return normalize(parse_json(text))
        except ValueError:  # json.JSONDecodeError este un ValueError
            continue

    raise ExtractionError(
        "The model did not return valid data for this file. Try again or use a clearer file."
    )
