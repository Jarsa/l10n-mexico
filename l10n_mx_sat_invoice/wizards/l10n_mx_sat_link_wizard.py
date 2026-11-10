# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import clean_context


class L10nMxSatLinkWizard(models.TransientModel):
    _name = "l10n_mx_sat.link.wizard"
    _description = "Link an invoice to a SAT CFDI"

    move_id = fields.Many2one(
        comodel_name="account.move", string="Invoice", required=True, readonly=True
    )
    currency_id = fields.Many2one(related="move_id.currency_id")
    amount_total = fields.Monetary(related="move_id.amount_total")
    only_partner = fields.Boolean(
        string="Only CFDIs of the partner",
        default=True,
        help="Show only the CFDIs with the RFC of the partner of the invoice.",
    )
    document_domain = fields.Binary(compute="_compute_document_domain")
    document_id = fields.Many2one(
        comodel_name="l10n_mx_sat.document",
        string="SAT CFDI",
        compute="_compute_document_id",
        store=True,
        readonly=False,
    )
    document_partner = fields.Char(
        string="CFDI partner", compute="_compute_document_partner"
    )
    document_date = fields.Datetime(related="document_id.issue_date")
    document_total = fields.Float(related="document_id.total")
    document_currency = fields.Char(related="document_id.currency_code")

    def _get_document_domain(self):
        self.ensure_one()
        move = self.move_id
        issued = move.is_sale_document()
        domain = [
            ("company_id", "=", move.company_id.id),
            ("document_kind", "=", "cfdi"),
            ("has_xml", "=", True),
            ("direction", "=", "issued" if issued else "received"),
            (
                "voucher_type",
                "=",
                "E" if move.move_type in ("out_refund", "in_refund") else "I",
            ),
            ("sat_status", "!=", "cancelled"),
            ("vendor_bill_id", "=", False),
            ("customer_invoice_id", "=", False),
        ]
        vat = move.commercial_partner_id.vat
        if self.only_partner and vat:
            domain.append(("receiver_rfc" if issued else "issuer_rfc", "=ilike", vat))
        return domain

    @api.depends("move_id", "only_partner")
    def _compute_document_domain(self):
        for wizard in self:
            wizard.document_domain = wizard._get_document_domain()

    @api.depends("move_id", "only_partner")
    def _compute_document_id(self):
        for wizard in self:
            wizard.document_id = wizard.move_id._l10n_mx_sat_link_candidate(
                wizard._get_document_domain()
            )

    @api.depends("document_id")
    def _compute_document_partner(self):
        for wizard in self:
            document = wizard.document_id
            wizard.document_partner = (
                document.receiver_name
                if document.direction == "issued"
                else document.issuer_name
            )

    def action_link(self):
        self.ensure_one()
        if not self.document_id:
            raise UserError(self.env._("Choose the CFDI to link."))
        # default_move_id (the wizard context) must not reach the records
        # created while linking (attachment, message, EDI document).
        context = clean_context(self.env.context)
        move = self.move_id.with_context(context)  # pylint: disable=context-overridden
        move._l10n_mx_sat_link_document(self.document_id)
        return {"type": "ir.actions.act_window_close"}
