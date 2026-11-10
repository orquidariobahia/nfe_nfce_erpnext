frappe.provide("nfe_nfce_erpnext.pdf");
frappe.provide("nfe_nfce_erpnext.whatsapp");

nfe_nfce_erpnext.pdf.download = function (frm) {
    if (!frm || !frm.doc) return;
    let format = (frm.meta && frm.meta.default_print_format) || "";
    let url = frappe.urllib.get_full_url(
        "/api/method/frappe.utils.print_format.download_pdf?" +
        "doctype=" + encodeURIComponent(frm.doc.doctype) +
        "&name=" + encodeURIComponent(frm.doc.name) +
        (format ? "&format=" + encodeURIComponent(format) : "") +
        (frm.doc.letter_head ? "&letterhead=" + encodeURIComponent(frm.doc.letter_head) : "")
    );
    let w = window.open(url);
    if (!w) {
        frappe.msgprint(__("Por favor, habilite os pop-ups"));
    }
};

nfe_nfce_erpnext.pdf.add_pdf_button = function (frm) {
    if (!frm || frm.is_new() || !frm.doc || frm.meta.issingle) return;
    
    // Evita adicionar duplicado se o form já tiver o botão
    if (frm.custom_buttons && frm.custom_buttons[__("Download PDF")]) return;

    frm.add_custom_button(__("Download PDF"), function () {
        nfe_nfce_erpnext.pdf.download(frm);
    }, __("Actions"));
};

// Aliases para compatibilidade
nfe_nfce_erpnext.whatsapp.add_share_button = function (frm) {
    nfe_nfce_erpnext.pdf.add_pdf_button(frm);
};

// =========================================================================
// CONFIGURAÇÃO DOS DOCTYPES:
// Basta adicionar o nome de qualquer DocType nesta lista para ter o botão!
// =========================================================================
nfe_nfce_erpnext.pdf.enabled_doctypes = [
    "Sales Invoice",
    "Purchase Invoice",
    "POS Invoice",
    "Payment Entry",
    "Nota Fiscal",
    "Sales Order",
    "Purchase Order",
    "Delivery Note",
    "Purchase Receipt",
    "Quotation",
    "Journal Entry",
    "Material Request",
    "Stock Entry"
];

// Se definido como true, adiciona automaticamente a QUALQUER documento imprimível:
nfe_nfce_erpnext.pdf.apply_to_all_printable = false;

// =========================================================================
// HOOK GLOBAL DE FORMULÁRIO (Executado no refresh de QUALQUER formulário)
// =========================================================================
$(document).on("form-refresh", function (event, frm) {
    if (!frm || frm.is_new() || !frm.doc || frm.meta.issingle) return;

    let should_add = nfe_nfce_erpnext.pdf.apply_to_all_printable
        ? frappe.model.can_print(null, frm)
        : nfe_nfce_erpnext.pdf.enabled_doctypes.includes(frm.doc.doctype);

    if (should_add) {
        nfe_nfce_erpnext.pdf.add_pdf_button(frm);
    }
});
