# Copyright (c) 2024, shirkit and contributors
# For license information, please see license.txt

import datetime
import frappe
from frappe.model.document import Document

class NotaFiscalSettings(Document):
    def onload(self):
        self.set_webhook_url()
        self.set_default_start_date()

    def validate(self):
        self.set_webhook_url()
        self.set_default_start_date()

    def set_webhook_url(self):
        self.pluggy_webhook_url = frappe.utils.get_url("/api/method/nfe_nfce_erpnext.pluggy_sync.handle_pluggy_webhook")

    def set_default_start_date(self):
        if not self.pluggy_start_date:
            self.pluggy_start_date = datetime.date.today().isoformat()
