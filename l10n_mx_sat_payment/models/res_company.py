# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_mx_sat_payment_mode = fields.Selection(
        selection=[
            ("none", "Do nothing"),
            ("link", "Link existing payments"),
            ("create", "Link existing payments or create them"),
        ],
        string="Payment complements",
        default="none",
        required=True,
        help="What to do with the CFDI payment complements downloaded from the "
        "SAT: link them to a payment already registered on the related "
        "invoices, or also create the payment when none exists.",
    )
    l10n_mx_sat_payment_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Fallback bank journal",
        domain="[('type', '=', 'bank'), ('company_id', '=', id)]",
        help="Journal of the payments whose bank account in the complement does "
        "not match any bank account of the company.",
    )
    l10n_mx_sat_payment_auto = fields.Boolean(
        string="Apply payment complements on download",
        help="Apply each payment complement as soon as it is downloaded from the "
        "SAT. Complements that cannot be applied stay pending.",
    )
