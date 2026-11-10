# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class L10nMxSatDocument(models.Model):
    _inherit = "l10n_mx_sat.document"

    # Same definition as in l10n_mx_sat_vendor_bill and l10n_mx_sat_purchase
    # so the three modules share the column.
    vendor_bill_id = fields.Many2one(
        comodel_name="account.move",
        string="Vendor bill",
        readonly=True,
        copy=False,
    )
    customer_invoice_id = fields.Many2one(
        comodel_name="account.move",
        string="Customer invoice",
        readonly=True,
        copy=False,
    )
    invoice_id = fields.Many2one(
        comodel_name="account.move",
        string="Invoice",
        compute="_compute_invoice_id",
    )

    @api.depends("direction", "vendor_bill_id", "customer_invoice_id")
    def _compute_invoice_id(self):
        for document in self:
            document.invoice_id = (
                document.customer_invoice_id
                if document.direction == "issued"
                else document.vendor_bill_id
            )

    def _l10n_mx_sat_invoice_rejection(self, move=None):
        """Reason why no invoice can be created from the document, or False.

        :param move: existing invoice the document is going to be linked to,
            instead of creating one
        """
        self.ensure_one()
        if move:
            if not move.is_invoice() or move.state == "cancel":
                return self.env._(
                    "%(move)s is not an invoice that can be linked to a CFDI.",
                    move=move.display_name,
                )
            if move.l10n_mx_sat_document_id:
                return self.env._(
                    "%(move)s is already linked to the CFDI %(uuid)s.",
                    move=move.display_name,
                    uuid=move.l10n_mx_sat_document_id.uuid,
                )
            if (
                move.company_id != self.company_id
                or move.is_sale_document() != (self.direction == "issued")
                or (move.move_type in ("out_refund", "in_refund"))
                != (self.voucher_type == "E")
            ):
                return self.env._(
                    "The CFDI %(uuid)s does not correspond to %(move)s: the "
                    "company, the direction (issued or received) and the type "
                    "(invoice or credit note) must match.",
                    uuid=self.uuid,
                    move=move.display_name,
                )
        if self.document_kind != "cfdi" or not self.has_xml:
            return self.env._("%(uuid)s is not a CFDI with XML.", uuid=self.uuid)
        if self.voucher_type not in ("I", "E"):
            return self.env._(
                "%(uuid)s is a CFDI of type %(type)s: only invoices (I) and "
                "credit notes (E) can be imported.",
                uuid=self.uuid,
                type=self.voucher_type,
            )
        if self.sat_status == "cancelled":
            return self.env._("%(uuid)s is cancelled in the SAT.", uuid=self.uuid)
        if self.invoice_id:
            return self.env._(
                "%(uuid)s is already linked to %(invoice)s.",
                uuid=self.uuid,
                invoice=self.invoice_id.display_name,
            )
        return False

    def _link_invoice(self, move):
        self.ensure_one()
        field = (
            "customer_invoice_id" if self.direction == "issued" else "vendor_bill_id"
        )
        self._sat_write({field: move.id})

    def action_create_invoice(self):
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Create invoice"),
            "res_model": "l10n_mx_sat.invoice.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_document_ids": self.ids},
        }

    def action_open_invoice(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.invoice_id.id,
            "view_mode": "form",
        }
