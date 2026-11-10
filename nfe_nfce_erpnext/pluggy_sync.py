import datetime
import requests
import frappe

PLUGGY_BASE_URL = "https://api.pluggy.ai"

@frappe.whitelist(allow_guest=True)
def handle_pluggy_webhook():
    """
    Real-Time Webhook Endpoint: Listens to Pluggy events (item/created, item/updated, transactions/created).
    Automatically saves new bank connection Item IDs and instantly ingests transactions.
    """
    try:
        data = frappe.request.get_json() or {}
        event = data.get("event")
        item_id = data.get("itemId") or data.get("id")

        if event in ("item/created", "item/updated") and item_id:
            settings = frappe.get_doc("Nota Fiscal Settings")
            existing_items = [i.strip() for i in (getattr(settings, "pluggy_item_id", None) or "").split(",") if i.strip()]
            if item_id not in existing_items:
                existing_items.append(item_id)
                settings.pluggy_item_id = ", ".join(existing_items)
                settings.save(ignore_permissions=True)
                frappe.db.commit()

        fetch_bank_transactions()

        return {"status": "success", "message": "Pluggy webhook processado com sucesso!"}
    except Exception as e:
        frappe.log_error(title="Pluggy Webhook Exception", message=str(e))
        return {"status": "error", "error": str(e)}

@frappe.whitelist()
def enqueue_pluggy_sync():
    """Enqueues the Pluggy bank transaction ingestion as an async Background Job using frappe.enqueue."""
    frappe.enqueue(
        "nfe_nfce_erpnext.pluggy_sync.fetch_bank_transactions",
        queue="default",
        timeout=600,
        event="pluggy_sync_job"
    )
    return {"status": "success", "message": "Sincronização de transações bancárias Pluggy iniciada em segundo plano!"}

@frappe.whitelist()
def fetch_bank_transactions():
    """
    Automatic Ingestion Job: Pulls recent outgoing bank transactions across ALL connected bank accounts (Open Finance),
    and creates Draft Payment Entries (docstatus = 0) in ERPNext for auto-linking with Purchase Invoices.
    Strictly filters out any historical transactions dated prior to pluggy_start_date!
    """
    settings = frappe.get_doc("Nota Fiscal Settings")
    client_id = frappe.conf.get("pluggy_client_id") or settings.get_password("pluggy_client_id")
    client_secret = frappe.conf.get("pluggy_client_secret") or settings.get_password("pluggy_client_secret")
    raw_item_id = frappe.conf.get("pluggy_item_id") or getattr(settings, "pluggy_item_id", None) or "6f91e2b1-a5c2-477b-9968-7e87bc3fa0cc"

    # Start date cut-off and posting strategy
    start_date = getattr(settings, "pluggy_start_date", None) or datetime.date.today().isoformat()
    if isinstance(start_date, datetime.date):
        start_date = start_date.isoformat()

    posting_strategy = getattr(settings, "pluggy_posting_date_strategy", None)

    if not client_id or not client_secret:
        frappe.log_error(title="Pluggy Sync Error", message="Pluggy Client ID or Secret missing in site_config or Nota Fiscal Settings")
        return {"status": "error", "error": "Credenciais da API Pluggy não configuradas."}

    token = get_pluggy_api_token(client_id, client_secret)
    if not token:
        return {"status": "error", "error": "Falha de autenticação com a API Pluggy."}

    headers = {
        "X-API-KEY": token,
        "Accept": "application/json"
    }

    try:
        item_ids = [i.strip() for i in raw_item_id.replace("\n", ",").split(",") if i.strip()]
        if not item_ids:
            item_ids = ["6f91e2b1-a5c2-477b-9968-7e87bc3fa0cc"]

        accounts = []
        for itm_id in item_ids:
            acc_res = requests.get(f"{PLUGGY_BASE_URL}/accounts?itemId={itm_id}", headers=headers, timeout=30)
            if acc_res.status_code == 200:
                accounts.extend(acc_res.json().get("results", []))
            else:
                frappe.log_error(title="Pluggy Accounts Warning", message=f"Could not fetch accounts for itemId {itm_id}: {acc_res.text[:150]}")

        if not accounts:
            return {"status": "success", "created_count": 0, "message": "Nenhuma conta bancária encontrada no Pluggy."}

        created_count = 0

        for acc in accounts:
            acc_id = acc.get("id")
            acc_name = acc.get("name") or "Conta Bancária"
            if not acc_id: continue

            txn_url = f"{PLUGGY_BASE_URL}/v2/transactions?accountId={acc_id}&from={start_date}"
            txn_res = requests.get(txn_url, headers=headers, timeout=30)
            if txn_res.status_code != 200:
                txn_url = f"{PLUGGY_BASE_URL}/v2/transactions?accountId={acc_id}"
                txn_res = requests.get(txn_url, headers=headers, timeout=30)
                if txn_res.status_code != 200: continue

            transactions = txn_res.json().get("results", [])
            for txn in transactions:
                amount = float(txn.get("amount", 0))
                txn_id = txn.get("id")
                description = txn.get("description") or txn.get("descriptionRaw") or "Transação Pluggy"
                txn_date = txn.get("date", "").split("T")[0] or datetime.date.today().isoformat()

                # STRICT CUT-OFF: Reject any transaction dated before pluggy_start_date!
                if txn_date < start_date:
                    continue

                if amount < 0 and txn_id:
                    existing = frappe.db.exists("Payment Entry", {"reference_no": txn_id})
                    if not existing:
                        create_draft_payment_entry(
                            txn_id=txn_id,
                            paid_amount=abs(amount),
                            posting_date=txn_date,
                            remarks=f"{acc_name}: {description}",
                            payment_type="Pay",
                            strategy=posting_strategy
                        )
                        created_count += 1

        frappe.db.commit()
        return {
            "status": "success",
            "connected_items": item_ids,
            "accounts_count": len(accounts),
            "created_count": created_count,
            "start_date": start_date,
            "message": f"Sincronização bancária Pluggy concluída! {created_count} novos pagamentos em rascunho criados a partir de {start_date}."
        }

    except Exception as e:
        frappe.log_error(title="Pluggy Sync Exception", message=str(e))
        return {"status": "error", "error": str(e)}

def get_pluggy_api_token(client_id: str, client_secret: str) -> str:
    """Authenticates against Pluggy /auth endpoint and returns API-KEY token."""
    url = f"{PLUGGY_BASE_URL}/auth"
    payload = {
        "clientId": client_id.strip() if isinstance(client_id, str) else client_id,
        "clientSecret": client_secret.strip() if isinstance(client_secret, str) else client_secret
    }
    try:
        res = requests.post(url, json=payload, timeout=15)
        if res.status_code == 200:
            return res.json().get("apiKey")
        else:
            frappe.log_error(title="Pluggy Auth Error", message=f"HTTP {res.status_code}: {res.text[:200]}")
    except Exception as e:
        frappe.log_error(title="Pluggy Auth Error", message=str(e))
    return None

def create_draft_payment_entry(txn_id: str, paid_amount: float, posting_date: str, remarks: str, payment_type: str = "Pay", strategy: str = None):
    """Inserts a Draft Payment Entry into ERPNext."""
    mode_of_payment = frappe.db.get_value("Mode of Payment", {"name": ["in", ["PIX Transferência", "Transferência Bancária", "Bank Draft", "Cash"]]}) or frappe.db.get_value("Mode of Payment", {}, "name")
    paid_from_account = frappe.db.get_value("Account", {"account_type": "Bank", "is_group": 0}, "name")

    # Posting date decision
    if strategy and "Data Atual" in strategy:
        gl_posting_date = datetime.date.today().isoformat()
    else:
        gl_posting_date = posting_date
    
    pe = frappe.get_doc({
        "doctype": "Payment Entry",
        "payment_type": payment_type,
        "mode_of_payment": mode_of_payment,
        "paid_from": paid_from_account,
        "party_type": "Supplier",
        "party": "Fornecedor Eventual (NFC-e)",
        "paid_amount": paid_amount,
        "received_amount": paid_amount,
        "posting_date": gl_posting_date,
        "reference_no": txn_id,
        "reference_date": posting_date, # Bank Transaction Date is ALWAYS preserved in reference_date
        "remarks": f"Pluggy Sync: {remarks}",
        "docstatus": 0
    })
    pe.insert(ignore_permissions=True)
