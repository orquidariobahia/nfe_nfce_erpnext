import json
import re
import frappe
import requests

def classify_item(supplier_cnpj: str, supplier_item_code: str, raw_description: str, ncm_code: str = None) -> str:
    """
    Tiered Item Classifier:
    Tier 1: Supplier Alias lookup (NFe Supplier Item Mapping) by (supplier_cnpj + supplier_item_code)
    Tier 2: NCM prefix or keyword regex rules
    Tier 3: LLM fallback (Gemini API)
    Fallback: 'Uncategorized Purchase' holding item
    """
    if not supplier_cnpj or not raw_description:
        return get_default_holding_item()

    # Tier 1: Supplier Alias Lookup
    mapped_item = frappe.db.get_value(
        "NFe Supplier Item Mapping",
        {"supplier_cnpj": supplier_cnpj, "supplier_item_code": supplier_item_code},
        "generic_item"
    )
    if mapped_item:
        return mapped_item

    # Tier 2: NCM Prefix & Regex Rules
    regex_matched_item = classify_by_ncm_or_regex(raw_description, ncm_code)
    if regex_matched_item:
        return regex_matched_item

    # Tier 3: LLM Classifier Fallback
    llm_matched_item = classify_with_llm(raw_description, ncm_code)
    if llm_matched_item:
        return llm_matched_item

    return get_default_holding_item()

def classify_by_ncm_or_regex(raw_description: str, ncm_code: str = None) -> str:
    """Matches raw description or NCM against internal generic non-stock items."""
    desc_upper = raw_description.upper()

    # Common NCM Prefixes & Keywords
    rules = [
        (r"FERTILIZANTE|ADUBO|NUTRIM|CALCIO|MAGNESIO", "Fertilizer - Calcium"),
        (r"MASCARA|PFF2|LUVA|EPI", "PPE - Masks & Gloves"),
        (r"EMBALAGEM|SACO|VASO|PLASTICO", "Plastic Pots & Bags"),
        (r"COMBUSTIVEL|GASOLINA|DIESEL|FRETE", "Fuel & Freight"),
        (r"FERRAMENTA|PECA|REPARO", "Tools & Spare Parts")
    ]

    for pattern, generic_item_code in rules:
        if re.search(pattern, desc_upper):
            # Check if generic item exists in ERPNext
            if frappe.db.exists("Item", generic_item_code):
                return generic_item_code

    return None

def classify_with_llm(raw_description: str, ncm_code: str = None) -> str:
    """
    Tier 3: Uses Gemini API to match ambiguous vendor description to candidate generic non-stock items.
    """
    api_key = frappe.conf.get("gemini_api_key")
    if not api_key and frappe.db.exists("DocType", "SEFAZ Settings"):
        meta = frappe.get_meta("SEFAZ Settings")
        if meta.has_field("gemini_api_key"):
            api_key = frappe.db.get_single_value("SEFAZ Settings", "gemini_api_key")

    if not api_key:
        return None

    # Fetch all non-stock items as candidates
    candidates = frappe.get_all("Item", filters={"maintain_stock": 0}, fields=["item_code", "item_name"])
    candidate_codes = [c["item_code"] for c in candidates]
    if not candidate_codes:
        return None

    system_prompt = (
        "You are an agricultural inventory categorizer. "
        "Match the vendor product description to the single most appropriate internal generic item code. "
        "Select ONLY from the provided candidate list."
    )

    user_prompt = f"""
    Vendor Description: "{raw_description}"
    NCM Code: "{ncm_code or 'N/A'}"
    Candidate Items: {json.dumps(candidate_codes)}
    """

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        body = {
            "contents": [{
                "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]
            }],
            "generationConfig": {
                "response_mime_type": "application/json"
            }
        }
        
        response = requests.post(url, json=body, headers=headers, timeout=5)
        if response.status_code == 200:
            result = response.json()
            text = result['candidates'][0]['content']['parts'][0]['text']
            parsed = json.loads(text)
            selected = parsed.get("selected_item_code") or parsed.get("item_code")
            if selected in candidate_codes:
                return selected
    except Exception as e:
        frappe.log_error(f"LLM Classification Exception: {str(e)}", "Classifier Error")

    return None

def get_default_holding_item() -> str:
    item_code = "Uncategorized Purchase"
    if not frappe.db.exists("Item", item_code):
        item = frappe.get_doc({
            "doctype": "Item",
            "item_code": item_code,
            "item_name": "Uncategorized Purchase",
            "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups",
            "is_purchase_item": 1,
            "is_sales_item": 0,
            "maintain_stock": 0
        })
        item.insert(ignore_permissions=True)
    else:
        frappe.db.set_value("Item", item_code, "is_purchase_item", 1)
    return item_code
