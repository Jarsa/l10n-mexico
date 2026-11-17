# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResCountry(models.Model):
    _inherit = "res.country"

    l10n_mx_edi_code = fields.Char(
        string="Code MX",
    )

    def write(self, vals):
        """Keep the Mexican address form of this module.

        l10n_mx_edi_extended (Enterprise) also assigns Mexico an address form of
        its own, which has no zip completion. That module sits deeper in the
        module graph, so it always loads after this one and its data would
        replace our form. Only its data is swapped: a form chosen by hand stays.
        """
        if (
            vals.get("address_view_id")
            and self.env.context.get("install_module") == "l10n_mx_edi_extended"
        ):
            toponym_view = self.env.ref("l10n_mx_toponym.mx_partner_address_form")
            vals = dict(vals, address_view_id=toponym_view.id)
        return super().write(vals)
