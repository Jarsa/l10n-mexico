# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestResPartnerVatUnique(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "partner_vat_unique.partner_vat_unique", True
        )
        cls.partner_model = cls.env["res.partner"]

    def test_real_vat_must_be_unique(self):
        self.partner_model.create({"name": "Primero", "vat": "AAA010101AAA"})
        with self.assertRaises(ValidationError):
            self.partner_model.create({"name": "Segundo", "vat": "AAA010101AAA"})

    def test_generic_rfc_can_be_repeated(self):
        for vat in ("XAXX010101000", "XEXX010101000"):
            first = self.partner_model.create({"name": f"Uno {vat}", "vat": vat})
            second = self.partner_model.create({"name": f"Dos {vat}", "vat": vat})
            self.assertTrue(first.same_vat_partner_id)
            self.assertEqual(second.vat, vat)
            second.write({"vat": vat, "name": "Dos editado"})

    def test_batch_create_checks_only_real_vats(self):
        self.partner_model.create({"name": "Generico", "vat": "XAXX010101000"})
        self.partner_model.create({"name": "Real", "vat": "BBB010101BBB"})
        self.partner_model.create({"name": "Otro generico", "vat": "XAXX010101000"})
        with self.assertRaises(ValidationError):
            self.partner_model.create(
                [
                    {"name": "Otro generico 2", "vat": "XAXX010101000"},
                    {"name": "Otro real", "vat": "BBB010101BBB"},
                ]
            )
