frappe.ui.form.on("Purchase Invoice", {
    refresh: function (frm) {
        if (frm.doc.docstatus === 0 && frm.doc.supplier === "Fornecedor Eventual (NFC-e)") {
            frm.add_custom_button(__("Criar Fornecedor Permanente"), function () {
                let default_name = "";
                if (frm.doc.remarks) {
                    let match = frm.doc.remarks.match(/Fornecedor:\s*([^(\n]+)/);
                    if (match && match[1]) {
                        let parsed_name = match[1].trim();
                        if (parsed_name !== "Fornecedor NFC-e") {
                            default_name = parsed_name;
                        }
                    }
                }

                frappe.prompt([
                    {
                        label: __("Nome do Fornecedor"),
                        fieldname: "supplier_name",
                        fieldtype: "Data",
                        default: default_name,
                        reqd: 1
                    }
                ], function (values) {
                    frappe.call({
                        method: "nfe_nfce_erpnext.api.create_permanent_supplier",
                        args: {
                            invoice_name: frm.doc.name,
                            supplier_name: values.supplier_name
                        },
                        freeze: true,
                        freeze_message: __("Criando cadastro do Fornecedor..."),
                        callback: function (r) {
                            if (r.message && r.message.status === "success") {
                                frappe.msgprint(r.message.message);
                                frm.reload_doc();
                            }
                        }
                    });
                }, __("Converter para Fornecedor Permanente"), __("Criar"));
            }, __("Actions"));
        }
    }
});
