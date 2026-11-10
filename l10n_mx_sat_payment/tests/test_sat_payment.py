# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.l10n_mx_sat_invoice.tests.test_invoice_wizard import (
    TestInvoiceWizard,
)

PAY_CONCEPT = """
<cfdi:Concepto ClaveProdServ="84111506" Cantidad="1" ClaveUnidad="ACT"
    Descripcion="Pago" ValorUnitario="0" Importe="0" ObjetoImp="01"/>"""
PAGOS = """
<pago20:Pagos xmlns:pago20="http://www.sat.gob.mx/Pagos20" Version="2.0">
    <pago20:Totales MontoTotalPagos="{amount}"/>
    <pago20:Pago FechaPago="2026-02-15T12:00:00" FormaDePagoP="03" MonedaP="MXN"
        TipoCambioP="1" Monto="{amount}" NumOperacion="OP-77"
        RfcEmisorCtaOrd="BBA830831LJ2" NomBancoOrdExt="BBVA"
        CtaOrdenante="{ordering}" RfcEmisorCtaBen="BMI9704113PA"
        CtaBeneficiario="{beneficiary}">
        {related}
    </pago20:Pago>
</pago20:Pagos>"""
RELATED = """
<pago20:DoctoRelacionado IdDocumento="{uuid}" Serie="A" Folio="{folio}"
    MonedaDR="MXN" EquivalenciaDR="1" NumParcialidad="1" ImpSaldoAnt="{total}"
    ImpPagado="{paid}" ImpSaldoInsoluto="{rest}" ObjetoImpDR="02"/>"""
COMPANY_CLABE = "012180001234567890"
OTHER_CLABE = "014180009876543210"


@tagged("post_install", "-at_install")
class TestSatPayment(TestInvoiceWizard):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_account = cls.env["res.partner.bank"].create(
            {"acc_number": COMPANY_CLABE, "partner_id": cls.company.partner_id.id}
        )
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.bank_journal.bank_account_id = cls.bank_account
        cls.fallback_journal = cls.env["account.journal"].create(
            {"name": "Other bank", "type": "bank", "code": "OBNK"}
        )
        cls.company.write(
            {
                "l10n_mx_sat_payment_mode": "create",
                "l10n_mx_sat_payment_journal_id": False,
                "l10n_mx_sat_payment_auto": False,
            }
        )

    def _posted_invoice(self, direction="issued"):
        document = self._create_document(direction=direction)
        move = self.env["account.move"].browse(
            self._create_invoices(document)[1]["res_id"]
        )
        move.action_post()
        return document, move

    def _create_complement(
        self, invoices, amount=None, direction="issued", beneficiary=COMPANY_CLABE
    ):
        """Payment complement paying ``invoices`` ({document: paid amount})."""
        amount = amount or sum(invoices.values())
        related = "".join(
            RELATED.format(
                uuid=document.uuid,
                folio=document.folio_number,
                total=f"{document.total:.2f}",
                paid=f"{paid:.2f}",
                rest=f"{document.total - paid:.2f}",
            )
            for document, paid in invoices.items()
        )
        ordering, beneficiary = (
            (OTHER_CLABE, beneficiary)
            if direction == "issued"
            else (beneficiary, OTHER_CLABE)
        )
        return self._create_document(
            direction=direction,
            voucher_type="P",
            concepts=PAY_CONCEPT,
            subtotal="0",
            total="0",
            moneda="XXX",
            complement=PAGOS.format(
                amount=f"{amount:.2f}",
                ordering=ordering,
                beneficiary=beneficiary,
                related=related,
            ),
        )

    def _register_payment(self, invoice, payment_date):
        Register = self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=invoice.ids
        )
        vals = {"payment_date": payment_date, "journal_id": self.bank_journal.id}
        # Required by l10n_mx_cfdi_account when it is installed
        form_field = Register._fields.get("payment_form_id")
        if form_field:
            vals["payment_form_id"] = (
                self.env[form_field.comodel_name].search([], limit=1).id
            )
        return Register.create(vals)._create_payments()

    def test_parse_complement(self):
        document, move = self._posted_invoice()
        complement = self._create_complement({document: 1160})
        self.assertEqual(complement.sat_payment_state, "pending")
        payment = complement.sat_payment_ids
        self.assertRecordValues(
            payment,
            [
                {
                    "date": date(2026, 2, 15),
                    "payment_form": "03",
                    "currency_code": "MXN",
                    "amount": 1160,
                    "operation_number": "OP-77",
                    "ordering_account": OTHER_CLABE,
                    "beneficiary_account": COMPANY_CLABE,
                    "state": "pending",
                }
            ],
        )
        self.assertRecordValues(
            payment.line_ids,
            [
                {
                    "uuid": document.uuid,
                    "installment": 1,
                    "amount_paid": 1160,
                    "remaining_balance": 0,
                    "invoice_id": move.id,
                }
            ],
        )

    def test_mode_none(self):
        self.company.l10n_mx_sat_payment_mode = "none"
        document, _move = self._posted_invoice()
        complement = self._create_complement({document: 1160})
        with self.assertRaisesRegex(UserError, "not applied"):
            complement.with_user(self.user).action_apply_payments()

    def test_create_payment_with_bank_account(self):
        document, move = self._posted_invoice()
        complement = self._create_complement({document: 1160})
        complement.with_user(self.user).action_apply_payments()
        payment = complement.sat_payment_ids.payment_id
        self.assertRecordValues(
            payment,
            [
                {
                    "journal_id": self.bank_journal.id,
                    "payment_type": "inbound",
                    "amount": 1160,
                    "partner_id": move.partner_id.id,
                    "l10n_mx_sat_document_id": complement.id,
                }
            ],
        )
        self.assertIn(payment.state, ("in_process", "paid"))
        self.assertEqual(payment.date.isoformat(), "2026-02-15")
        self.assertIn(complement.uuid, payment.memo)
        self.assertIn(move.payment_state, ("in_payment", "paid"))
        self.assertEqual(complement.sat_payment_state, "done")

    def test_partial_payment(self):
        document, move = self._posted_invoice()
        complement = self._create_complement({document: 500})
        complement.action_apply_payments()
        self.assertEqual(complement.sat_payment_ids.payment_id.amount, 500)
        self.assertEqual(move.amount_residual, 660)
        self.assertEqual(move.payment_state, "partial")

    def test_several_invoices_one_payment(self):
        document_1, move_1 = self._posted_invoice()
        document_2, move_2 = self._posted_invoice()
        complement = self._create_complement({document_1: 1160, document_2: 1160})
        complement.action_apply_payments()
        payment = complement.sat_payment_ids.payment_id
        self.assertEqual(payment.amount, 2320)
        self.assertEqual((move_1 + move_2).mapped("amount_residual"), [0, 0])

    def test_no_journal(self):
        document, _move = self._posted_invoice()
        complement = self._create_complement({document: 1160}, beneficiary=OTHER_CLABE)
        with self.assertRaisesRegex(UserError, "No bank journal"):
            complement.action_apply_payments()
        self.company.l10n_mx_sat_payment_journal_id = self.fallback_journal
        complement.action_apply_payments()
        self.assertEqual(
            complement.sat_payment_ids.payment_id.journal_id, self.fallback_journal
        )

    def test_received_complement_outbound(self):
        document, move = self._posted_invoice(direction="received")
        complement = self._create_complement({document: 1160}, direction="received")
        complement.action_apply_payments()
        payment = complement.sat_payment_ids.payment_id
        self.assertEqual(payment.payment_type, "outbound")
        self.assertEqual(payment.journal_id, self.bank_journal)
        self.assertIn(move.payment_state, ("in_payment", "paid"))

    def test_link_existing_payment(self):
        self.company.l10n_mx_sat_payment_mode = "link"
        document, move = self._posted_invoice()
        existing = self._register_payment(move, "2026-02-16")
        complement = self._create_complement({document: 1160})
        complement.action_apply_payments()
        self.assertEqual(complement.sat_payment_ids.payment_id, existing)
        self.assertEqual(existing.l10n_mx_sat_document_id, complement)
        # A second complement cannot take the same payment
        other = self._create_complement({document: 1160})
        with self.assertRaisesRegex(UserError, "No registered payment"):
            other.action_apply_payments()

    def test_link_prefers_reconciled_payment(self):
        self.company.l10n_mx_sat_payment_mode = "link"
        document, move = self._posted_invoice()
        _other_document, other_move = self._posted_invoice()
        payments = {
            invoice: self._register_payment(invoice, "2026-02-15")
            for invoice in (other_move, move)
        }
        complement = self._create_complement({document: 1160})
        complement.action_apply_payments()
        self.assertEqual(complement.sat_payment_ids.payment_id, payments[move])

    def test_invoice_not_registered(self):
        document = self._create_document(direction="issued")  # no invoice created
        complement = self._create_complement({document: 1160})
        self.assertFalse(complement.sat_payment_ids.line_ids.invoice_id)
        with self.assertRaisesRegex(UserError, "not registered"):
            complement.action_apply_payments()
        # Draft invoices are rejected too
        move = self.env["account.move"].browse(
            self._create_invoices(document)[1]["res_id"]
        )
        with self.assertRaisesRegex(UserError, "not posted"):
            complement.action_apply_payments()
        move.action_post()
        complement.action_apply_payments()
        self.assertEqual(complement.sat_payment_state, "done")

    def test_auto_apply_on_download(self):
        self.company.l10n_mx_sat_payment_auto = True
        document, _move = self._posted_invoice()
        complement = self._create_complement({document: 1160})
        self.assertEqual(complement.sat_payment_state, "done")
        # A complement that cannot be applied does not break the download
        orphan = self._create_document(direction="issued")
        complement = self._create_complement({orphan: 1160})
        self.assertEqual(complement.sat_payment_state, "pending")

    def test_cancelled_complement(self):
        document, _move = self._posted_invoice()
        complement = self._create_complement({document: 1160})
        complement._sat_write({"sat_status": "cancelled"})
        with self.assertRaisesRegex(UserError, "cancelled"):
            complement.action_apply_payments()

    def test_list_action_collects_errors(self):
        document, _move = self._posted_invoice()
        good = self._create_complement({document: 1160})
        orphan = self._create_document(direction="issued")
        bad = self._create_complement({orphan: 1160})
        with self.assertRaisesRegex(UserError, bad.uuid):
            (good + bad).action_apply_payments()
