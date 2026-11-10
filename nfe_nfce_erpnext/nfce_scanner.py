import re
import requests
from bs4 import BeautifulSoup
import frappe
from nfe_nfce_erpnext.logic.classifier import classify_item
from nfe_nfce_erpnext.sefaz_sync import get_or_create_supplier

@frappe.whitelist(allow_guest=True)
def parse_qr(qr_url: str = None, **kwargs):
    """
    Backend Endpoint: Parses SEFAZ NFC-e QR code, extracts vendor CNPJ, total purchase amount,
    and individual product line items, creating a Draft Purchase Invoice in ERPNext.
    """
    if frappe.session.user == "Guest":
        return {"status": "error", "error": "Você precisa estar logado no sistema para registrar compras por NFC-e."}

    if not frappe.has_permission("Purchase Invoice", "create"):
        return {"status": "error", "error": "Permissão negada para registrar compras por NFC-e."}

    if not qr_url or qr_url == "qr_url":
        qr_url = frappe.form_dict.get("qr_url") or kwargs.get("qr_url")

    if not qr_url or qr_url == "qr_url":
        return {"status": "error", "error": "URL do QR Code não fornecida ou inválida"}

    chave_44 = ""
    supplier_cnpj = ""
    total_amount_from_url = 0.0

    chave_match = re.search(r"(\d{44})", qr_url)
    if chave_match:
        chave_44 = chave_match.group(1)
        supplier_cnpj = chave_44[6:20] # Digits 7-20 = CNPJ

    if "|" in qr_url:
        pipe_parts = qr_url.split("|")
        for part in pipe_parts:
            try:
                val = float(part.replace(",", "."))
                if 0.01 <= val <= 100000.0 and val != float(chave_44[:2]):
                    total_amount_from_url = val
            except ValueError:
                pass

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    supplier_name = "Fornecedor NFC-e"
    items = []
    grand_total_html = 0.0
    csc_error_detected = False

    try:
        res = requests.get(qr_url, headers=headers, timeout=15)
        if res.status_code == 200:
            if "CSC inexistente" in res.text or "103" in res.text:
                csc_error_detected = True
            else:
                items, grand_total_html, supplier_name, supplier_cnpj = parse_items_from_html_or_text(res.text, supplier_cnpj, supplier_name)

    except Exception as fetch_err:
        csc_error_detected = True
        frappe.log_error(title="NFC-e Scanner Warning", message=f"SEFAZ Fetch Warning: {str(fetch_err)}")

    if not items:
        final_total = grand_total_html or total_amount_from_url or 1.0
        generic_item = classify_item(supplier_cnpj, "", "Compra NFC-e")
        items.append({
            "item_code": generic_item,
            "qty": 1.0,
            "rate": final_total,
            "amount": final_total,
            "description": f"Compra NFC-e (Chave: {chave_44 or 'N/A'})"
        })

    supplier_docname = get_or_create_supplier(supplier_cnpj, supplier_name)
    company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all("Company")[0].name

    try:
        pi_remarks = f"Ingerido via NFC-e Scanner PWA\n" \
                     f"Fornecedor: {supplier_name}\n" \
                     f"CNPJ: {supplier_cnpj or 'N/A'}\n" \
                     f"Chave de Acesso: {chave_44 or 'N/A'}\n" \
                     f"URL Original: {qr_url}"

        pi = frappe.get_doc({
            "doctype": "Purchase Invoice",
            "company": company,
            "currency": "BRL",
            "conversion_rate": 1.0,
            "supplier": supplier_docname,
            "docstatus": 0, # Draft
            "items": items,
            "remarks": pi_remarks
        })
        pi.insert(ignore_permissions=True)
        frappe.db.commit()

        if csc_error_detected:
            return {
                "status": "partial_success",
                "invoice_name": pi.name,
                "chave_44": chave_44,
                "redirect_url": f"/app/purchase-invoice/{pi.name}",
                "sefaz_lookup_url": "http://nfe.sefaz.ba.gov.br/servicos/nfce/Modulos/Geral/NFCEC_consulta_chave_acesso.aspx",
                "message": "SEFAZ retornou erro de CSC no QR Code. Fatura Rascunho criada por Chave de Acesso!"
            }

        return {
            "status": "success",
            "invoice_name": pi.name,
            "redirect_url": f"/app/purchase-invoice/{pi.name}"
        }

    except Exception as e:
        frappe.log_error(title="NFC-e Scanner Error", message=f"NFC-e Purchase Invoice Creation Exception: {str(e)}")
        return {"status": "error", "error": str(e)}

@frappe.whitelist(allow_guest=True)
def parse_sefaz_html(invoice_name: str = None, html_content: str = None):
    """
    Enriches an existing Draft Purchase Invoice with line items parsed from SEFAZ plain text or HTML.
    """
    if frappe.session.user == "Guest":
        return {"status": "error", "error": "Você precisa estar logado no sistema para atualizar Faturas de Compra."}

    if not frappe.has_permission("Purchase Invoice", "write"):
        return {"status": "error", "error": "Permissão negada para atualizar Fatura de Compra."}

    if not invoice_name:
        invoice_name = frappe.form_dict.get("invoice_name")

    if not html_content:
        html_content = frappe.form_dict.get("html_content")

    if not invoice_name:
        return {"status": "error", "error": "ID da Fatura Rascunho não fornecido."}

    if not html_content:
        return {"status": "error", "error": "Texto ou HTML da SEFAZ não fornecido."}

    try:
        pi = frappe.get_doc("Purchase Invoice", invoice_name)
    except Exception as e:
        return {"status": "error", "error": f"Fatura '{invoice_name}' não encontrada: {str(e)}"}

    if pi.docstatus != 0:
        return {"status": "error", "error": "Apenas rascunhos podem ser atualizados."}

    items, grand_total, supplier_name, supplier_cnpj = parse_items_from_html_or_text(html_content, pi.tax_id or "")

    if items:
        if supplier_cnpj and (not pi.tax_id or pi.supplier == "Fornecedor NFC-e"):
            pi.supplier = get_or_create_supplier(supplier_cnpj, supplier_name)

        try:
            pi.set("items", items)
            pi.save(ignore_permissions=True)
            frappe.db.commit()
            return {
                "status": "success",
                "message": f"{len(items)} itens extraídos e inseridos na fatura!",
                "redirect_url": f"/app/purchase-invoice/{pi.name}"
            }
        except Exception as save_err:
            frappe.log_error(title="NFC-e Save Error", message=f"Parse SEFAZ Save Exception: {str(save_err)}")
            return {"status": "error", "error": f"Erro ao salvar fatura: {str(save_err)}"}

    return {"status": "error", "error": "Nenhum item encontrado no texto ou HTML fornecido."}

def parse_items_from_html_or_text(content: str, supplier_cnpj: str = "", supplier_name: str = "Fornecedor NFC-e"):
    """Dual Parser Engine: Supports plain text clipboard copy and SEFAZ HTML DOM trees (BA, SP, RS, MG)."""
    items = []
    grand_total = 0.0

    # 1. HTML DOM Parsing (BeautifulSoup)
    if "<html" in content.lower() or "<table" in content.lower() or "<div" in content.lower():
        try:
            soup = BeautifulSoup(content, "html.parser")
            emit_tag = soup.find("div", id="u20") or soup.find("div", id="txtRazaoSocial") or soup.find("span", class_="txtTop") or soup.find("div", class_="txtTopo")
            if emit_tag:
                supplier_name = emit_tag.get_text(strip=True)

            text_all = soup.get_text()
            cnpj_match = re.search(r"CNPJ:\s*([\d\.\/\-]+)", text_all)
            if cnpj_match:
                supplier_cnpj = re.sub(r"\D", "", cnpj_match.group(1))

            total_tag = soup.find("span", class_=re.compile(r"totalNff|txtMaior|vltTotal|totalNumb", re.I))
            if total_tag:
                try:
                    grand_total = float(re.sub(r"[^\d,\.]", "", total_tag.get_text()).replace(",", "."))
                except ValueError:
                    pass

            item_rows = soup.find_all("tr", id=re.compile(r"Item", re.I)) or soup.find_all("tr") or soup.find_all("div", class_=re.compile(r"item|linha", re.I))

            for row in item_rows:
                name_tag = row.find("span", class_="txtTit") or row.find("span", class_="txtMaior") or row.find("td", class_="item-nome")
                if not name_tag:
                    continue

                p_name = name_tag.get_text(strip=True)
                if not p_name or any(k in p_name for k in ["NFC-e", "DOCUMENTO", "Vl. Total"]):
                    continue

                code = ""
                code_tag = row.find("span", class_="RCod") or row.find("span", class_="RCode")
                if code_tag:
                    code_match = re.search(r"(\d+)", code_tag.get_text())
                    if code_match:
                        code = code_match.group(1)

                qty, rate, amount = 1.0, 0.0, 0.0

                qty_tag = row.find("span", class_="Rqtd") or row.find("span", class_="RText") or row.find("span", class_="txtQtde")
                if qty_tag:
                    qty_match = re.search(r"Qtde\.:?\s*([\d,\.]+)", qty_tag.get_text(), re.I)
                    if qty_match:
                        try:
                            qty = float(qty_match.group(1).replace(",", "."))
                        except ValueError:
                            pass

                unit_tag = row.find("span", class_="RvlUnit") or row.find("span", class_="txtValor")
                if unit_tag:
                    unit_match = re.search(r"Vl\.\s*Unit\.:?\s*([\d,\.]+)", unit_tag.get_text(), re.I)
                    if unit_match:
                        try:
                            rate = float(unit_match.group(1).replace(",", "."))
                        except ValueError:
                            pass

                val_tag = row.find("span", class_="valor") or row.find("span", class_="vlr")
                if val_tag:
                    try:
                        amount = float(re.sub(r"[^\d,\.]", "", val_tag.get_text()).replace(",", "."))
                        if not rate and qty > 0:
                            rate = amount / qty
                    except ValueError:
                        pass

                item_desc = f"{p_name} (Código: {code})" if code else p_name
                generic_item = classify_item(supplier_cnpj, code, p_name)

                items.append({
                    "item_code": generic_item,
                    "qty": qty,
                    "rate": rate or (amount / qty if qty > 0 else 1.0),
                    "amount": amount or (qty * rate),
                    "description": item_desc
                })

            if items:
                return items, grand_total, supplier_name, supplier_cnpj

        except Exception as html_err:
            frappe.log_error(f"HTML Parse Warning: {str(html_err)}", "NFC-e HTML Parse Warning")

    # 2. Plain Text Parsing (Regex Fallback)
    pattern = r"([^\n\r]+?)\s*(?:\(Código:\s*(\d+)\))?\s*[\r\n]+\s*Qtde\.:?\s*([\d,\.]+)\s*UN:\s*\w+\s*Vl\.\s*Unit\.:?\s*([\d,\.]+)[^\r\n]*[\r\n]+\s*([\d,\.]+)"
    matches = re.findall(pattern, content, re.IGNORECASE)

    if matches:
        cnpj_match = re.search(r"CNPJ:\s*([\d\.\/\-]+)", content)
        if cnpj_match:
            supplier_cnpj = re.sub(r"\D", "", cnpj_match.group(1))

        for line in content.splitlines():
            line_s = line.strip()
            if line_s and not any(k in line_s for k in ["NFC-e", "DOCUMENTO", "CNPJ", "AV.", "RUA", "Qtde", "Valor"]):
                supplier_name = line_s
                break

        for p_name, code, qty_str, rate_str, amount_str in matches:
            p_name = p_name.strip()
            if not p_name or any(k in p_name for k in ["NFC-e", "DOCUMENTO"]):
                continue

            try:
                qty = float(qty_str.replace(",", "."))
                rate = float(rate_str.replace(",", "."))
                amount = float(amount_str.replace(",", "."))
            except ValueError:
                qty, rate, amount = 1.0, 1.0, 1.0

            item_desc = f"{p_name} (Código: {code})" if code else p_name
            generic_item = classify_item(supplier_cnpj, code or "", p_name)

            items.append({
                "item_code": generic_item,
                "qty": qty,
                "rate": rate,
                "amount": amount,
                "description": item_desc
            })

        total_match = re.search(r"Valor a pagar R\$:\s*([\d,\.]+)", content, re.I) or re.search(r"Valor total R\$:\s*([\d,\.]+)", content, re.I)
        if total_match:
            try:
                grand_total = float(total_match.group(1).replace(",", "."))
            except ValueError:
                pass

        return items, grand_total, supplier_name, supplier_cnpj

    return items, grand_total, supplier_name, supplier_cnpj
