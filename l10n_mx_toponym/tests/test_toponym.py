# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestToponym(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mx_country = cls.env.ref("base.mx")

    def test_catalog_loaded(self):
        """The post_init_hook loads cities, localities and zip codes."""
        cities = self.env["res.city"].search_count(
            [("country_id", "=", self.mx_country.id)]
        )
        self.assertTrue(cities, "No Mexican cities were loaded")
        localities = self.env["l10n_mx_edi.res.locality"].search_count([])
        self.assertTrue(localities, "No localities were loaded")
        zips = self.env["res.city.zip"].search_count(
            [("city_id.country_id", "=", self.mx_country.id)]
        )
        self.assertTrue(zips, "No Mexican zip entries were loaded")

    def test_zip_catalog_consistency(self):
        """Loaded zip entries are linked to Mexican cities with a state."""
        zip_entry = self.env["res.city.zip"].search(
            [("city_id.country_id", "=", self.mx_country.id)], limit=1
        )
        self.assertTrue(zip_entry.city_id.state_id)
        self.assertEqual(zip_entry.city_id.country_id, self.mx_country)

    def test_partner_colony_from_zip(self):
        """Partner colony/locality fields are computed from the selected zip."""
        zip_entry = self.env["res.city.zip"].search(
            [
                ("city_id.country_id", "=", self.mx_country.id),
                ("l10n_mx_edi_colony", "!=", False),
            ],
            limit=1,
        )
        partner = self.env["res.partner"].create(
            {
                "name": "Test Toponym Partner",
                "country_id": self.mx_country.id,
                "state_id": zip_entry.city_id.state_id.id,
                "city_id": zip_entry.city_id.id,
                "zip_id": zip_entry.id,
            }
        )
        self.assertEqual(partner.l10n_mx_edi_colony, zip_entry.l10n_mx_edi_colony)
        self.assertEqual(
            partner.l10n_mx_edi_colony_code, zip_entry.l10n_mx_edi_colony_code
        )
        self.assertEqual(
            partner.l10n_mx_edi_locality_id, zip_entry.l10n_mx_edi_locality_id
        )
