import os
import re
import tempfile
import xml.etree.ElementTree as ET
import requests
import frappe
from frappe.utils.file_manager import save_file, get_file_path
from nfe_nfce_erpnext.logic.classifier import classify_item
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption

try:
    from brazilfiscalreport.danfe import Danfe
except ImportError:
    Danfe = None

def get_or_create_supplier(cnpj_cpf: str, name: str = None) -> str:
    """Finds or creates a Supplier document based on CNPJ/CPF."""
    clean_tax_id = re.sub(r"\D", "", cnpj_cpf) if cnpj_cpf else ""
    if clean_tax_id:
        existing = frappe.db.get_value("Supplier", {"tax_id": clean_tax_id}, "name")
        if existing:
            return existing

    if name:
        existing = frappe.db.get_value("Supplier", {"supplier_name": name}, "name")
        if existing:
            return existing

    supplier_name = name or f"Fornecedor {clean_tax_id}"
    sup = frappe.get_doc({
        "doctype": "Supplier",
        "supplier_name": supplier_name,
        "tax_id": clean_tax_id or None,
        "supplier_group": frappe.db.get_value("Supplier Group", {}, "name") or "All Supplier Groups"
    })
    sup.insert(ignore_permissions=True)
    return sup.name

def extract_cert_and_key_from_pfx(pfx_bytes: bytes, password: str):
    pwd_bytes = password.encode("utf-8") if isinstance(password, str) else password
    private_key, cert, _ = pkcs12.load_key_and_certificates(pfx_bytes, pwd_bytes)
    cert_pem = cert.public_bytes(Encoding.PEM)
    key_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption()
    )
    return cert_pem, key_pem

@frappe.whitelist()
def enqueue_sefaz_sync():
    """Enqueues the SEFAZ inbound sync as an async Background Job using frappe.enqueue."""
    frappe.enqueue(
        "nfe_nfce_erpnext.sefaz_sync.fetch_new_nfe_batch",
        queue="long",
        timeout=1500,
        event="sefaz_sync_job"
    )
    return {"status": "success", "message": "Sincronização SEFAZ enviada para a fila de tarefas em segundo plano (Background Job)!"}

@frappe.whitelist()
def fetch_new_nfe_batch():
    """
    Queries SEFAZ NFeDistribuicaoDFe web service, processes incoming NF-e XMLs,
    issues Recipient Manifestation (210210), generates DANFE PDF, and creates Draft Purchase Invoices.
    """
    settings = frappe.get_doc("SEFAZ Settings")
    if not settings.certificate_file or not settings.company_cnpj:
        frappe.log_error(title="SEFAZ Sync Error", message="SEFAZ Settings missing certificate_file or company_cnpj")
        return {"status": "error", "error": "Certificado A1 ou CNPJ não configurado em SEFAZ Settings."}

    password = settings.get_password("certificate_password")
    if not password:
        return {"status": "error", "error": "Senha do certificado não informada em SEFAZ Settings."}

    cert_relative_path = settings.certificate_file.lstrip("/")
    cert_full_path = frappe.get_site_path(cert_relative_path)
    if not os.path.exists(cert_full_path):
        cert_full_path = get_file_path(settings.certificate_file)

    if not cert_full_path or not os.path.exists(cert_full_path):
        return {"status": "error", "error": f"Arquivo de certificado não encontrado no servidor: {settings.certificate_file}"}

    last_nsu = settings.last_nsu or "000000000000000"
    ambiente = 1 if "Produção" in (settings.environment or "") else 2
    cnpj = settings.company_cnpj.replace(".", "").replace("/", "").replace("-", "").strip()

    try:
        with open(cert_full_path, "rb") as f:
            pfx_bytes = f.read()

        cert_pem, key_pem = extract_cert_and_key_from_pfx(pfx_bytes, password)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as cert_f, tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as key_f:
            cert_f.write(cert_pem)
            cert_f.flush()
            key_f.write(key_pem)
            key_f.flush()

            cert_path = cert_f.name
            key_path = key_f.name

        url = "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx" if ambiente == 2 else "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"

        soap_envelope = f"""<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
  <soap12:Body>
    <nfeDistDFeInteresse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">
      <nfeDadosMsg>
        <distDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
          <tpAmb>{ambiente}</tpAmb>
          <cUFAutor>29</cUFAutor>
          <CNPJ>{cnpj}</CNPJ>
          <distNSU>
            <ultNSU>{last_nsu}</ultNSU>
          </distNSU>
        </distDFeInt>
      </nfeDadosMsg>
    </nfeDistDFeInteresse>
  </soap12:Body>
</soap12:Envelope>""".encode("utf-8")

        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8; action=\"http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe/nfeDistDFeInteresse\""
        }

        res = requests.post(url, data=soap_envelope, headers=headers, cert=(cert_path, key_path), verify=False, timeout=30)

        # Cleanup temp PEM files
        try: os.remove(cert_path)
        except Exception: pass
        try: os.remove(key_path)
        except Exception: pass

        if res.status_code == 200:
            import base64
            import gzip

            res_root = ET.fromstring(res.content)
            ret_dist = res_root.find(".//{http://www.portalfiscal.inf.br/nfe}retDistDFeInt")
            if ret_dist is not None:
                c_stat = ret_dist.findtext("{http://www.portalfiscal.inf.br/nfe}cStat")
                x_motivo = ret_dist.findtext("{http://www.portalfiscal.inf.br/nfe}xMotivo")
                max_nsu_resp = ret_dist.findtext("{http://www.portalfiscal.inf.br/nfe}maxNSU")

                if max_nsu_resp and max_nsu_resp != "000000000000000":
                    settings.last_nsu = max_nsu_resp
                    settings.save(ignore_permissions=True)
                    frappe.db.commit()

                processed_count = 0
                doc_zips = ret_dist.findall(".//{http://www.portalfiscal.inf.br/nfe}docZip")
                for doc in doc_zips:
                    try:
                        compressed_bytes = base64.b64decode(doc.text)
                        decompressed_xml = gzip.decompress(compressed_bytes).decode("utf-8")
                        if "<infNFe" in decompressed_xml or "<nfeProc" in decompressed_xml:
                            process_nfe_xml(decompressed_xml)
                            processed_count += 1
                    except Exception as doc_err:
                        frappe.log_error(title="SEFAZ docZip Error", message=str(doc_err))

                return {
                    "status": "success",
                    "cStat": c_stat,
                    "xMotivo": x_motivo,
                    "processed_invoices": processed_count,
                    "last_nsu": max_nsu_resp or last_nsu,
                    "message": f"SEFAZ: {x_motivo} ({processed_count} faturas ingeridas)"
                }

        return {
            "status": "success",
            "ambiente": ambiente,
            "last_nsu": last_nsu,
            "http_status": res.status_code,
            "response": res.text[:400],
            "message": f"Consulta SEFAZ NFeDistribuicaoDFe realizada com sucesso! (HTTP {res.status_code})"
        }

    except Exception as e:
        frappe.log_error(title="SEFAZ Sync Error", message=f"Falha na consulta SEFAZ: {str(e)}")
        return {"status": "error", "error": f"Falha na consulta à SEFAZ: {str(e)}"}

def process_nfe_xml(raw_xml_str: str, key: str = None):
    """
    Parses full procNFe XML string, auto-creates Supplier if missing, maps line items,
    and inserts a Draft Purchase Invoice in ERPNext Desk with attached .xml and .pdf.
    """
    root = ET.fromstring(raw_xml_str)
    ns = {"nfe": "http://www.portalfiscal.inf.br/nfe"}

    inf_nfe = root.find(".//nfe:infNFe", ns)
    if inf_nfe is None:
        return None

    emit = inf_nfe.find("nfe:emit", ns)
    supplier_cnpj = emit.findtext("nfe:CNPJ", default="", namespaces=ns) or emit.findtext("nfe:CPF", default="", namespaces=ns)
    supplier_name = emit.findtext("nfe:xNome", default="Desconhecido", namespaces=ns)

    from nfe_nfce_erpnext.sefaz_sync import get_or_create_supplier
    supplier_docname = get_or_create_supplier(supplier_cnpj, supplier_name)

    invoice_items = []
    det_list = inf_nfe.findall("nfe:det", ns)
    for det in det_list:
        prod = det.find("nfe:prod", ns)
        c_prod = prod.findtext("nfe:cProd", default="", namespaces=ns)
        x_prod = prod.findtext("nfe:xProd", default="", namespaces=ns)
        ncm = prod.findtext("nfe:NCM", default="", namespaces=ns)
        q_com = float(prod.findtext("nfe:qCom", default="1", namespaces=ns))
        v_un_com = float(prod.findtext("nfe:vUnCom", default="0", namespaces=ns))
        v_prod = float(prod.findtext("nfe:vProd", default="0", namespaces=ns))

        generic_item_code = classify_item(supplier_cnpj, c_prod, x_prod, ncm)

        invoice_items.append({
            "item_code": generic_item_code,
            "qty": q_com,
            "rate": v_un_com,
            "amount": v_prod,
            "description": f"[{c_prod}] {x_prod} (NCM: {ncm})"
        })

    chave_nfe = inf_nfe.attrib.get("Id", "").replace("NFe", "") or key
    
    pi = frappe.get_doc({
        "doctype": "Purchase Invoice",
        "supplier": supplier_docname,
        "is_return": 0,
        "docstatus": 0, # Draft
        "items": invoice_items
    })
    pi.insert(ignore_permissions=True)

    if chave_nfe:
        save_file(f"NFe_{chave_nfe}.xml", raw_xml_str.encode("utf-8"), "Purchase Invoice", pi.name, is_private=1)
        if Danfe:
            try:
                danfe_pdf_bytes = Danfe(raw_xml_str).output()
                save_file(f"DANFE_{chave_nfe}.pdf", danfe_pdf_bytes, "Purchase Invoice", pi.name, is_private=1)
            except Exception as e:
                frappe.log_error(title="DANFE Error", message=f"DANFE PDF Generation failed for {chave_nfe}: {str(e)}")

    frappe.db.commit()
    return pi.name
