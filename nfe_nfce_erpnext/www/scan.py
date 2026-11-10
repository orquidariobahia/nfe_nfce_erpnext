import frappe

def get_context(context):
    """
    Enforces authentication and Purchase Invoice creation permission for /scan route,
    and provides csrf_token to window context.
    """
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/scan"
        raise frappe.Redirect

    if not frappe.has_permission("Purchase Invoice", "create"):
        frappe.throw("Você não tem permissão para registrar compras por NFC-e.", frappe.PermissionError)

    context.csrf_token = frappe.sessions.get_csrf_token()
    context.no_cache = 1
    return context
