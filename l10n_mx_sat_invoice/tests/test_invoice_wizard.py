# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from datetime import date
from unittest.mock import patch

from lxml import etree

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.web.controllers.utils import clean_action

# Fictitious RFCs: the SAT test RFC for the company and made-up ones for partners.
COMPANY_RFC = "EKU9003173C9"
VENDOR_RFC = "XIA190128J61"
CUSTOMER_RFC = "XOT190128J61"
TFD = (
    '<tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" '
    'Version="1.1" UUID="{uuid}" FechaTimbrado="2026-02-10T10:05:00"/>'
)
CONCEPT_IVA = """
<cfdi:Concepto ClaveProdServ="01010101" NoIdentificacion="{code}" Cantidad="2"
    ClaveUnidad="H87" Descripcion="Widget" ValorUnitario="500.00" Importe="1000.00"
    ObjetoImp="02" {extra}>
    <cfdi:Impuestos>
        <cfdi:Traslados>
            <cfdi:Traslado Base="{base}" Impuesto="002" TipoFactor="Tasa"
                TasaOCuota="0.160000" Importe="{iva}"/>
        </cfdi:Traslados>
        {withholdings}
    </cfdi:Impuestos>
</cfdi:Concepto>"""
WITHHOLDINGS = """
<cfdi:Retenciones>
    <cfdi:Retencion Base="1000.00" Impuesto="001" TipoFactor="Tasa"
        TasaOCuota="0.100000" Importe="100.00"/>
    <cfdi:Retencion Base="1000.00" Impuesto="002" TipoFactor="Tasa"
        TasaOCuota="0.106667" Importe="106.67"/>
</cfdi:Retenciones>"""


@tagged("post_install", "-at_install")
class TestInvoiceWizard(AccountTestInvoicingCommon):
    @classmethod
    @AccountTestInvoicingCommon.setup_country("mx")
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.vat = COMPANY_RFC
        cls.vendor = cls.env["res.partner"].create(
            {
                "name": "Soluciones Demo",
                "vat": VENDOR_RFC,
                "country_id": cls.env.ref("base.mx").id,
            }
        )
        cls.requests = {}
        for direction in ("received", "issued"):
            cls.requests[direction] = (
                cls.env["l10n_mx_sat.download.request"]
                .sudo()
                .create(
                    {
                        "company_id": cls.company.id,
                        "document_kind": "cfdi",
                        "direction": direction,
                        "request_type": "xml",
                        "date_from": "2026-02-01 00:00:00",
                        "date_to": "2026-02-28 23:59:59",
                        "state": "downloading",
                    }
                )
            )
        cls.user = new_test_user(
            cls.env,
            login="sat_invoice_user",
            groups="account.group_account_invoice,l10n_mx_sat.group_sat_user",
            company_id=cls.company.id,
        )
        cls.counter = 0

    @classmethod
    def _create_document(
        cls,
        direction="received",
        voucher_type="I",
        concepts=None,
        subtotal="1000.00",
        total="1160.00",
        moneda="MXN",
        complement="",
        related="",
        issuer=(VENDOR_RFC, "SOLUCIONES DEMO"),
        receiver=(CUSTOMER_RFC, "CLIENTE DEMO"),
    ):
        cls.counter += 1
        uuid = f"AAAAAAAA-0000-0000-0000-{cls.counter:012d}"
        if direction == "received":
            receiver = (COMPANY_RFC, "ESCUELA KEMPER URGATE")
        else:
            issuer = (COMPANY_RFC, "ESCUELA KEMPER URGATE")
        if concepts is None:
            concepts = CONCEPT_IVA.format(
                code="WID", base="1000.00", iva="160.00", withholdings="", extra=""
            )
        xml = f"""<?xml version="1.0" encoding="utf-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Version="4.0"
    Serie="A" Folio="{cls.counter}" Fecha="2026-02-10T10:00:00" SubTotal="{subtotal}"
    Moneda="{moneda}" Total="{total}" TipoDeComprobante="{voucher_type}"
    MetodoPago="PUE" FormaPago="03" LugarExpedicion="06600">
    {related}
    <cfdi:Emisor Rfc="{issuer[0]}" Nombre="{issuer[1]}" RegimenFiscal="601"/>
    <cfdi:Receptor Rfc="{receiver[0]}" Nombre="{receiver[1]}"
        DomicilioFiscalReceptor="06600" RegimenFiscalReceptor="603" UsoCFDI="G03"/>
    <cfdi:Conceptos>{concepts}</cfdi:Conceptos>
    <cfdi:Complemento>{TFD.format(uuid=uuid)}{complement}</cfdi:Complemento>
</cfdi:Comprobante>""".encode()
        # The SAT sync code runs as superuser; the tests run as the accountant.
        document = (
            cls.env["l10n_mx_sat.document"]
            .sudo()
            ._upsert_from_xml(
                etree.fromstring(xml), xml, cls.company, cls.requests[direction]
            )
            .sudo(False)
        )
        if document.vendor_bill_id:
            # l10n_mx_sat_vendor_bill, when installed, bills every received CFDI
            document.vendor_bill_id.unlink()
            document._sat_write({"vendor_bill_id": False})
        return document

    def _create_invoices(self, documents, user=None, **vals):
        action = documents.action_create_invoice()
        wizard = (
            self.env[action["res_model"]]
            .with_user(user or self.env.user)
            .with_context(**action["context"])
            .create(vals)
        )
        return wizard, wizard.action_create_invoices()

    def _tax(self, xmlid):
        return self.env["account.chart.template"].ref(xmlid)

    def test_received_invoice(self):
        document = self._create_document(
            concepts=CONCEPT_IVA.format(
                code="WID",
                base="1000.00",
                iva="160.00",
                withholdings=WITHHOLDINGS,
                extra="",
            ),
            total="953.33",
        )
        wizard, action = self._create_invoices(document)
        self.assertEqual(wizard.direction, "received")
        self.assertEqual(
            wizard.journal_id, self.company_data["default_journal_purchase"]
        )
        self.assertEqual(wizard.account_id, wizard.journal_id.default_account_id)
        move = self.env["account.move"].browse(action["res_id"])
        self.assertRecordValues(
            move,
            [
                {
                    "move_type": "in_invoice",
                    "partner_id": self.vendor.id,
                    "ref": f"A-{document.folio_number}",
                    "invoice_date": date(2026, 2, 10),
                    "currency_id": self.env.ref("base.MXN").id,
                    "amount_total": 953.33,
                    "l10n_mx_sat_document_id": document.id,
                }
            ],
        )
        self.assertEqual(move.invoice_date, document.issue_date.date())
        line = move.invoice_line_ids
        self.assertRecordValues(
            line,
            [
                {
                    "name": "Widget",
                    "quantity": 2,
                    "price_unit": 500,
                    "account_id": wizard.account_id.id,
                    "product_id": False,
                }
            ],
        )
        self.assertEqual(
            sorted((t.l10n_mx_tax_type, round(t.amount, 2)) for t in line.tax_ids),
            [("isr", -10.0), ("iva", -10.67), ("iva", 16.0)],
        )
        self.assertEqual(document.vendor_bill_id, move)
        self.assertEqual(document.invoice_id, move)
        xml = move.message_ids.attachment_ids
        self.assertEqual(xml.raw, document.attachment_id.raw)
        self.assertNotIn("differs", move.message_ids[:1].body)
        self.assertIn(document.uuid, move.message_ids[:1].body)
        self.assertIn("already linked", document._l10n_mx_sat_invoice_rejection())
        with self.assertRaises(UserError):
            self._create_invoices(document)

    def test_product_and_default_tax(self):
        product = self.product_a
        product.default_code = "WID"
        self.company.account_purchase_tax_id = self._tax("vat16_T")
        document = self._create_document()
        move = self.env["account.move"].browse(
            self._create_invoices(document)[1]["res_id"]
        )
        self.assertRecordValues(
            move.invoice_line_ids,
            [
                {
                    "product_id": product.id,
                    "account_id": product.property_account_expense_id.id,
                    "tax_ids": self._tax("vat16_T").ids,
                }
            ],
        )

    def test_issued_invoice_creates_partner(self):
        document = self._create_document(direction="issued")
        wizard, action = self._create_invoices(document)
        self.assertEqual(wizard.journal_id, self.company_data["default_journal_sale"])
        move = self.env["account.move"].browse(action["res_id"])
        self.assertEqual(move.move_type, "out_invoice")
        self.assertRecordValues(
            move.partner_id,
            [{"name": "CLIENTE DEMO", "vat": CUSTOMER_RFC, "zip": "06600"}],
        )
        self.assertEqual(move.invoice_line_ids.tax_ids, self._tax("tax12"))
        self.assertEqual(move.amount_total, 1160)
        self.assertEqual(document.customer_invoice_id, move)

    def test_generic_rfc_partner(self):
        public = self.env["res.partner"].create({"name": "PUBLICO EN GENERAL"})
        document = self._create_document(
            direction="issued", receiver=("XAXX010101000", "PUBLICO EN GENERAL")
        )
        move = self.env["account.move"].browse(
            self._create_invoices(document)[1]["res_id"]
        )
        self.assertEqual(move.partner_id, public)
        foreign = self._create_document(
            direction="issued", receiver=("XEXX010101000", "ACME")
        )
        move = self.env["account.move"].browse(
            self._create_invoices(foreign)[1]["res_id"]
        )
        self.assertRecordValues(
            move.partner_id, [{"name": "ACME", "vat": False, "country_id": False}]
        )

    def test_refund_with_related(self):
        related = (
            '<cfdi:CfdiRelacionados TipoRelacion="01">'
            '<cfdi:CfdiRelacionado UUID="BBBBBBBB-0000-0000-0000-000000000001"/>'
            "</cfdi:CfdiRelacionados>"
        )
        document = self._create_document(voucher_type="E", related=related)
        move = self.env["account.move"].browse(
            self._create_invoices(document)[1]["res_id"]
        )
        self.assertEqual(move.move_type, "in_refund")
        self.assertEqual(move.amount_total, 1160)
        self.assertIn("BBBBBBBB-0000-0000-0000-000000000001", move.message_ids[:1].body)

    def test_discount(self):
        concept = CONCEPT_IVA.format(
            code="WID",
            base="900.00",
            iva="144.00",
            withholdings="",
            extra='Descuento="100.00"',
        )
        document = self._create_document(concepts=concept, total="1044.00")
        move = self.env["account.move"].browse(
            self._create_invoices(document)[1]["res_id"]
        )
        self.assertEqual(move.invoice_line_ids.discount, 10)
        self.assertEqual(move.amount_total, 1044)

    def test_exempt(self):
        concept = """
<cfdi:Concepto ClaveProdServ="01010101" Cantidad="1" ClaveUnidad="H87"
    Descripcion="Exempt" ValorUnitario="1000.00" Importe="1000.00" ObjetoImp="02">
    <cfdi:Impuestos><cfdi:Traslados>
        <cfdi:Traslado Base="1000.00" Impuesto="002" TipoFactor="Exento"/>
    </cfdi:Traslados></cfdi:Impuestos>
</cfdi:Concepto>"""
        document = self._create_document(concepts=concept, total="1000.00")
        move = self.env["account.move"].browse(
            self._create_invoices(document)[1]["res_id"]
        )
        self.assertEqual(move.invoice_line_ids.tax_ids, self._tax("tax20"))
        self.assertEqual(move.amount_total, 1000)

    def test_no_tax_object(self):
        concept = """
<cfdi:Concepto ClaveProdServ="01010101" Cantidad="1" ClaveUnidad="H87"
    Descripcion="No tax" ValorUnitario="1000.00" Importe="1000.00" ObjetoImp="01"/>"""
        document = self._create_document(concepts=concept, total="1000.00")
        move = self.env["account.move"].browse(
            self._create_invoices(document)[1]["res_id"]
        )
        self.assertFalse(move.invoice_line_ids.tax_ids)
        self.assertEqual(move.amount_total, 1000)

    def test_fuel_ieps_split(self):
        concept = """
<cfdi:Concepto ClaveProdServ="15101514" Cantidad="27.407" ClaveUnidad="LTR"
    Descripcion="MAGNA" ValorUnitario="18.329503" Importe="502.35" ObjetoImp="02">
    <cfdi:Impuestos><cfdi:Traslados>
        <cfdi:Traslado Base="489.98" Impuesto="002" TipoFactor="Tasa"
            TasaOCuota="0.160000" Importe="78.40"/>
    </cfdi:Traslados></cfdi:Impuestos>
</cfdi:Concepto>"""
        document = self._create_document(
            concepts=concept, subtotal="502.35", total="580.75"
        )
        move = self.env["account.move"].browse(
            self._create_invoices(document)[1]["res_id"]
        )
        self.assertRecordValues(
            move.invoice_line_ids,
            [
                {
                    "name": "MAGNA",
                    "price_unit": 489.98,
                    "tax_ids": self._tax("tax14").ids,
                },
                {"name": "MAGNA (IEPS)", "price_unit": 12.37, "tax_ids": []},
            ],
        )
        self.assertEqual(move.amount_total, 580.75)
        self.assertNotIn("differs", move.message_ids[:1].body)

    def test_ieps_partial_base_split(self):
        concept = """
<cfdi:Concepto ClaveProdServ="81161700" Cantidad="1" ClaveUnidad="E48"
    Descripcion="Telecom" ValorUnitario="150.00" Importe="150.00" ObjetoImp="02">
    <cfdi:Impuestos><cfdi:Traslados>
        <cfdi:Traslado Base="100.00" Impuesto="003" TipoFactor="Tasa"
            TasaOCuota="0.080000" Importe="8.00"/>
        <cfdi:Traslado Base="158.00" Impuesto="002" TipoFactor="Tasa"
            TasaOCuota="0.160000" Importe="25.28"/>
    </cfdi:Traslados></cfdi:Impuestos>
</cfdi:Concepto>"""
        document = self._create_document(
            concepts=concept, subtotal="150.00", total="183.28"
        )
        move = self.env["account.move"].browse(
            self._create_invoices(document)[1]["res_id"]
        )
        iva, ieps = self._tax("tax14"), self._tax("ieps_8_purchase")
        self.assertRecordValues(
            move.invoice_line_ids,
            [
                {"price_unit": 100, "tax_ids": (iva + ieps).ids},
                {"price_unit": 50, "tax_ids": iva.ids},
            ],
        )
        self.assertEqual(move.amount_total, 183.28)

    def test_fuel_statement_ecc12(self):
        complement = """
<ecc12:EstadoDeCuentaCombustible
    xmlns:ecc12="http://www.sat.gob.mx/EstadoDeCuentaCombustible12" Version="1.2"
    TipoOperacion="Tarjeta" NumeroDeCuenta="1234" SubTotal="100.00" Total="114.00">
    <ecc12:Conceptos>
        <ecc12:ConceptoEstadoDeCuentaCombustible Identificador="1"
            Fecha="2026-02-05T10:00:00" Rfc="XIA190128J61" ClaveEstacion="E1"
            Cantidad="5.0" TipoCombustible="1" Unidad="LTR" NombreCombustible="MAGNA"
            FolioOperacion="OP1" ValorUnitario="20.00" Importe="100.00">
            <ecc12:Traslados>
                <ecc12:Traslado Impuesto="IVA" TasaOCuota="0.16" Importe="14.00"/>
            </ecc12:Traslados>
        </ecc12:ConceptoEstadoDeCuentaCombustible>
    </ecc12:Conceptos>
</ecc12:EstadoDeCuentaCombustible>"""
        concept = """
<cfdi:Concepto ClaveProdServ="15101500" Cantidad="1" ClaveUnidad="ACT"
    Descripcion="Fuel statement" ValorUnitario="100.00" Importe="100.00" ObjetoImp="02">
    <cfdi:Impuestos><cfdi:Traslados>
        <cfdi:Traslado Base="87.50" Impuesto="002" TipoFactor="Tasa"
            TasaOCuota="0.160000" Importe="14.00"/>
    </cfdi:Traslados></cfdi:Impuestos>
</cfdi:Concepto>"""
        document = self._create_document(
            concepts=concept, subtotal="100.00", total="114.00", complement=complement
        )
        wizard, action = self._create_invoices(document)
        move = self.env["account.move"].browse(action["res_id"])
        self.assertRecordValues(
            move.invoice_line_ids,
            [
                {
                    "name": "Station E1 - Operation OP1",
                    "price_unit": 87.5,
                    "tax_ids": self._tax("tax14").ids,
                    "account_id": wizard.account_id.id,
                },
                {
                    "name": "Station E1 - Operation OP1 (IEPS)",
                    "price_unit": 12.5,
                    "tax_ids": [],
                    "account_id": wizard.account_id.id,
                },
            ],
        )
        self.assertEqual(move.amount_total, 114)

    def test_local_taxes(self):
        complement = """
<implocal:ImpuestosLocales xmlns:implocal="http://www.sat.gob.mx/implocal" version="1.0"
    TotaldeRetenciones="0.00" TotaldeTraslados="30.00">
    <implocal:TrasladosLocales ImpLocTrasladado="ISH" TasadeTraslado="3.00"
        Importe="30.00"/>
    <implocal:RetencionesLocales ImpLocRetenido="CEDULAR" TasadeRetencion="1.00"
        Importe="10.00"/>
</implocal:ImpuestosLocales>"""
        document = self._create_document(total="1180.00", complement=complement)
        wizard, action = self._create_invoices(document)
        move = self.env["account.move"].browse(action["res_id"])
        self.assertRecordValues(
            move.invoice_line_ids[1:],
            [
                {
                    "name": "ISH",
                    "price_unit": 30,
                    "tax_ids": [],
                    "account_id": wizard.account_id.id,
                },
                {
                    "name": "CEDULAR",
                    "price_unit": -10,
                    "tax_ids": [],
                    "account_id": wizard.account_id.id,
                },
            ],
        )
        self.assertEqual(move.amount_total, 1180)

    def test_missing_tax(self):
        concept = """
<cfdi:Concepto ClaveProdServ="50202306" Cantidad="10" ClaveUnidad="LTR"
    Descripcion="Beer" ValorUnitario="10.00" Importe="100.00" ObjetoImp="02">
    <cfdi:Impuestos><cfdi:Traslados>
        <cfdi:Traslado Base="10" Impuesto="003" TipoFactor="Cuota"
            TasaOCuota="1.500000" Importe="15.00"/>
    </cfdi:Traslados></cfdi:Impuestos>
</cfdi:Concepto>"""
        document = self._create_document(
            concepts=concept, subtotal="100.00", total="115.00"
        )
        with self.assertRaisesRegex(UserError, "IEPS Cuota 1.5"):
            self._create_invoices(document)
        self.assertFalse(document.invoice_id)

    def test_total_mismatch_warning(self):
        document = self._create_document(total="1200.00")
        move = self.env["account.move"].browse(
            self._create_invoices(document)[1]["res_id"]
        )
        self.assertEqual(move.amount_total, 1160)
        self.assertIn("differs", move.message_ids[:1].body)

    def test_rejections(self):
        cancelled = self._create_document()
        cancelled._sat_write({"sat_status": "cancelled"})
        self.assertIn("cancelled", cancelled._l10n_mx_sat_invoice_rejection())
        payment = self._create_document(voucher_type="P", subtotal="0", total="0")
        self.assertIn("type P", payment._l10n_mx_sat_invoice_rejection())
        with self.assertRaisesRegex(UserError, "cancelled"):
            self._create_invoices(cancelled + payment)
        with self.assertRaisesRegex(ValidationError, "issued CFDIs"):
            self._create_invoices(
                self._create_document() + self._create_document("issued")
            )

    def test_inactive_currency(self):
        document = self._create_document(moneda="JPY")
        with self.assertRaisesRegex(UserError, "JPY"):
            self._create_invoices(document)

    def test_several_documents_and_user_access(self):
        documents = self._create_document() + self._create_document()
        wizard, action = self._create_invoices(documents, user=self.user)
        moves = self.env["account.move"].search(action["domain"])
        self.assertEqual(len(moves), 2)
        self.assertEqual(moves.create_uid, self.user)
        self.assertEqual(documents.vendor_bill_id, moves)
        self.assertEqual(moves.invoice_line_ids.mapped("price_subtotal"), [1000, 1000])

    def test_wizard_context_does_not_reach_attachments(self):
        """The default_document_ids of the wizard holds ids of SAT documents:
        Documents reads it as ir.attachment.document_ids (documents.document)
        and fails with a missing record when it reaches the XML attachment."""
        document = self._create_document()
        Attachment = self.env.registry["ir.attachment"]
        original_create = Attachment.create
        contexts = []

        def spy_create(records, vals_list):
            contexts.append(dict(records.env.context))
            return original_create(records, vals_list)

        with patch.object(Attachment, "create", spy_create):
            self._create_invoices(document)
        self.assertTrue(contexts)
        for context in contexts:
            self.assertNotIn("default_document_ids", context)

    def test_single_invoice_opens_the_form_view(self):
        """The action of the invoices has the list view as view_id: the web
        client must not get it as the form view."""
        _wizard, action = self._create_invoices(self._create_document())
        action = clean_action(action, self.env)
        self.assertEqual(action["views"], [(False, "form")])
        self.assertTrue(action["res_id"])

    def _create_bill(self, move_type="in_invoice", partner=None, amount=1160):
        return self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": (partner or self.vendor).id,
                "invoice_date": "2026-02-10",
                "invoice_line_ids": [
                    Command.create(
                        {"name": "Widget", "price_unit": amount, "tax_ids": False}
                    )
                ],
            }
        )

    def _link_wizard(self, move, **vals):
        action = move.action_l10n_mx_sat_link_document()
        return (
            self.env[action["res_model"]]
            .with_user(self.user)
            .with_context(**action["context"])
            .create(vals)
        )

    def test_link_existing_invoice(self):
        document = self._create_document()
        self._create_document(total="2320.00")
        self._create_document(issuer=("AAA010101AAA", "OTRO PROVEEDOR"))
        bill = self._create_bill()
        wizard = self._link_wizard(bill)
        # The only CFDI of the vendor with the total of the bill is proposed
        self.assertEqual(wizard.document_id, document)
        self.assertEqual(wizard.document_partner, "SOLUCIONES DEMO")
        candidates = self.env["l10n_mx_sat.document"].search(wizard.document_domain)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates.mapped("issuer_rfc"), [VENDOR_RFC] * 2)
        wizard.only_partner = False
        self.assertEqual(
            len(self.env["l10n_mx_sat.document"].search(wizard.document_domain)), 3
        )
        wizard.document_id = document
        wizard.action_link()
        self.assertEqual(bill.l10n_mx_sat_document_id, document)
        self.assertEqual(document.vendor_bill_id, bill)
        self.assertEqual(document.invoice_id, bill)
        # The bill is not modified
        self.assertEqual(bill.state, "draft")
        self.assertEqual(bill.invoice_line_ids.mapped("name"), ["Widget"])
        self.assertEqual(bill.amount_total, 1160)
        attachment = self.env["ir.attachment"].search(
            [("res_model", "=", "account.move"), ("res_id", "=", bill.id)]
        )
        self.assertEqual(attachment.raw, document.attachment_id.raw)
        self.assertIn("linked to the SAT CFDI", bill.message_ids[0].body)
        self.assertNotIn("differs", bill.message_ids[0].body)
        # A linked CFDI is no longer offered nor imported
        other_bill = self._create_bill()
        self.assertNotIn(
            document,
            self.env["l10n_mx_sat.document"].search(
                self._link_wizard(other_bill, only_partner=False).document_domain
            ),
        )
        with self.assertRaisesRegex(UserError, "already linked"):
            self._create_invoices(document)

    def test_link_posted_invoice_with_other_total(self):
        document = self._create_document(direction="issued")
        customer = self.env["res.partner"].create(
            {"name": "Cliente Demo", "vat": CUSTOMER_RFC}
        )
        invoice = self._create_bill("out_invoice", customer, amount=1000)
        invoice.action_post()
        wizard = self._link_wizard(invoice)
        # Totals differ: nothing is proposed, the user chooses
        self.assertFalse(wizard.document_id)
        wizard.document_id = document
        wizard.action_link()
        self.assertEqual(document.customer_invoice_id, invoice)
        self.assertEqual(invoice.state, "posted")
        self.assertIn("differs", invoice.message_ids[0].body)

    def test_link_rejections(self):
        document = self._create_document()
        bill = self._create_bill()
        with self.assertRaisesRegex(UserError, "does not correspond"):
            self._create_bill("in_refund")._l10n_mx_sat_link_document(document)
        with self.assertRaisesRegex(UserError, "does not correspond"):
            self._create_bill("out_invoice")._l10n_mx_sat_link_document(document)
        with self.assertRaisesRegex(UserError, "not an invoice"):
            self.env["account.move"].create({})._l10n_mx_sat_link_document(document)
        bill._l10n_mx_sat_link_document(document)
        with self.assertRaisesRegex(UserError, "already linked to the CFDI"):
            bill._l10n_mx_sat_link_document(self._create_document())
        with self.assertRaisesRegex(UserError, "already linked"):
            self._create_bill()._l10n_mx_sat_link_document(document)
