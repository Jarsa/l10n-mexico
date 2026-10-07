# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class L10nMxSatPurchaseInvoiceWizard(models.TransientModel):
    _name = "l10n_mx_sat.purchase.invoice.wizard"
    _inherit = "l10n_mx_sat.document.selector.mixin"
    _description = "Create the vendor bill of purchase orders from a SAT CFDI"

    purchase_order_ids = fields.Many2many(
        comodel_name="purchase.order",
        string="Purchase Orders",
        required=True,
    )
    partner_id = fields.Many2one(compute="_compute_from_orders")
    company_id = fields.Many2one(compute="_compute_from_orders")
    currency_id = fields.Many2one(compute="_compute_from_orders")
    amount_total = fields.Monetary(
        string="Orders Total", compute="_compute_from_orders"
    )
    l10n_mx_sat_document_id = fields.Many2one(required=True)
    total_mismatch = fields.Boolean(compute="_compute_total_mismatch")

    @api.depends("purchase_order_ids")
    def _compute_from_orders(self):
        for wizard in self:
            orders = wizard.purchase_order_ids
            wizard.partner_id = orders[:1].partner_id
            wizard.company_id = orders[:1].company_id
            wizard.currency_id = orders[:1].currency_id
            wizard.amount_total = sum(orders.mapped("amount_total"))

    @api.constrains("purchase_order_ids")
    def _check_purchase_order_ids(self):
        for wizard in self:
            orders = wizard.purchase_order_ids
            if (
                len(orders.partner_id.commercial_partner_id) > 1
                or len(orders.company_id) > 1
            ):
                raise ValidationError(
                    self.env._(
                        "The purchase orders must belong to the same vendor and company"
                    )
                )
            if len(orders.currency_id) > 1:
                raise ValidationError(
                    self.env._("The purchase orders must use the same currency.")
                )

    @api.depends("l10n_mx_sat_document_id", "amount_total")
    def _compute_total_mismatch(self):
        for wizard in self:
            document = wizard.l10n_mx_sat_document_id
            wizard.total_mismatch = bool(
                document
                and wizard.currency_id.compare_amounts(
                    document.total, wizard.amount_total
                )
            )

    def action_create_invoice(self):
        self.ensure_one()
        rejection = self._l10n_mx_sat_check_document()
        if rejection:
            return self._l10n_mx_sat_rejection_action(rejection)
        orders = self.purchase_order_ids
        if orders.filtered(lambda o: o.state != "purchase"):
            raise UserError(self.env._("Only confirmed purchase orders can be billed."))
        document = self.l10n_mx_sat_document_id
        attachment = self.env["ir.attachment"].create(
            document._prepare_vendor_bill_attachment_vals()
        )
        invoices_before = orders.invoice_ids
        action = orders.action_create_invoice(attachment_ids=attachment.ids)
        move = orders.invoice_ids - invoices_before
        document._link_vendor_bill(move)
        return action
