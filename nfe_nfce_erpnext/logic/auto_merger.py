import datetime
import frappe

def try_auto_link_invoice(doc, method):
    """
    Hook on Payment Entry validate/before_insert.
    Automatically searches for matching Draft Purchase Invoices by exact amount (+/- 2 days)
    and disambiguates using Supplier CNPJ/name in remarks if multiple exist.
    """
    # Skip if already linked or not a draft
    if doc.docstatus != 0 or doc.references:
        return

    posting_dt = datetime.datetime.strptime(str(doc.posting_date), "%Y-%m-%d").date() if isinstance(doc.posting_date, str) else doc.posting_date
    start_date = posting_dt - datetime.timedelta(days=2)
    end_date = posting_dt + datetime.timedelta(days=2)

    filters = {
        "docstatus": 0,  # Draft Purchase Invoices
        "grand_total": doc.paid_amount,
        "posting_date": ["between", [start_date, end_date]]
    }

    invoices = frappe.get_all("Purchase Invoice", filters=filters, fields=["name", "supplier", "tax_id"])

    matching_invoice_name = None
    if len(invoices) == 1:
        matching_invoice_name = invoices[0].name
    elif len(invoices) > 1 and doc.remarks:
        # Disambiguate using Supplier CNPJ or supplier_name in remarks
        for inv in invoices:
            if inv.tax_id and inv.tax_id in doc.remarks:
                matching_invoice_name = inv.name
                break
            elif inv.supplier and inv.supplier.lower() in doc.remarks.lower():
                matching_invoice_name = inv.name
                break

    if matching_invoice_name:
        doc.append("references", {
            "reference_doctype": "Purchase Invoice",
            "reference_name": matching_invoice_name,
            "allocated_amount": doc.paid_amount
        })
        frappe.msgprint(f"Auto-linked to Draft Invoice {matching_invoice_name}", alert=True)
