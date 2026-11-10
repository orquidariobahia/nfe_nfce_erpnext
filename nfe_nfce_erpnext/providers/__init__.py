import frappe
from nfe_nfce_erpnext.providers.base import BaseFiscalProvider
from nfe_nfce_erpnext.providers.webmania import WebmaniaProvider

def get_fiscal_provider() -> BaseFiscalProvider:
    """
    Factory function that returns the configured Fiscal Provider based on Nota Fiscal Settings.
    Defaults to WebmaniaProvider if not specified.
    """
    settings = frappe.get_doc("Nota Fiscal Settings")
    provider_name = getattr(settings, "fiscal_provider", "WebManiaBR") or "WebManiaBR"

    if provider_name == "WebManiaBR":
        return WebmaniaProvider()
    else:
        # Fallback to WebManiaBR as default
        return WebmaniaProvider()
