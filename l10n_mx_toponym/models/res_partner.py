# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    l10n_mx_edi_locality_id = fields.Many2one(
        comodel_name="l10n_mx_edi.res.locality",
        string="Locality",
        compute="_compute_l10n_mx_edi_locality_id",
        store=True,
        readonly=False,
    )
    l10n_mx_edi_colony = fields.Char(
        string="Colony",
        compute="_compute_l10n_mx_edi_colony",
        store=True,
        readonly=False,
    )
    l10n_mx_edi_colony_code = fields.Char(
        string="Colony Code",
        compute="_compute_l10n_mx_edi_colony_code",
        store=True,
        readonly=False,
    )

    @api.depends("zip_id")
    def _compute_l10n_mx_edi_locality_id(self):
        if hasattr(super(), "_compute_l10n_mx_edi_locality_id"):
            return super()._compute_l10n_mx_edi_locality_id()  # pragma: no cover
        for record in self:
            if record.zip_id:
                record.l10n_mx_edi_locality_id = record.zip_id.l10n_mx_edi_locality_id
            elif not record.country_enforce_cities:
                record.l10n_mx_edi_locality_id = False

    @api.depends("zip_id")
    def _compute_l10n_mx_edi_colony(self):
        if hasattr(super(), "_compute_l10n_mx_edi_colony"):
            return super()._compute_l10n_mx_edi_colony()  # pragma: no cover
        for record in self:
            if record.zip_id:
                record.l10n_mx_edi_colony = record.zip_id.l10n_mx_edi_colony
            elif not record.country_enforce_cities:
                record.l10n_mx_edi_colony = False

    @api.depends("zip_id")
    def _compute_l10n_mx_edi_colony_code(self):
        if hasattr(super(), "_compute_l10n_mx_edi_colony_code"):
            return super()._compute_l10n_mx_edi_colony_code()  # pragma: no cover
        for record in self:
            if record.zip_id:
                record.l10n_mx_edi_colony_code = record.zip_id.l10n_mx_edi_colony_code
            elif not record.country_enforce_cities:
                record.l10n_mx_edi_colony_code = False

    def _l10n_mx_toponym_get_address_errors(self):
        """Check a Mexican address against the ZIP catalog.

        The SAT rejects a CFDI complement (e.g. Carta Porte) when the colony
        code, the municipality or the state of an address do not belong to
        its ZIP code. Modules that stamp addresses call this method to stop
        the user before reaching the PAC.

        :return: list of translated messages, empty when the address is
            consistent with the catalog, is not a Mexican address or the
            catalog is empty
        """
        self.ensure_one()
        if self.country_id.code != "MX":
            return []
        Zip = self.env["res.city.zip"]
        country_domain = [("city_id.country_id", "=", self.country_id.id)]
        if not Zip.search_count(country_domain, limit=1):
            # the catalog has not been downloaded yet: nothing to compare with
            return []
        if not self.zip:
            return [self.env._("The ZIP code is missing.")]
        errors = []
        zips = Zip.search([("name", "=", self.zip), *country_domain])
        if not zips:
            errors.append(
                self.env._(
                    "The ZIP code %(zip)s does not exist in the ZIP catalog.",
                    zip=self.zip,
                )
            )
        else:
            cities = zips.city_id
            if self.state_id and self.state_id not in cities.state_id:
                errors.append(
                    self.env._(
                        "The state %(state)s does not match the ZIP code %(zip)s "
                        "(%(expected)s).",
                        state=self.state_id.name,
                        zip=self.zip,
                        expected=", ".join(cities.state_id.mapped("name")),
                    )
                )
            if self.city_id and self.city_id not in cities:
                errors.append(
                    self.env._(
                        "The city %(city)s does not match the ZIP code %(zip)s "
                        "(%(expected)s).",
                        city=self.city_id.name,
                        zip=self.zip,
                        expected=", ".join(cities.mapped("name")),
                    )
                )
            colony_code = self.l10n_mx_edi_colony_code
            colonies = zips.filtered("l10n_mx_edi_colony_code")
            # ZIP entries without colony code (typed by hand) cannot be compared
            if (
                colony_code
                and colonies
                and colony_code not in colonies.mapped("l10n_mx_edi_colony_code")
            ):
                errors.append(
                    self.env._(
                        "The colony code %(code)s does not belong to the ZIP code "
                        "%(zip)s. Valid colonies: %(colonies)s.",
                        code=colony_code,
                        zip=self.zip,
                        colonies=", ".join(
                            f"{colony.l10n_mx_edi_colony_code} "
                            f"{colony.l10n_mx_edi_colony}"
                            for colony in colonies.sorted("l10n_mx_edi_colony_code")
                        ),
                    )
                )
        if self.city_id and not self.city_id.l10n_mx_edi_code:
            errors.append(
                self.env._(
                    "The city %(city)s has no SAT municipality code. Select the "
                    "city of the ZIP catalog.",
                    city=self.city_id.name,
                )
            )
        return errors

    @api.model
    def _address_fields(self):
        return super()._address_fields() + [
            "l10n_mx_edi_locality_id",
            "l10n_mx_edi_colony",
            "l10n_mx_edi_colony_code",
        ]
