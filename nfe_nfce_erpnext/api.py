import base64
import json
import os
import re

import frappe
import phonenumbers
import requests
import unidecode
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from frappe.desk.form.linked_with import get_linked_docs, get_linked_doctypes
from frappe.model.mapper import get_mapped_doc
from frappe.utils import flt
from frappe.model.utils import get_fetch_values
from erpnext.stock.doctype.item.item import get_item_defaults
from erpnext.setup.doctype.item_group.item_group import get_item_group_defaults
from erpnext.accounts.party import get_party_account
from frappe.utils.file_manager import save_url
from nfe_nfce_erpnext.providers import get_fiscal_provider
from nfe_nfce_erpnext.nfce_scanner import parse_qr, parse_sefaz_html

tempStates = {
    "Acre": "AC",
    "Alagoas": "AL",
    "Amapá": "AP",
    "Amazonas": "AM",
    "Bahia": "BA",
    "Ceará": "CE",
    "Distrito Federal": "DF",
    "Espírito Santo": "ES",
    "Goiás": "GO",
    "Maranhão": "MA",
    "Mato Grosso": "MT",
    "Mato Grosso do Sul": "MS",
    "Minas Gerais": "MG",
    "Pará": "PA",
    "Paraíba": "PB",
    "Paraná": "PR",
    "Pernambuco": "PE",
    "Piauí": "PI",
    "Rio de Janeiro": "RJ",
    "Rio Grande do Norte": "RN",
    "Rio Grande do Sul": "RS",
    "Rondônia": "RO",
    "Roraima": "RR",
    "Santa Catarina": "SC",
    "São Paulo": "SP",
    "Sergipe": "SE",
    "Tocantins": "TO",
}

states = {}

for state, sigla in tempStates.items():
    states[state] = sigla
    states[state.upper()] = sigla
    states[state.lower()] = sigla
    states[unidecode.unidecode(state)] = sigla
    states[unidecode.unidecode(state.upper())] = sigla
    states[unidecode.unidecode(state.lower())] = sigla

def loadField(name, loaded_json):
    field = loaded_json.get(name)
    if field is not None:
        return " ".join(str(field).strip().split()).upper()
    return None

def selectOption(toSelect, options):
    for option in options:
        if option.startswith("(" + toSelect + ")"):
            return option
    return None


def parseOption(option):
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

@frappe.whitelist()
def signQz(message):
    key = serialization.load_pem_private_key(
        open("../apps/nfe_nfce_erpnext/nfe_nfce_erpnext/key.pem", "rb").read(),
        None,
        backend=default_backend(),
    )
    signature = key.sign(
        message.encode("utf-8"), padding.PKCS1v15(), hashes.SHA512()
    )  # Use hashes.SHA1() for QZ Tray 2.0 and older
    return str(base64.b64encode(signature))


@frappe.whitelist()
def emitirNotaFiscal(*args, **kwargs):

    loaded_json = None
    nota_db = None

    if kwargs.get("nota") is not None:
        nota_db = kwargs.get("nota")
    elif kwargs.get("source_name") is not None:
        loaded_json = json.loads(kwargs["source_name"])
    elif kwargs.get("doc") is not None:
        loaded_json = json.loads(kwargs["doc"])
    else:
        frappe.throw(
            title="Documento não encontrado",
            msg="O pedido para emitir a Nota Fiscal não foi encontrado.",
        )
        return json.dumps({"error": "Documento não encontrado."})

    if nota_db is None and loaded_json.get("docstatus") == 0:
        frappe.throw(
            title="Nota não submetida",
            msg="A Nota fiscal precisa ser submetida antes da emissão da mesma.",
        )
        return json.dumps(
            {
                "error": "Documento precisa ser submetido antes da emissão da Nota Fiscal."
            }
        )
    elif nota_db is None:
        nota_db = frappe.get_doc("Nota Fiscal", loaded_json.get("name"))

    if nota_db.docstatus != 1:
        frappe.throw(
            title="Nota não submetida",
            msg="A Nota fiscal precisa ser submetida antes da emissão da mesma.",
        )
        return json.dumps(
            {
                "error": "1 Documento precisa ser submetido antes da emissão da Nota Fiscal."
            }
        )

    settings = get_fiscal_provider().get_settings()

    result = {}
    result["operacao"] = int(parseOption(nota_db.operacao))
    result["natureza_operacao"] = nota_db.natureza_operacao
    result["modelo"] = int(parseOption(nota_db.modelo))
    result["finalidade"] = int(parseOption(nota_db.finalidade))
    result["ambiente"] = int(parseOption(nota_db.ambiente))
    if result["ambiente"] == 0:
        result["ambiente"] = settings["ambiente"]

    cliente = {}

    if nota_db.cpf is not None:
        cliente["cpf"] = nota_db.cpf
        cliente["nome_completo"] = nota_db.nome_completo
    elif nota_db.cnpj is not None:
        cliente["cnpj"] = nota_db.cnpj
        cliente["razao_social"] = nota_db.razao_social
        cliente["ie"] = nota_db.ie

    cliente["endereco"] = nota_db.endereco
    cliente["numero"] = nota_db.numero
    cliente["complemento"] = nota_db.complemento
    cliente["bairro"] = nota_db.bairro
    cliente["cidade"] = nota_db.cidade
    cliente["uf"] = parseOption(nota_db.uf)
    cliente["cep"] = nota_db.cep
    cliente["telefone"] = nota_db.telefone
    cliente["email"] = nota_db.email

    result["cliente"] = cliente

    produtos = []

    for item in nota_db.produtos:
        produto = {}
        produto["nome"] = item.get("nome")
        produto["codigo"] = item.get("codigo")
        produto["ncm"] = item.get("ncm")
        produto["quantidade"] = int(item.get("quantidade"))
        produto["unidade"] = parseOption(item.get("unidade"))
        produto["origem"] = int(parseOption(item.get("origem")))
        produto["subtotal"] = item.get("subtotal") - item.get("desconto")
        produto["total"] = item.get("total")
        produto["classe_imposto"] = item.get("classe_imposto")
        produto["cnpj_fabricante"] = item.get("cnpj_fabricante")
        produtos.append(produto)

    result["produtos"] = produtos

    pedido = {}
    pedido["presenca"] = int(parseOption(nota_db.presenca))
    pedido["modalidade_frete"] = int(parseOption(nota_db.modalidade_frete))
    pedido["frete"] = nota_db.frete
    pedido["desconto"] = nota_db.desconto
    pedido["informacoes_fisco"] = nota_db.informacoes_fisco
    pedido["informacoes_complementares"] = nota_db.informacoes_complementares
    pedido["observacoes_contribuinte"] = nota_db.observacoes_contribuinte

    pedido["pagamento"] = parseOption(nota_db.pagamento)
    pedido["desc_pagamento"] = nota_db.desc_pagamento
    if nota_db.formas_pagamento is not None and len(nota_db.formas_pagamento) > 0:
        pedido["forma_pagamento"] = []
        pedido["valor_pagamento"] = []
        for forma in nota_db.formas_pagamento:
            pedido["forma_pagamento"].append(parseOption(forma.forma_pagamento))
            pedido["valor_pagamento"].append(forma.valor_pagamento)
    else:
        pedido["forma_pagamento"] = parseOption(nota_db.forma_pagamento)
        pedido["valor_pagamento"] = nota_db.valor_pagamento
    
    result["pedido"] = pedido

    if pedido["modalidade_frete"] != 9:
        transporte = {}
        transporte["volume"] = nota_db.volume
        transporte["especie"] = nota_db.especie
        transporte["peso_bruto"] = nota_db.peso_bruto
        transporte["peso_liquido"] = nota_db.peso_liquido

        entrega = {}
        if nota_db.entrega_cnpj is not None:
            entrega["cnpj"] = int(nota_db.entrega_cnpj)
            entrega["razao_social"] = nota_db.entrega_razao_social
            if nota_db.entrega_ie is not None:
                entrega["ie"] = int(nota_db.entrega_ie)
        elif nota_db.entrega_cpf is not None:
            entrega["cpf"] = nota_db.entrega_cpf
            entrega["nome_completo"] = nota_db.entrega_nome_completo
        entrega["uf"] = parseOption(nota_db.entrega_uf)
        entrega["cep"] = nota_db.entrega_cep
        entrega["endereco"] = nota_db.entrega_endereco
        entrega["numero"] = nota_db.entrega_numero
        entrega["complemento"] = nota_db.entrega_complemento
        entrega["bairro"] = nota_db.entrega_bairro
        entrega["cidade"] = nota_db.entrega_cidade

        transporte["entrega"] = entrega
        result["transporte"] = transporte

    # TODO entrega_telefone e entrega_email não está sendo salvo nem carregado
    # if nota_db.entrega_telefone is not None:
    #    transporte["telefone"] = int(nota_db.entrega_telefone)
    # transporte["email"] = nota_db.entrega_email

    provider = get_fiscal_provider()
    returned_json = provider.emit_nota_fiscal(result)

    if returned_json.get("error") is not None:
        frappe.throw(title="Erro ao emitir nota fiscal", msg=response.text)
        return response.text

    if returned_json.get("status") == "reprovado":
        frappe.throw(title="Erro ao emitir nota fiscal", msg=response.text)
        return json.dumps({"error": returned_json.get("motivo")})

    if returned_json.get("status") == "aprovado":
        # TODO anexar o XML e a Danfe
        # print(nota_db.chave)
        nota_db.db_set("status", returned_json.get("status"), notify=True)
        nota_db.db_set("chave", returned_json.get("chave"), commit=True)
        # print(returned_json.get("danfe"))
        # add_attachments("Nota Fiscal", nota_db.name, [returned_json.get("danfe")]
        # f = save_url(returned_json.get("danfe"), returned_json.get("chave") + ".danfe.pdf", "Nota Fiscal", nota_db.name, None, True)
        # print(f.as_dict())
        # f.submit()
        # f.save()
        # f.insert()
        # f.notify_update()
        # print(f.is_remote_file)
        nota_db.notify_update()
        return json.dumps(
            {
                "success": True,
                "chave": returned_json.get("chave"),
                "modelo": returned_json.get("modelo"),
                "xml": returned_json.get("xml"),
                "danfe": returned_json.get("danfe"),
                "danfe_simples": returned_json.get("danfe_simples"),
                "danfe_etiqueta": returned_json.get("danfe_etiqueta"),
            }
        )

    frappe.throw(title="Erro desconhecido emitir nota fiscal", msg=response.text)
    return json.dumps({"error": "Erro desconhecido."})


@frappe.whitelist()
def imprimirNotaFiscal(*args, **kwargs):
    server_doc = None

    if kwargs.get("server_pos_invoice") is not None:
        server_doc = frappe.get_doc("POS Invoice", kwargs["server_pos_invoice"])
    else:
        frappe.throw(
            title="Pedido não encontrado",
            msg="Um pedido precisa existir antes de imprimir uma Nota fiscal.",
        )
        return json.dumps(
            {"error": "Um pedido precisa existir antes de imprimir uma Nota fiscal."}
        )

    if server_doc.nf_ultima_nota is None:
        frappe.throw(
            title="Nota não encontrada",
            msg="Uma Nota fiscal precisa existir antes de imprimir a mesma.",
        )
        return json.dumps(
            {"error": "Uma Nota fiscal precisa existir antes de imprimir a mesma."}
        )

    nota = frappe.get_doc("Nota Fiscal", server_doc.nf_ultima_nota)

    if nota.status == "processamento":
        frappe.throw(
            title="Nota em processamento",
            msg="A Nota fiscal ainda está em processamento.",
        )
        return json.dumps({"error": "A Nota fiscal ainda está em processamento."})

    if nota.status == "contingencia":
        frappe.throw(
            title="Nota em contingência", msg="A Nota fiscal está em contingência."
        )
        return json.dumps({"error": "A Nota fiscal está em contingência."})

    if nota.status != "aprovado":
        frappe.throw(title="Nota não aprovada", msg="A Nota fiscal não foi aprovada.")
        return json.dumps({"error": "A Nota fiscal não foi aprovada."})

    provider = get_fiscal_provider()
    danfe_url = provider.get_danfe_url(nota.chave, "danfe")
    html = requests.request("GET", danfe_url)

    return json.dumps({"html": html.text})


@frappe.whitelist()
def get_danfe_url(chave, format_type="danfe"):
    provider = get_fiscal_provider()
    return provider.get_danfe_url(chave, format_type)


@frappe.whitelist()
def criarNotaFiscal(*args, **kwargs):

    insert = kwargs.get("insert") if kwargs.get("insert") is not None else False
    submit = kwargs.get("submit") if kwargs.get("submit") is not None else False
    modelo = kwargs.get("modelo") if kwargs.get("modelo") is not None else 2
    if isinstance(modelo, str):
        modelo = int(modelo)

    server_doc = None
    # TODO migrar para apenas server_doc para conferência do pedido
    if kwargs.get("server_pos_invoice") is not None:
        if isinstance(kwargs["server_pos_invoice"], str):
            server_doc = frappe.get_doc("POS Invoice", kwargs["server_pos_invoice"])
        else:
            server_doc = frappe.get_doc("POS Invoice", kwargs["server_pos_invoice"].name)
    elif kwargs.get("server_invoice") is not None:
        if isinstance(kwargs["server_invoice"], str):
            server_doc = frappe.get_doc("Sales Invoice", kwargs["server_invoice"])
        else:
            server_doc = frappe.get_doc("Sales Invoice", kwargs["server_invoice"].name)
    else:
        frappe.throw(
            title="Pedido não encontrado",
            msg="Um pedido precisa existir antes de criar uma Nota fiscal.",
        )
        return json.dumps(
            {"error": "Um pedido precisa existir antes de criar uma Nota fiscal."}
        )

    if server_doc.nf_ultima_nota is not None:
        ultima = frappe.get_doc("Nota Fiscal", server_doc.nf_ultima_nota)
        if ultima.docstatus.is_draft():
            return ultima
        elif ultima.docstatus.is_submitted():
            if (
                ultima.status == "aprovado"
                or ultima.status == "processamento"
                or ultima.status == "contingencia"
            ):
                return ultima

    nota = frappe.new_doc("Nota Fiscal")

    nota.id = server_doc.name[-15:]
    customer = server_doc.customer

    nota.modelo = selectOption(
        str(modelo),
        frappe.get_meta("Nota Fiscal").get_field("modelo").options.split("\n"),
    )
    modelo = parseOption(nota.modelo)

    customer = frappe.get_cached_doc("Customer", customer)
    linked = get_linked_docs(
        "Customer", customer.name, linkinfo=get_linked_doctypes("Customer")
    )

    if customer.tax_id is not None:
        if customer.customer_type == "Company":
            nota.cnpj = re.sub("\D", "", customer.tax_id)
            nota.razao_social = customer.nf_razao_social
            nota.ie = customer.nf_inscricao_estadual
        elif customer.customer_type == "Individual":
            nota.cpf = re.sub("\D", "", customer.tax_id)
            nota.nome_completo = customer.customer_name

    # TODO calcular "Consumidor Final" e "Contribuinte"

    contacts = linked.get("Contact")

    for contact in contacts:
        contact = frappe.get_cached_doc("Contact", contact.name)
        if contact.is_billing_contact == 1:
            if contact.email_id is not None and nota.email is None:
                nota.email = contact.email_id
            if contact.phone is not None and nota.telefone is None:
                nota.telefone = re.sub("\D", "", contact.phone)

    if (modelo == 1 or modelo == "1") and customer.customer_primary_address is not None and (nota.email is None or nota.telefone is None):
        primary_address = frappe.get_cached_doc("Address", customer.customer_primary_address)
        if nota.email is None:
            nota.email = primary_address.email_id
        if nota.telefone is None:
            nota.telefone = primary_address.phone

    if (modelo == 1 or modelo == "1") and customer.customer_primary_contact is not None and (nota.email is None or nota.telefone is None):
        primary_contact = frappe.get_cached_doc("Contact", customer.customer_primary_contact)
        if nota.email is None:
            nota.email = (
                primary_contact.email_id
                if nota.email is None
                else nota.email + "," + primary_contact.email_id
            )
        if nota.telefone is None:
            nota.telefone = (
                primary_contact.phone
                if nota.telefone is None
                else nota.telefone + "," + primary_contact.phone
            )

    # TODO retornou empty mesmo tendo salvo
    addresses = linked.get("Address")

    if addresses is None or len(addresses) == 0:
        addresses = get_linked_docs(
            "Contact", linked.get("Contact")[0].name, linkinfo=get_linked_doctypes("Contact")
        )      
    if modelo == 1 or modelo == "1":
        for address in addresses:
            address = frappe.get_cached_doc("Address", address.name)
            if address.address_type == "Billing":
                if (
                    address.city is not None
                    and address.address_line1 is not None
                    and address.pincode is not None
                ):
                    nota.endereco = address.address_line1
                    nota.numero = address.number
                    nota.complemento = address.address_line2
                    nota.bairro = address.neighborhood
                    nota.cidade = address.city
                    nota.uf = selectOption(
                        (
                            states.get(address.state)
                            if address.state in states
                            else states.get(address.state.lower())
                        ),
                        frappe.get_meta("Nota Fiscal")
                        .get_field("uf")
                        .options.split("\n"),
                    )
                    nota.cep = re.sub("\D", "", address.pincode)
                    if nota.email is None:
                        nota.email = (
                            address.email_id
                            if nota.email is None
                            else (
                                nota.email + "," + address.email_id
                                if address.email_id is not None
                                else nota.email
                            )
                        )
                    nota.telefone = re.sub(
                        "\D",
                        "",
                        address.phone if nota.telefone is None else nota.telefone,
                    )

            if address.address_type == "Shipping" or address.is_shipping_address == 1:
                if (
                    address.city is not None
                    and address.address_line1 is not None
                    and address.pincode is not None
                ):
                    if customer.customer_type == "Company":
                        nota.entrega_cnpj = nota.cnpj
                        nota.entrega_razao_social = customer.nf_razao_social
                        nota.entrega_ie = customer.nf_inscricao_estadual
                    elif customer.customer_type == "Individual":
                        nota.entrega_cpf = nota.cpf
                        nota.entrega_nome_completo = customer.customer_name

                    nota.entrega_endereco = address.address_line1
                    nota.entrega_numero = address.number
                    nota.entrega_complemento = address.address_line2
                    nota.entrega_bairro = address.neighborhood
                    nota.entrega_cidade = address.city
                    nota.entrega_uf = selectOption(
                        (
                            states.get(address.state)
                            if address.state in states
                            else states.get(address.state.lower())
                        ),
                        frappe.get_meta("Nota Fiscal")
                        .get_field("uf")
                        .options.split("\n"),
                    )
                    nota.entrega_cep = re.sub("\D", "", address.pincode)

    for item in server_doc.items:
        produto = frappe.new_doc("Produto")
        produto_loaded = frappe.get_doc("Item", item.get("item_code"))

        if not produto_loaded.get("nf_ncm") or not produto_loaded.get("nf_uom") or not produto_loaded.get("nf_classe_imposto") or not produto_loaded.get("nf_origem"):
            if produto_loaded.get("item_name") == "Frete":
                nota.frete += item.get("amount")
                nota.modalidade_frete = selectOption(
                    str(3),
                    frappe.get_meta("Nota Fiscal")
                    .get_field("modalidade_frete")
                    .options.split("\n"),
                )
                continue
            frappe.throw(
                title="Produto não configurado",
                msg="O produto "
                + produto_loaded.get("item_name")
                + " não está configurado para emissão de Nota Fiscal.",
            )
            return json.dumps(
                {
                    "error": "O produto "
                    + produto_loaded.get("item_name")
                    + " não está configurado para emissão de Nota Fiscal."
                }
            )

        produto.nome = produto_loaded.get("item_name")
        produto.codigo = produto_loaded.get("item_code")
        produto.ncm = re.sub("\D", "", produto_loaded.get("nf_ncm"))
        produto.quantidade = item.get("qty")
        produto.unidade = produto_loaded.get("nf_uom")
        produto.origem = produto_loaded.get("nf_origem")
        produto.desconto = item.get("discount_amount")
        produto.subtotal = item.get("price_list_rate")
        produto.total = produto.subtotal * produto.quantidade
        produto.classe_imposto = produto_loaded.get("nf_classe_imposto")
        produto.cnpj_fabricante = produto_loaded.get("nf_cnpj_fabricante")

        nota.produtos.append(produto)

    x = 0
    nota.valor_pagamento = None
    nota.forma_pagamento = None
    sem_pagamento = selectOption(
        str(90),
        frappe.get_meta("Nota Fiscal").get_field("forma_pagamento").options.split("\n"),
    )
    for payment in server_doc.payments:
        mode_of_payment = frappe.get_doc(
            "Mode of Payment",
            (
                payment.get("mode_of_payment")
                if isinstance(payment, dict)
                else payment.mode_of_payment
            ),
        )
        amnt = payment.get("amount") if isinstance(payment, dict) else payment.amount
        if amnt is None or amnt == 0 or amnt == "0" or amnt == "" or not amnt:
            continue
        if x == 0:
            nota.valor_pagamento = amnt
            nota.forma_pagamento = mode_of_payment.nf_forma_de_pagamento
        elif x == 1:
            forma = frappe.new_doc("Forma de Pagamento")
            forma.forma_pagamento = mode_of_payment.nf_forma_de_pagamento
            forma.valor_pagamento = amnt
            nota.formas_pagamento.append(forma)

            forma = frappe.new_doc("Forma de Pagamento")
            forma.forma_pagamento = nota.forma_pagamento
            forma.valor_pagamento = nota.valor_pagamento
            nota.formas_pagamento.append(forma)
            nota.forma_pagamento = None
            nota.valor_pagamento = None
        else:
            forma = frappe.new_doc("Forma de Pagamento")
            forma.forma_pagamento = mode_of_payment.nf_forma_de_pagamento
            forma.valor_pagamento = amnt
            nota.formas_pagamento.append(forma)
        x = x + 1
    if nota.formas_pagamento is not None and len(nota.formas_pagamento) > 1:
        for forma in nota.formas_pagamento:
            if forma.valor_pagamento == sem_pagamento:
                frappe.throw(
                    title="Pagamento inválido",
                    msg="Não é permitido dividir o pagamento para pagar depois.",
                )
                return json.dumps(
                    {"error": "Não é permitido dividir o pagamento para pagar depois."}
                )

    if server_doc.discount_amount is not None and server_doc.discount_amount > 0:
        nota.desconto += server_doc.discount_amount

    if server_doc.loyalty_points is not None and server_doc.loyalty_points > 0 and server_doc.loyalty_amount is not None and server_doc.loyalty_amount > 0:
        nota.desconto += server_doc.loyalty_amount

    nota.link_id = server_doc.name
    nota.link = server_doc.doctype

    if parseOption(nota.ambiente) == "0":
        provider = get_fiscal_provider()
        ambiente_val = provider.get_settings().get("ambiente", 2)
        nota.ambiente = selectOption(
            str(ambiente_val),
            ["(1) - Produção", "(2) - Homologação"],
        )

    if insert and server_doc is not None and nota.forma_pagamento != sem_pagamento:
        # print("Inserting")
        nota.insert()
        nota.save()
        server_doc.db_set("nf_ultima_nota", nota.name, notify=True, commit=True)
        frappe.db.commit()
        #server_doc.save()

        if submit:
            nota.submit()
            frappe.db.commit()

    return nota

    # Produtos
    # item (sku) / nome / ncm / quantidade / unidade (medida) / peso (em kg) / origem / desconto (individual) / subtotal (valor integral sem desconto) / total ((subtotal - desconto) * quantidade) / classe_imposto / cnpj_fabricante

    # Pedido
    # presenca / modalidade_frete / frete / desconto / total / informacoes_fisco / informacoes_complementares / observacoes_contribuinte

    # Pedido - Pagamento
    # pagamento / forma_pagamento / desc_pagamento / valor_pagamento

    # Pedido - Fatura

    # Pedido - Parcelas

    # Transporte
    # volume / especie / peso_bruto / peso_liquido

    # Transporte - Entrega
    # cnpj / nome / ie / cpf / nome_completo / uf / cep / endereco / numero / complemento / bairro / cidade / telefone / email

    # print(result)

def make_sales_invoice(source_name, target_doc=None, ignore_permissions=False):
	def postprocess(source, target):
		set_missing_values(source, target)
		target.is_pos = False

	def set_missing_values(source, target):
		target.flags.ignore_permissions = True
		target.run_method("set_missing_values")
		target.run_method("set_po_nos")
		target.run_method("calculate_taxes_and_totals")
		target.run_method("set_use_serial_batch_fields")

		if source.company_address:
			target.update({"company_address": source.company_address})
		else:
			# set company address
			target.update(get_company_address(target.company))

		if target.company_address:
			target.update(get_fetch_values("Sales Invoice", "company_address", target.company_address))

		target.debit_to = get_party_account("Customer", source.customer, source.company)

	def update_item(source, target, source_parent):
		target.amount = flt(source.amount)
		target.base_amount = target.amount
		target.qty = source.qty

		if target.item_code:
			item = get_item_defaults(target.item_code, source_parent.company)
			item_group = get_item_group_defaults(target.item_code, source_parent.company)
			cost_center = item.get("selling_cost_center") or item_group.get("selling_cost_center")

			if cost_center:
				target.cost_center = cost_center

	doclist = get_mapped_doc(
		"POS Invoice",
		source_name,
		{
			"POS Invoice": {
				"doctype": "Sales Invoice",
			},
			"POS Invoice Item": {
				"doctype": "Sales Invoice Item",
				"postprocess": update_item,
			},
		},
		target_doc,
		postprocess,
		ignore_permissions=ignore_permissions,
	)

	return doclist

def criarSalesInvoice(*args, **kwargs):
    insert = kwargs.get("insert") if kwargs.get("insert") is not None else False
    submit = kwargs.get("submit") if kwargs.get("submit") is not None else False

    server_doc = None

    if kwargs.get("server_pos_invoice") is not None:
        if isinstance(kwargs["server_pos_invoice"], str):
            server_doc = frappe.get_doc("POS Invoice", kwargs["server_pos_invoice"])
        else:
            server_doc = frappe.get_doc("POS Invoice", kwargs["server_pos_invoice"].name)
    else:
        frappe.throw(
            title="Pedido não encontrado",
            msg="Um pedido precisa existir antes de criar uma Nota fiscal.",
        )
        return json.dumps(
            {"error": "Um pedido precisa existir antes de criar uma Nota fiscal."}
        )

    invoice = make_sales_invoice(server_doc.name)
    invoice.insert()
    invoice.save()
    invoice.submit()
    frappe.db.commit()

@frappe.whitelist()
def pullDataCNPJ(*args, **kwargs):

    doc = kwargs["doc"]
    cnpj = kwargs["cnpj"]
    doctype = kwargs["doctype"]
    if cnpj is not None:

        cnpj = re.sub("\D", "", cnpj)

        response = requests.request("GET", "https://publica.cnpj.ws/cnpj/" + cnpj)
        dados = json.loads(response.text)

        razao_social = loadField("razao_social", dados)
        estabelecimento = dados.get("estabelecimento")
        nome_fantasia = loadField("nome_fantasia", estabelecimento)
        tipo_logradouro = loadField("tipo_logradouro", estabelecimento)
        logradouro = loadField("logradouro", estabelecimento)
        numero = loadField("numero", estabelecimento)
        complemento = loadField("complemento", estabelecimento)
        bairro = loadField("bairro", estabelecimento)
        cep = loadField("cep", estabelecimento)
        pais = loadField("nome", estabelecimento.get("pais"))
        estado = loadField("nome", estabelecimento.get("estado"))
        cidade = loadField("nome", estabelecimento.get("cidade"))
        email = loadField("email", estabelecimento)
        dd1 = loadField("ddd1", estabelecimento)
        telefone1 = loadField("telefone1", estabelecimento)
        telefone = None
        if dd1 is not None and telefone1 is not None:
            telefone = re.sub("\D", "", dd1 + telefone1)
            phone = phonenumbers.parse(telefone, "BR")
            phone = phonenumbers.format_number(
                phone, phonenumbers.PhoneNumberFormat.E164
            )
            phone = phone
            final = phone[5:]
            if len(final) == 8:
                final = final[:4] + "-" + final[4:]
            else:
                final = final[:5] + "-" + final[5:]
            telefone = phone[:3] + " " + phone[3:5] + " " + final

        customer = frappe.get_doc(doctype, doc)

        inscricoes_estaduais = estabelecimento.get("inscricoes_estaduais")
        if len(inscricoes_estaduais) == 1:
            inscricao_estadual = inscricoes_estaduais[0].get("inscricao_estadual")
            customer.nf_inscricao_estadual = inscricao_estadual

        customer.nf_razao_social = razao_social

        # Get linked addresses cleanly without get_linked_doctypes (bypasses missing HR module)
        address_links = frappe.get_all("Dynamic Link", filters={"link_doctype": doctype, "link_name": customer.name, "parenttype": "Address"}, fields=["parent"])

        if not address_links:
            address = frappe.new_doc("Address")
            address.address_title = f"{customer.name}-Cadastro"
            address.address_line1 = f"{tipo_logradouro} {logradouro}" if tipo_logradouro else (logradouro or "")
            address.number = numero or ""
            address.address_line2 = complemento or ""
            address.neighborhood = bairro or ""
            address.city = cidade or ""
            address.state = estado or ""
            address.pincode = cep or ""
            address.email_id = email or ""
            address.phone = telefone or ""
            address.append("links", {
                "link_doctype": doctype,
                "link_name": customer.name
            })
            address.insert(ignore_permissions=True)

        customer.save(ignore_permissions=True)
        frappe.db.commit()
        customer.notify_update()

        # TODO recarregar a página após salvar

@frappe.whitelist()
def forceCancelDocument(*args, **kwargs):
    source_name = kwargs.get("source_name")
    if source_name is None:
        frappe.throw(
            title="Documento não encontrado",
            msg="O documento que você está tentando cancelar não foi encontrado.",
        )
        return json.dumps({"error": "Documento não encontrado."})
    
    # Get the document by name
    try:
        doc = frappe.get_doc("POS Invoice", source_name)
    except frappe.DoesNotExistError:
        frappe.throw(
            title="Documento não encontrado",
            msg="O documento que você está tentando cancelar não foi encontrado.",
        )
        return json.dumps({"error": "Documento não encontrado."})
    if doc.doctype not in ["POS Invoice"]:
        frappe.throw(
            title="Documento inválido",
            msg="O documento que você está tentando cancelar não é um documento válido para esta operação.",
        )
        return json.dumps({"error": "Documento inválido."})
    if doc.docstatus == 0:
        frappe.throw(
            title="Documento não submetido",
            msg="O documento que você está tentando cancelar não foi submetido.",
        )
        return json.dumps({"error": "Documento não submetido."})
    
    if doc.doctype == "POS Invoice":
        nota_ref = doc.nf_ultima_nota
        consolidated_ref = doc.consolidated_invoice
        
        doc.db_set("nf_ultima_nota", None, commit=False)
        doc.db_set("consolidated_invoice", None, commit=False)
        frappe.db.commit()
        
        if nota_ref:
            nota = frappe.get_doc("Nota Fiscal", nota_ref)
            nota.flags.ignore_links = True
            nota.cancel()
        
        if consolidated_ref:
            consolidated = frappe.get_doc("Sales Invoice", consolidated_ref)
            consolidated.flags.ignore_links = True
            consolidated.cancel()
        
        doc.reload()
        doc.cancel()

    return json.dumps({"success": True, "message": "Documento cancelado com sucesso."})


def updatePosInvoice(doc, method=None):
    return

def submitPosInvoice(doc, method=None):
    print(doc)
    nota = criarNotaFiscal(server_pos_invoice=doc, insert=True, submit=True, modelo=2)
    if parseOption(nota.forma_pagamento) == 90 or parseOption(nota.forma_pagamento) == "90":
        # TODO Criar Sales Invoice
        t = criarSalesInvoice(server_pos_invoice=doc)
        print(t)
        doc.cancel()
        frappe.db.commit()
    else:
        emitida = emitirNotaFiscal(nota=nota)
    return

def beforeInsertLoyaltyPointEntry(doc, method=None):
    if doc is not None:
        invoice = frappe.get_cached_doc(doc.invoice_type, doc.invoice)
        program = frappe.get_cached_doc("Loyalty Program", doc.loyalty_program)
        if program is not None and program is not None:
            for payment in program.mode_of_payment_multiplier:
                for invoice_payment in invoice.payments:
                    if payment.mode_of_payment == invoice_payment.mode_of_payment:
                        doc.loyalty_points += invoice_payment.amount * payment.amount / program.conversion_factor
    return

def afterSaveItemPrice(doc, method=None):
    if doc is not None and doc.price_list == "Revenda":
        ll = frappe.db.get_all("Item Price", filters={"item_code": doc.item_code}, fields=["price_list", "name", "price_list_rate"], order_by="price_list_rate")
        if ll is not None and len(ll) == 2:    
            revenda = ll[0] if ll[0].price_list == "Revenda" else ll[1]
            cliente = ll[0] if ll[0].price_list == "Cliente" else ll[1]

            rules = frappe.db.get_all("Pricing Rule Item Code", filters={"item_code": doc.item_code}, fields=["parent"])
            if rules is not None and len(rules) == 1:
                frappe.db.set_value("Pricing Rule", rules[0].parent, "rate", revenda.price_list_rate)
            elif rules is None or len(rules) == 0:
                rule = frappe.new_doc("Pricing Rule")
                rule.apply_on = "Item Code"
                rule.price_or_product_discount = "Price"
                rule.selling = 1
                rule.applicable_for = "Customer Group"
                rule.customer_group = "Revenda"
                rule.rate_or_discount = "Rate"
                rule.rate = revenda.price_list_rate
                rule.append("items", {"item_code": doc.item_code})
                rule.title = doc.item_name
                rule.insert()
    return


@frappe.whitelist(allow_guest=True)
def parse_qr(qr_url: str = None, **kwargs):
    if not qr_url or qr_url == "qr_url":
        qr_url = frappe.form_dict.get("qr_url") or kwargs.get("qr_url")
    from nfe_nfce_erpnext.nfce_scanner import parse_qr as _parse_qr
    return _parse_qr(qr_url=qr_url, **kwargs)


@frappe.whitelist(allow_guest=True)
def parse_sefaz_html(invoice_name: str = None, html_content: str = None, **kwargs):
    try:
        if not invoice_name:
            invoice_name = frappe.form_dict.get("invoice_name") or kwargs.get("invoice_name")
        if not html_content:
            html_content = frappe.form_dict.get("html_content") or kwargs.get("html_content")

        from nfe_nfce_erpnext.nfce_scanner import parse_sefaz_html as _parse_sefaz_html
        return _parse_sefaz_html(invoice_name=invoice_name, html_content=html_content)
    except Exception as e:
        frappe.log_error(f"parse_sefaz_html Exception: {str(e)}", "NFC-e Wrapper Exception")
        return {"status": "error", "error": str(e)}


@frappe.whitelist()
def create_permanent_supplier(invoice_name: str, supplier_name: str = None):
    if not frappe.has_permission("Supplier", "create"):
        frappe.throw("Permissão negada para criar Fornecedor.", frappe.PermissionError)

    pi = frappe.get_doc("Purchase Invoice", invoice_name)
    remarks = pi.remarks or ""

    cnpj_match = re.search(r"(\d{14})", remarks)
    tax_id = cnpj_match.group(1) if cnpj_match else ""

    from nfe_nfce_erpnext.sefaz_sync import get_or_create_supplier
    permanent_name = supplier_name or (f"Fornecedor CNPJ {tax_id}" if tax_id else "Novo Fornecedor NFC-e")

    supplier_docname = get_or_create_supplier(tax_id, permanent_name, auto_create=True)

    pi.supplier = supplier_docname
    pi.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "success", "supplier": supplier_docname, "message": f"Fatura vinculada ao Fornecedor '{supplier_docname}'!"}


@frappe.whitelist()
def bulk_submit_invoices(docnames):
    if isinstance(docnames, str):
        import json
        docnames = json.loads(docnames)

    if not frappe.has_permission("Purchase Invoice", "submit"):
        frappe.throw("Permissão negada para submeter Faturas de Compra.", frappe.PermissionError)

    submitted_invoices = 0
    submitted_payments = 0

    for name in docnames:
        pi = frappe.get_doc("Purchase Invoice", name)
        if pi.docstatus == 0:
            pi.submit()
            submitted_invoices += 1

            # Specifically for this bulk review button: auto-submit linked Draft Payment Entries
            linked_pe_names = frappe.get_all(
                "Payment Entry Reference",
                filters={"reference_doctype": "Purchase Invoice", "reference_name": name, "docstatus": 0},
                fields=["parent"]
            )

            for pe_ref in linked_pe_names:
                pe_name = pe_ref.parent
                if frappe.db.get_value("Payment Entry", pe_name, "docstatus") == 0:
                    pe_doc = frappe.get_doc("Payment Entry", pe_name)
                    pe_doc.submit()
                    submitted_payments += 1

    frappe.db.commit()

    msg = f"{submitted_invoices} faturas aprovadas com sucesso!"
    if submitted_payments > 0:
        msg += f" ({submitted_payments} pagamentos vinculados também submetidos)"

    return {"status": "success", "message": msg}


@frappe.whitelist()
def get_document_share_key(doctype, name):
    """Generate or retrieve a Document Share Key for public PDF access without login."""
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    key = doc.get_document_share_key(no_expiry=True)
    frappe.db.commit()
    return key
