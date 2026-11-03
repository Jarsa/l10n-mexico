# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, models

# RFC published by the SAT for sales to the general public and for foreign
# partners. They are shared by many partners by design.
GENERIC_RFCS = ("XAXX010101000", "XEXX010101000")


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.constrains("vat", "parent_id")
    def _check_vat_unique(self):
        partners = self.filtered(lambda partner: partner.vat not in GENERIC_RFCS)
        return super(ResPartner, partners)._check_vat_unique()
