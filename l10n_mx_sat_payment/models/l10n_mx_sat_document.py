# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import logging

from odoo import Command, api, fields, models

_logger = logging.getLogger(__name__)


class L10nMxSatDocument(models.Model):
    _inherit = "l10n_mx_sat.document"

    sat_payment_ids = fields.One2many(
        comodel_name="l10n_mx_sat.payment",
        inverse_name="document_id",
        string="Payments",
    )
    sat_payment_state = fields.Selection(
        selection=[
            ("pending", "To apply"),
            ("partial", "Partially applied"),
            ("done", "Applied"),
        ],
        string="Payment complement",
        compute="_compute_sat_payment_state",
        store=True,
    )

    @api.depends("voucher_type", "sat_payment_ids.payment_id")
    def _compute_sat_payment_state(self):
        for document in self:
            payments = document.sat_payment_ids
            pending = payments.filtered(lambda p: not p.payment_id)
            if document.voucher_type != "P" or not payments:
                document.sat_payment_state = False
            elif not pending:
                document.sat_payment_state = "done"
            elif pending == payments:
                document.sat_payment_state = "pending"
            else:
                document.sat_payment_state = "partial"

    @api.model
    def _upsert_from_xml(self, tree, xml_bytes, company, request):
        document = super()._upsert_from_xml(tree, xml_bytes, company, request)
        if document and document.voucher_type == "P" and not document.sat_payment_ids:
            document._l10n_mx_sat_payment_parse(tree)
            if (
                company.l10n_mx_sat_payment_auto
                and company.l10n_mx_sat_payment_mode != "none"
            ):
                document.sat_payment_ids._apply(raise_error=False)
        return document

    def _l10n_mx_sat_payment_parse(self, tree):
        """Store the ``Pago`` nodes of the payment complement and their documents."""
        self.ensure_one()
        commands = [Command.clear()]
        for sequence, node in enumerate(tree.iter("{*}Pago"), start=1):
            if node.getparent() is None or not node.getparent().tag.endswith("Pagos"):
                continue
            lines = [
                Command.create(
                    {
                        "uuid": (related.get("IdDocumento") or "").upper(),
                        "series": related.get("Serie"),
                        "folio": related.get("Folio"),
                        "installment": int(related.get("NumParcialidad") or 0),
                        "previous_balance": float(related.get("ImpSaldoAnt") or 0),
                        "amount_paid": float(related.get("ImpPagado") or 0),
                        "remaining_balance": float(
                            related.get("ImpSaldoInsoluto") or 0
                        ),
                        "currency_code": related.get("MonedaDR"),
                        "equivalence": float(
                            related.get("EquivalenciaDR")
                            or related.get("TipoCambioDR")
                            or 1
                        ),
                    }
                )
                for related in node.findall("{*}DoctoRelacionado")
            ]
            commands.append(
                Command.create(
                    {
                        "sequence": sequence,
                        "date": (node.get("FechaPago") or "")[:10] or False,
                        "payment_form": node.get("FormaDePagoP"),
                        "currency_code": node.get("MonedaP"),
                        "rate": float(node.get("TipoCambioP") or 1),
                        "amount": float(node.get("Monto") or 0),
                        "operation_number": node.get("NumOperacion"),
                        "ordering_rfc": node.get("RfcEmisorCtaOrd"),
                        "ordering_bank": node.get("NomBancoOrdExt"),
                        "ordering_account": node.get("CtaOrdenante"),
                        "beneficiary_rfc": node.get("RfcEmisorCtaBen"),
                        "beneficiary_account": node.get("CtaBeneficiario"),
                        "line_ids": lines,
                    }
                )
            )
        self._sat_write({"sat_payment_ids": commands})

    def action_apply_payments(self):
        return self.sat_payment_ids.action_apply()
