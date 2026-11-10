frappe.ui.form.on("POS Invoice", {
    timeline_refresh: function (frm) {
        add_nf_buttons(frm, "server_pos_invoice");
        frm.add_custom_button(__('Forçar Cancelamento'), function () {
            frappe.confirm(
                'Tem certeza que deseja forçar o cancelamento deste documento? Esta ação não pode ser desfeita.',
                function() {
                    frappe.call({
                        type: "POST",
                        method: "nfe_nfce_erpnext.api.forceCancelDocument",
                        args: {
                            "source_name": frm.doc.name,
                        },
                        callback: function (r) {
                            console.log(r);
                            if (!r.exc) {
                                frappe.msgprint("Cancelamento forçado com sucesso.");
                                frm.reload_doc();
                            }
                        }
                    });
                }
            );
        });
    },
});

frappe.ui.form.on("Sales Invoice", {
    timeline_refresh: function (frm) {
        add_nf_buttons(frm, "server_invoice");
    },
});

function add_nf_buttons(frm, server_invoice) {
    frm.add_custom_button(__('Criar NF-e'), function () {
        frappe.call({
            type: "GET",
            method: "nfe_nfce_erpnext.api.criarNotaFiscal",
            args: {
                [server_invoice]: frm.doc.name,
                "modelo": 1,
                "insert": true
            },
            callback: function (r) {
                console.log(r);
                if (!r.exc) {
                    frappe.set_route("Form", r.message.doctype, r.message.name);
                }
            }
        });
    }, __('Create'));

    frm.add_custom_button(__('Criar NFC-e'), function () {
        frappe.call({
            type: "GET",
            method: "nfe_nfce_erpnext.api.criarNotaFiscal",
            args: {
                [server_invoice] : frm.doc.name,
                "modelo": 2,
                "insert": true
            },
            callback: function (r) {
                console.log(r);
                if (!r.exc) {
                    frappe.set_route("Form", r.message.doctype, r.message.name);
                }
            }
        });
    }, __('Create'));
}