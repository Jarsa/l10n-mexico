# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import clean_context


class L10nMxSatInvoiceWizard(models.TransientModel):
    _name = "l10n_mx_sat.invoice.wizard"
    _description = "Create invoices from SAT CFDIs"

    document_ids = fields.Many2many(
        comodel_name="l10n_mx_sat.document",
        string="SAT CFDIs",
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company", compute="_compute_from_documents"
    )
    direction = fields.Selection(
        selection=[("issued", "Issued"), ("received", "Received")],
        compute="_compute_from_documents",
    )
    journal_type = fields.Selection(
        selection=[("sale", "Sale"), ("purchase", "Purchase")],
        compute="_compute_from_documents",
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Journal",
        required=True,
        compute="_compute_journal_id",
        precompute=True,
        store=True,
        readonly=False,
        check_company=True,
        domain="[('type', '=', journal_type)]",
    )
    account_id = fields.Many2one(
        comodel_name="account.account",
        string="Account",
        required=True,
        compute="_compute_account_id",
        precompute=True,
        store=True,
        readonly=False,
        check_company=True,
        domain="[('account_type', 'not in', "
        "('asset_receivable', 'liability_payable', 'off_balance'))]",
        help="Account of the lines whose product has no income/expense account "
        "and of the local taxes.",
    )

    @api.constrains("document_ids")
    def _check_document_ids(self):
        for wizard in self:
            documents = wizard.document_ids
            if len(documents.company_id) > 1:
                raise ValidationError(
                    self.env._("The CFDIs must belong to the same company.")
                )
            if len(set(documents.mapped("direction"))) > 1:
                raise ValidationError(
                    self.env._(
                        "Select only issued CFDIs (customer invoices) or only "
                        "received CFDIs (vendor bills)."
                    )
                )

    @api.depends("document_ids")
    def _compute_from_documents(self):
        for wizard in self:
            documents = wizard.document_ids[:1]
            wizard.company_id = documents.company_id
            wizard.direction = documents.direction
            wizard.journal_type = (
                "sale" if documents.direction == "issued" else "purchase"
            )

    @api.depends("company_id", "journal_type")
    def _compute_journal_id(self):
        for wizard in self:
            wizard.journal_id = self.env["account.journal"].search(
                [
                    *self.env["account.journal"]._check_company_domain(
                        wizard.company_id
                    ),
                    ("type", "=", wizard.journal_type),
                ],
                limit=1,
            )

    @api.depends("journal_id")
    def _compute_account_id(self):
        for wizard in self:
            wizard.account_id = wizard.journal_id.default_account_id

    def action_create_invoices(self):
        self.ensure_one()
        rejections = list(
            filter(
                None,
                self.document_ids.mapped(lambda d: d._l10n_mx_sat_invoice_rejection()),
            )
        )
        if rejections:
            raise UserError("\n".join(rejections))
        # default_document_ids (the wizard context) must not reach the
        # attachments created on the invoice: other modules add one2many
        # fields with that name (e.g. ir.attachment.document_ids of Documents,
        # which then looks for documents.document records with the ids of the
        # SAT documents). The cleaned context must replace the current one:
        # passed as kwargs it is merged into it and the key survives.
        context = clean_context(self.env.context)
        Move = self.env["account.move"].with_context(context)  # pylint: disable=context-overridden
        moves = Move
        for document in self.document_ids:
            moves |= Move._l10n_mx_sat_create_invoice(
                document, self.journal_id, self.account_id
            )
        action = self.env["ir.actions.actions"]._for_xml_id(
            "account.action_move_out_invoice_type"
            if self.direction == "issued"
            else "account.action_move_in_invoice_type"
        )
        action["domain"] = [("id", "in", moves.ids)]
        if len(moves) == 1:
            # Not "views": False: the web client would rebuild it with the
            # view_id of the action, which is the list view.
            action.update({"res_id": moves.id, "views": [(False, "form")]})
        return action
