frappe.listview_settings['Purchase Invoice'] = {
    onload: function (listview) {
        listview.page.add_actions_menu_item(__('Aprovar Selecionadas'), function () {
            let checked_items = listview.get_checked_items();
            if (!checked_items.length) {
                frappe.msgprint(__('Selecione pelo menos uma Fatura de Compra em rascunho.'));
                return;
            }

            frappe.confirm(
                __('Deseja aprovar e submeter {0} faturas de compra selecionadas?', [checked_items.length]),
                function () {
                    let docnames = checked_items.map(d => d.name);
                    frappe.call({
                        method: 'nfe_nfce_erpnext.api.bulk_submit_invoices',
                        args: { docnames: docnames },
                        freeze: true,
                        freeze_message: __('Submetendo faturas selecionadas...'),
                        callback: function (r) {
                            if (r.message && r.message.status === 'success') {
                                frappe.msgprint(r.message.message);
                                listview.refresh();
                            }
                        }
                    });
                }
            );
        });
    }
};
