frappe.ui.form.on("Nota Fiscal", {

    timeline_refresh: function (frm) {
        // create button for "Add to Knowledge Base"
        if (frm.doc.docstatus === 1) {
            if ((!frm.doc.chave || frm.doc.status.toLowerCase() != "aprovado")) {
                frm.page.add_action_item(__('Emitir Nota'), function () {
                    if (frm.doc.__unsaved) {
                        frappe.throw("Salve a nota antes de emitir");
                        return;
                    } else
                        frappe.call({
                            type: "GET",
                            method: "nfe_nfce_erpnext.api.emitirNotaFiscal",

                            args: {
                                "source_name": frm.doc
                            },
                            callback: function (r) {
                                console.log(r);
                                if (r.message) {
                                    var msg = JSON.parse(r.message);
                                    if (msg.error)
                                        frappe.throw(msg.error);
                                    else if (msg.success === true) {
                                        console.log(msg);
                                        frappe.msgprint("Nota emitida com sucesso. " + msg.modelo + " - " + msg.chave);
                                        frm.refresh();
                                        // TODO tentar imprimir com QZTray
                                    }
                                }
                            }
                        });
                });
            } else {
                if (frm.doc.status && frm.doc.status.toLowerCase() === "aprovado") {
                    const open_doc = function (format_type) {
                        frappe.call({
                            method: "nfe_nfce_erpnext.api.get_danfe_url",
                            args: { chave: frm.doc.chave, format_type: format_type },
                            callback: function (r) {
                                if (r.message) {
                                    window.open(r.message, '_blank');
                                }
                            }
                        });
                    };
                    frm.page.add_action_item(__('Abrir Danfe'), function () { open_doc('danfe'); });
                    frm.page.add_action_item(__('Abrir Danfe Simples'), function () { open_doc('simples'); });
                    frm.page.add_action_item(__('Abrir Danfe Etiqueta'), function () { open_doc('etiqueta'); });
                    frm.page.add_action_item(__('Abrir XML'), function () { open_doc('xml'); });
                }
            }
        }
    },
    onload: function (frm) {
        // frappe.msgprint("onload");
        window.frm = frm;
    },
    entrega_copiar_faturamento: function(frm) {
        frm.doc.entrega_cpf = frm.doc.cpf
        frm.doc.entrega_cnpj = frm.doc.cnpj
        frm.doc.entrega_razao_social = frm.doc.razao_social
        frm.doc.entrega_ie = frm.doc.ie
        frm.doc.entrega_nome_completo = frm.doc.nome_completo
        frm.doc.entrega_endereco = frm.doc.endereco
        frm.doc.entrega_numero = frm.doc.numero
        frm.doc.entrega_complemento = frm.doc.complemento
        frm.doc.entrega_bairro = frm.doc.bairro
        frm.doc.entrega_cidade = frm.doc.cidade
        frm.doc.entrega_uf = frm.doc.uf
        frm.doc.entrega_cep = frm.doc.cep
        frm.refresh()
    },

    /*refresh: function (frm) {
         frappe.msgprint("refresh");
    }*/
});