import frappe

def setup_default_fixtures():
    """
    Auto-creates required production system defaults on app install/migrate:
    - Default Supplier 'Fornecedor Eventual (NFC-e)'
    - Default Holding Item 'Compra NFC-e' with is_purchase_item = 1
    """
    supplier_group = frappe.db.get_value("Supplier Group", {"is_group": 0}, "name") or (frappe.get_all("Supplier Group") and frappe.get_all("Supplier Group")[0].name)
    if not supplier_group:
        return

    placeholder_supplier = "Fornecedor Eventual (NFC-e)"
    if not frappe.db.exists("Supplier", placeholder_supplier):
        frappe.get_doc({
            "doctype": "Supplier",
            "supplier_name": placeholder_supplier,
            "tax_id": "",
            "supplier_group": supplier_group
        }).insert(ignore_permissions=True)

    item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name") or (frappe.get_all("Item Group") and frappe.get_all("Item Group")[0].name)
    holding_item = "Compra NFC-e"
    if not frappe.db.exists("Item", holding_item):
        frappe.get_doc({
            "doctype": "Item",
            "item_code": holding_item,
            "item_name": "Compra Geral por NFC-e",
            "item_group": item_group,
            "is_purchase_item": 1,
            "stock_uom": "Nos"
        }).insert(ignore_permissions=True)

    # Disable 'must_be_whole_number' on UOMs to support weighed/fractional quantities (e.g. 0.396 kg)
    for uom_name in ["Nos", "Unit", "Unidade", "Kg"]:
        if frappe.db.exists("UOM", uom_name):
            frappe.db.set_value("UOM", uom_name, "must_be_whole_number", 0)

    frappe.db.commit()
