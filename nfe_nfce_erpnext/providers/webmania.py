import json
import requests
import frappe
from nfe_nfce_erpnext.providers.base import BaseFiscalProvider

def parse_option(option):
    if option is not None and option.startswith("("):
        return option[option.find("(") + 1 : option.find(")")]
    return option

def remove_nulls(value):
    if isinstance(value, dict):
        return {k: remove_nulls(v) for k, v in value.items() if v is not None}
    elif isinstance(value, list):
        return [remove_nulls(item) for item in value if item is not None]
    else:
        return value

class WebmaniaProvider(BaseFiscalProvider):
    """
    WebManiaBR REST API Provider Implementation for NF-e / NFC-e.
    """

    BASE_URL = "https://webmaniabr.com/api/1"
    DANFE_BASE_URL = "https://nfe.webmaniabr.com"

    def get_settings(self) -> dict:
        settings = frappe.get_doc("Nota Fiscal Settings")
        return {
            "headers": {
                "cache-control": "no-cache",
                "content-type": "application/json",
                "x-consumer-key": settings.get_password("webmania_consumer_key") or "",
                "x-consumer-secret": settings.get_password("webmania_consumer_secret") or "",
                "x-access-token": settings.get_password("webmania_access_token") or "",
                "x-access-token-secret": settings.get_password("webmania_access_token_secret") or "",
            },
            "ambiente": parse_option(settings.webmania_ambiente),
        }

    def emit_nota_fiscal(self, payload: dict) -> dict:
        config = self.get_settings()
        url = f"{self.BASE_URL}/nfe/emissao/"
        cleaned_payload = remove_nulls(payload)
        
        response = requests.post(
            url,
            data=json.dumps(cleaned_payload),
            headers=config["headers"],
            timeout=30
        )

        if response.status_code != 200 or "json" not in response.headers.get("content-type", ""):
            frappe.throw(title="Erro WebMania - Emissão NF-e", msg=response.text)

        return response.json()

    def cancel_nota_fiscal(self, chave: str, motivo: str) -> dict:
        config = self.get_settings()
        url = f"{self.BASE_URL}/nfe/cancelar/"
        payload = {
            "chave": chave,
            "motivo": motivo
        }

        response = requests.put(
            url,
            data=json.dumps(payload),
            headers=config["headers"],
            timeout=30
        )

        if response.status_code != 200 or "json" not in response.headers.get("content-type", ""):
            frappe.throw(title="Erro WebMania - Cancelamento NF-e", msg=response.text)

        return response.json()

    def get_danfe_url(self, chave: str, format_type: str = "danfe") -> str:
        routes = {
            "danfe": f"{self.DANFE_BASE_URL}/danfe/{chave}",
            "simples": f"{self.DANFE_BASE_URL}/danfe/simples/{chave}",
            "etiqueta": f"{self.DANFE_BASE_URL}/danfe/etiqueta/{chave}",
            "xml": f"{self.DANFE_BASE_URL}/xmlnfe/{chave}",
        }
        return routes.get(format_type, routes["danfe"])
