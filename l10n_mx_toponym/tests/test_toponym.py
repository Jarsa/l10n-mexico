# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from os.path import dirname, join
from unittest.mock import patch

import requests

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

SAMPLE = join(dirname(__file__), "sepomex_sample.txt")


@tagged("post_install", "-at_install")
class TestToponym(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mx_country = cls.env.ref("base.mx")
        cls.Zip = cls.env["res.city.zip"]
        with open(SAMPLE, encoding="latin-1") as sample:
            cls.sample_text = sample.read()

    def setUp(self):
        super().setUp()
        # start from a database without the sample entries (an installed
        # catalog may already have them)
        self.Zip.search(
            [("name", "in", ["01000", "01010", "01020", "20000", "20010"])]
        ).unlink()

    def _load_sample(self):
        with patch.object(
            type(self.Zip), "_sepomex_download", return_value=self.sample_text
        ):
            return self.Zip._sepomex_refresh()

    def test_catalog_loaded(self):
        """The post_init_hook loads cities and localities; the zip catalog is
        downloaded from Correos de México (here: the shipped sample)."""
        cities = self.env["res.city"].search_count(
            [("country_id", "=", self.mx_country.id)]
        )
        self.assertTrue(cities, "No Mexican cities were loaded")
        localities = self.env["l10n_mx_edi.res.locality"].search_count([])
        self.assertTrue(localities, "No localities were loaded")
        self._load_sample()
        zips = self.Zip.search_count([("city_id.country_id", "=", self.mx_country.id)])
        self.assertTrue(zips, "No Mexican zip entries were loaded")

    def test_sepomex_load_is_additive_and_idempotent(self):
        """Only missing (city, zip, colony code) entries are created; the
        locality is taken from an entry of the same zip; a second run adds 0."""
        before = self.Zip.search_count([])
        created, skipped = self._load_sample()
        self.assertGreater(created, 0)
        self.assertEqual(self.Zip.search_count([]), before + created)
        entry = self.Zip.search(
            [("name", "=", "01000"), ("l10n_mx_edi_colony", "=", "San Ángel")]
        )
        self.assertEqual(len(entry), 1)
        state_code = entry.city_id.state_id.code
        self.assertIn(state_code, ("CMX", "DF"))
        self.assertEqual(entry.l10n_mx_edi_colony_code, "0001")
        xml_id = entry.get_external_id()[entry.id]
        self.assertEqual(
            xml_id,
            f"l10n_mx_toponym.res_city_zip_mx_{state_code.lower()}_010_0001_01000",
        )
        known = self.Zip.search([("name", "=", "20010")], order="id")
        self.assertGreater(len(known), 1, "several colonies in 20010")
        first, others = known[:1], known[1:]
        locality = self.env["l10n_mx_edi.res.locality"].search(
            [("state_id", "=", first.city_id.state_id.id)], limit=1
        )
        first.l10n_mx_edi_locality_id = locality
        count_others = len(others)
        others.unlink()
        created_again, _skipped = self._load_sample()
        self.assertEqual(created_again, count_others)
        reloaded = self.Zip.search([("name", "=", "20010")]) - first
        self.assertEqual(len(reloaded), count_others)
        self.assertTrue(
            all(
                zip_entry.l10n_mx_edi_locality_id == locality for zip_entry in reloaded
            ),
            "the new colonies of a known zip take its locality",
        )
        self.assertEqual(self._load_sample()[0], 0)
        self.assertTrue(
            self.env["ir.config_parameter"].get_param(
                "l10n_mx_toponym.sepomex_last_update"
            )
        )

    def test_sepomex_unknown_municipality_is_skipped(self):
        rows = list(self.Zip._sepomex_rows(self.sample_text))
        rows[0]["c_mnpio"] = "999"
        rows[0]["d_codigo"] = "99999"
        created, skipped = self.Zip._sepomex_load(rows[:1])
        self.assertEqual((created, skipped), (0, 1))

    def test_sepomex_download_failure(self):
        """The cron never breaks on a download error; the button reports it."""
        with patch.object(
            type(self.Zip),
            "_sepomex_download",
            side_effect=requests.ConnectionError("offline"),
        ):
            self.assertIsNone(self.Zip._cron_sepomex_refresh())
            with self.assertRaisesRegex(UserError, "could not be downloaded"):
                self.Zip.action_sepomex_refresh()

    def test_zip_display_name_and_search_by_colony(self):
        """The colony shows in the name of the zip and can be searched."""
        self._load_sample()
        entry = self.Zip.search(
            [("name", "=", "01000"), ("l10n_mx_edi_colony", "=", "San Ángel")]
        )
        self.assertEqual(
            entry.display_name,
            ", ".join(
                [
                    "01000",
                    "San Ángel",
                    entry.city_id.name,
                    entry.city_id.state_id.name,
                    self.mx_country.name,
                ]
            ),
        )
        found = self.Zip.name_search("San Ángel", limit=50)
        self.assertIn(entry.id, [rec_id for rec_id, _name in found])

    def test_partner_colony_from_zip(self):
        """Partner colony/locality fields are computed from the selected zip."""
        self._load_sample()
        zip_entry = self.Zip.search(
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
