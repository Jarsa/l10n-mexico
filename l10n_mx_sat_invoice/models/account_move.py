# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import re
from datetime import datetime

from lxml import etree

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

CFDI_CODE_TO_TAX_TYPE = {"001": "isr", "002": "iva", "003": "ieps"}
GENERIC_RFCS = ("XAXX010101000", "XEXX010101000")
FOREIGN_RFC = "XEXX010101000"
# SAT product keys of fuels (gasoline, diesel...). Fuel sellers do not break
# down the IEPS: the amount of the concept includes it and only the VAT is
# listed, with a base lower than the amount.
FUEL_PRODUCT_KEYS = {str(code) for code in range(15101500, 15101516)}
IMPLOCAL_NS = "http://www.sat.gob.mx/implocal"
ECC12_NS = "http://www.sat.gob.mx/EstadoDeCuentaCombustible12"


class AccountMove(models.Model):
    _inherit = "account.move"

    l10n_mx_sat_document_id = fields.Many2one(
        comodel_name="l10n_mx_sat.document",
        string="SAT CFDI",
        readonly=True,
        copy=False,
        index="btree_not_null",
    )

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    @api.model
    def _l10n_mx_sat_create_invoice(self, document, journal, account):
        """Create the draft invoice of a CFDI downloaded from the SAT.

        :param document: l10n_mx_sat.document record with its XML
        :param journal: sale or purchase account.journal
        :param account: account.account of the lines whose product has no
            income/expense account
        :return: the created account.move
        """
        # ponytail: parsed here, not in a document helper: l10n_mx_sat_purchase
        # defines its own _get_cfdi_tree with other semantics.
        tree = etree.fromstring(document.attachment_id.with_context(bin_size=False).raw)
        voucher_type = tree.get("TipoDeComprobante")
        if voucher_type not in ("I", "E"):
            raise UserError(
                self.env._(
                    "The CFDI %(uuid)s is of type %(type)s: only invoices (I) "
                    "and credit notes (E) can be imported.",
                    uuid=document.uuid,
                    type=voucher_type,
                )
            )
        prefix = "out_" if document.direction == "issued" else "in_"
        move_type = prefix + ("refund" if voucher_type == "E" else "invoice")
        company = journal.company_id
        move = self.with_company(company).create(
            {
                "move_type": move_type,
                "journal_id": journal.id,
                "company_id": company.id,
            }
        )
        with move._get_edi_creation() as move:
            move._l10n_mx_sat_fill_invoice(tree, document, account)
        attachment = self.env["ir.attachment"].create(
            {
                "name": document.attachment_id.name or f"{document.uuid}.xml",
                "raw": document.attachment_id.raw,
                "mimetype": "application/xml",
                "res_model": self._name,
                "res_id": move.id,
            }
        )
        move._l10n_mx_sat_after_import(tree, document, attachment)
        return move

    def _l10n_mx_sat_after_import(self, tree, document, attachment):
        """Hook called once the invoice is filled and the XML attached."""
        self.ensure_one()
        document._link_invoice(self)
        body = self.env._(
            "Invoice created from the SAT CFDI %(uuid)s.", uuid=document.uuid
        )
        related = tree.find("{*}CfdiRelacionados")
        if related is not None:
            uuids = ", ".join(
                node.get("UUID") for node in related.findall("{*}CfdiRelacionado")
            )
            body += " " + self.env._(
                "Related CFDIs (%(relation)s): %(uuids)s.",
                relation=related.get("TipoRelacion"),
                uuids=uuids,
            )
        total = float(tree.get("Total") or 0)
        if self.currency_id.compare_amounts(self.amount_total, total):
            body += " " + self.env._(
                "The total of the invoice (%(invoice)s) differs from the total "
                "of the CFDI (%(cfdi)s): review the lines and the taxes.",
                invoice=self.amount_total,
                cfdi=total,
            )
        self.message_post(body=body, attachment_ids=attachment.ids)

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _l10n_mx_sat_fill_invoice(self, tree, document, account):
        self.ensure_one()
        partner = self._l10n_mx_sat_find_partner(tree)
        currency_name = tree.get("Moneda") or "MXN"
        currency = (
            self.env["res.currency"]
            .with_context(active_test=False)
            .search([("name", "=", currency_name)], limit=1)
        )
        if not currency.active:
            raise UserError(
                self.env._(
                    "The currency %(currency)s of the CFDI %(uuid)s is not active.",
                    currency=currency_name,
                    uuid=document.uuid,
                )
            )
        self.write(
            {
                "partner_id": partner.id,
                "currency_id": currency.id,
                "invoice_date": datetime.strptime(
                    tree.get("Fecha")[:10], "%Y-%m-%d"
                ).date(),
                "ref": "-".join(filter(None, [tree.get("Serie"), tree.get("Folio")])),
                "l10n_mx_sat_document_id": document.id,
            }
        )
        self.write(
            {
                "invoice_line_ids": [
                    Command.create(vals)
                    for vals in self._l10n_mx_sat_prepare_invoice_lines(tree, account)
                ]
            }
        )

    def _l10n_mx_sat_find_partner(self, tree):
        """Partner of the CFDI: the receiver of issued CFDIs, the issuer of
        received ones. Created when it does not exist."""
        self.ensure_one()
        role = "Receptor" if self.is_sale_document() else "Emisor"
        node = tree.find("{*}" + role)
        rfc = (node.get("Rfc") or "").strip().upper()
        name = node.get("Nombre")
        Partner = self.env["res.partner"]
        if rfc in GENERIC_RFCS:
            partner = Partner._retrieve_partner(name=name, company=self.company_id)
        else:
            partner = Partner._retrieve_partner(
                name=name, vat=rfc, company=self.company_id
            )
        if partner or not name:
            return partner
        vals = {"name": name}
        if rfc != FOREIGN_RFC:
            vals["country_id"] = self.env.ref("base.mx").id
        if rfc not in GENERIC_RFCS:
            vals["vat"] = rfc
            if role == "Receptor":
                vals["zip"] = node.get("DomicilioFiscalReceptor")
        return Partner.create(vals)

    # ------------------------------------------------------------------
    # Lines
    # ------------------------------------------------------------------

    def _l10n_mx_sat_prepare_invoice_lines(self, tree, account):
        """Values of the invoice lines of the CFDI ``tree``."""
        self.ensure_one()
        ecc12 = tree.find(f".//{{{ECC12_NS}}}EstadoDeCuentaCombustible")
        if ecc12 is not None:
            lines = self._l10n_mx_sat_prepare_ecc12_lines(ecc12, account)
        else:
            lines = []
            for concept in tree.findall("{*}Conceptos/{*}Concepto"):
                lines += self._l10n_mx_sat_prepare_concept_lines(concept, account)
        return lines + self._l10n_mx_sat_prepare_local_tax_lines(tree, account)

    def _l10n_mx_sat_prepare_concept_lines(self, concept, account):
        """Values of the invoice lines of a CFDI concept.

        One line per concept, except when the taxes do not apply to the whole
        amount: fuels (the IEPS is included in the amount and not broken down)
        and concepts where the IEPS applies to part of the base (e.g.
        telecommunications) are split in two lines so the taxes computed by
        Odoo match the CFDI.
        """
        name = concept.get("Descripcion") or concept.get("ClaveProdServ") or ""
        quantity = float(concept.get("Cantidad") or 1)
        price_unit = float(concept.get("ValorUnitario") or 0)
        amount = float(concept.get("Importe") or 0)
        discount_amount = float(concept.get("Descuento") or 0)
        net = amount - discount_amount
        product = self._l10n_mx_sat_find_product(concept)
        base_vals = {
            "product_id": product.id,
            "name": name,
            "account_id": self._l10n_mx_sat_get_line_account(product, account).id,
            "quantity": 1,
        }
        transfers = [
            self._l10n_mx_sat_parse_tax_node(node)
            for node in concept.findall("{*}Impuestos/{*}Traslados/{*}Traslado")
        ]
        withholdings = [
            self._l10n_mx_sat_parse_tax_node(node, withholding=True)
            for node in concept.findall("{*}Impuestos/{*}Retenciones/{*}Retencion")
        ]
        iva = [tax for tax in transfers if tax["type"] == "iva"]
        ieps = [
            tax
            for tax in transfers
            if tax["type"] == "ieps" and tax["factor"] == "Tasa"
        ]
        if (
            concept.get("ClaveProdServ") in FUEL_PRODUCT_KEYS
            and iva
            and not ieps
            and float_compare(iva[0]["base"], net, precision_digits=2) < 0
        ):
            # ponytail: the IEPS of fuels is the amount not covered by the VAT base
            base = iva[0]["base"]
            return [
                {
                    **base_vals,
                    "price_unit": base,
                    "tax_ids": [
                        Command.set(
                            self._l10n_mx_sat_find_taxes(iva + withholdings).ids
                        )
                    ],
                },
                {
                    **base_vals,
                    "name": self.env._("%s (IEPS)", name),
                    "price_unit": self.currency_id.round(net - base),
                    "tax_ids": [Command.clear()],
                },
            ]
        if iva and ieps:
            # Part of the amount without IEPS: VAT base = IEPS base + IEPS + rest
            rest = self.currency_id.round(
                iva[0]["base"] - ieps[0]["base"] - ieps[0]["amount"]
            )
            if rest > 0:
                return [
                    {
                        **base_vals,
                        "price_unit": ieps[0]["base"],
                        "tax_ids": [
                            Command.set(
                                self._l10n_mx_sat_find_taxes(
                                    iva + ieps + withholdings
                                ).ids
                            )
                        ],
                    },
                    {
                        **base_vals,
                        "price_unit": rest,
                        "tax_ids": [
                            Command.set(
                                self._l10n_mx_sat_find_taxes(iva + withholdings).ids
                            )
                        ],
                    },
                ]
        taxes = self._l10n_mx_sat_find_taxes(transfers + withholdings)
        return [
            {
                **base_vals,
                "quantity": quantity,
                "price_unit": price_unit,
                "discount": discount_amount / amount * 100 if amount else 0,
                "tax_ids": [Command.set(taxes.ids)],
            }
        ]

    def _l10n_mx_sat_prepare_ecc12_lines(self, ecc12, account):
        """Lines of a fuel account statement (complement ECC 1.2): one line
        per operation with the VAT base and one with the IEPS, which the
        complement does not break down."""
        lines = []
        for concept in ecc12.findall(
            "{*}Conceptos/{*}ConceptoEstadoDeCuentaCombustible"
        ):
            amount = float(concept.get("Importe") or 0)
            transfers = [
                self._l10n_mx_sat_parse_tax_node(node)
                for node in concept.findall("{*}Traslados/{*}Traslado")
            ]
            iva = [tax for tax in transfers if tax["type"] == "iva"]
            ieps_amount = sum(
                tax["amount"] for tax in transfers if tax["type"] == "ieps"
            )
            # The ECC 1.2 taxes have no base: deduce it from the VAT amount
            base = (
                round(iva[0]["amount"] / (iva[0]["rate"] / 100), 2)
                if iva and iva[0]["rate"]
                else amount
            )
            name = self.env._(
                "Station %(station)s - Operation %(operation)s",
                station=concept.get("ClaveEstacion"),
                operation=concept.get("FolioOperacion"),
            )
            lines.append(
                {
                    "name": name,
                    "account_id": account.id,
                    "quantity": 1,
                    "price_unit": base,
                    "tax_ids": [Command.set(self._l10n_mx_sat_find_taxes(iva).ids)],
                }
            )
            ieps = self.currency_id.round(amount - base + ieps_amount)
            if ieps:
                lines.append(
                    {
                        "name": self.env._("%s (IEPS)", name),
                        "account_id": account.id,
                        "quantity": 1,
                        "price_unit": ieps,
                        "tax_ids": [Command.clear()],
                    }
                )
        return lines

    def _l10n_mx_sat_prepare_local_tax_lines(self, tree, account):
        """Local taxes (complement ImpuestosLocales) as lines without taxes."""
        lines = []
        for tag, attr, sign in (
            ("TrasladosLocales", "ImpLocTrasladado", 1),
            ("RetencionesLocales", "ImpLocRetenido", -1),
        ):
            for node in tree.iterfind(f".//{{{IMPLOCAL_NS}}}{tag}"):
                lines.append(
                    {
                        "name": node.get(attr),
                        "account_id": account.id,
                        "quantity": 1,
                        "price_unit": sign * float(node.get("Importe") or 0),
                        "tax_ids": [Command.clear()],
                    }
                )
        return lines

    def _l10n_mx_sat_find_product(self, concept):
        self.ensure_one()
        name = re.sub(r"^\[.*\] ", "", concept.get("Descripcion") or "")
        return self.env["product.product"]._retrieve_product(
            name=name,
            default_code=concept.get("NoIdentificacion"),
            company=self.company_id,
        )

    def _l10n_mx_sat_get_line_account(self, product, account):
        self.ensure_one()
        if product:
            accounts = product.product_tmpl_id.with_company(
                self.company_id
            ).get_product_accounts(fiscal_pos=self.fiscal_position_id)
            product_account = accounts[
                "income" if self.is_sale_document() else "expense"
            ]
            if product_account:
                return product_account
        return account

    # ------------------------------------------------------------------
    # Taxes
    # ------------------------------------------------------------------

    @api.model
    def _l10n_mx_sat_parse_tax_node(self, node, withholding=False):
        """Values of a Traslado/Retencion node. Rates are in percent for
        ``Tasa`` and in currency per unit for ``Cuota``; withholdings are
        negative."""
        factor = node.get("TipoFactor") or "Tasa"
        rate = float(node.get("TasaOCuota") or 0)
        if factor == "Tasa":
            rate *= 100
        sign = -1 if withholding else 1
        # CFDI taxes are coded (002), the ECC 1.2 complement names them (IVA)
        code = node.get("Impuesto") or ""
        return {
            "type": CFDI_CODE_TO_TAX_TYPE.get(code, code.lower() or None),
            "factor": factor,
            "rate": sign * rate,
            "base": float(node.get("Base") or 0),
            "amount": sign * float(node.get("Importe") or 0),
        }

    def _l10n_mx_sat_find_taxes(self, tax_vals_list):
        taxes = self.env["account.tax"]
        for vals in tax_vals_list:
            taxes |= self._l10n_mx_sat_find_tax(vals)
        return taxes

    def _l10n_mx_sat_find_tax(self, vals):
        """Odoo tax matching a CFDI tax: same use, SAT type, factor and rate.
        The default tax of the company wins when several match."""
        self.ensure_one()
        company = self.company_id
        Tax = self.env["account.tax"].with_company(company)
        sale = self.is_sale_document()
        domain = [
            *Tax._check_company_domain(company),
            ("type_tax_use", "=", "sale" if sale else "purchase"),
            ("l10n_mx_factor_type", "=", vals["factor"]),
        ]
        if vals["factor"] != "Exento":
            domain += [
                ("l10n_mx_tax_type", "=", vals["type"]),
                (
                    "amount_type",
                    "=",
                    "percent" if vals["factor"] == "Tasa" else "fixed",
                ),
            ]
        taxes = Tax.search(domain, order="sequence, id").filtered(
            lambda tax: not float_compare(tax.amount, vals["rate"], precision_digits=2)
        )
        if not taxes:
            raise UserError(
                self.env._(
                    "No %(use)s tax found for %(type)s %(factor)s %(rate)s. "
                    "Configure it with the SAT tax type, factor type and rate "
                    "of the CFDI.",
                    use=self.env._("sale") if sale else self.env._("purchase"),
                    type=(vals["type"] or "").upper(),
                    factor=vals["factor"],
                    rate=vals["rate"],
                )
            )
        default = (
            company.account_sale_tax_id if sale else company.account_purchase_tax_id
        )
        return default if default in taxes else taxes[:1]
