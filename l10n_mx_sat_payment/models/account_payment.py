# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    l10n_mx_sat_document_id = fields.Many2one(
        comodel_name="l10n_mx_sat.document",
        string="SAT payment complement",
        readonly=True,
        copy=False,
        index="btree_not_null",
    )
