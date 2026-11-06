# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

from odoo.addons.base.models.res_bank import sanitize_account_number

_logger = logging.getLogger(__name__)
DATE_TOLERANCE = timedelta(days=3)


class L10nMxSatPayment(models.Model):
    _name = "l10n_mx_sat.payment"
    _description = "Payment of a SAT payment complement"
    _order = "document_id, sequence, id"

    document_id = fields.Many2one(
        comodel_name="l10n_mx_sat.document",
        string="SAT document",
        required=True,
        ondelete="cascade",
        index=True,
        readonly=True,
    )
    company_id = fields.Many2one(related="document_id.company_id", store=True)
    direction = fields.Selection(related="document_id.direction", store=True)
    sequence = fields.Integer(readonly=True)
    date = fields.Date(string="Payment date", readonly=True)
    payment_form = fields.Char(string="Payment form", readonly=True)
    currency_code = fields.Char(string="Currency", readonly=True)
    rate = fields.Float(digits=(16, 6), readonly=True)
    amount = fields.Float(digits=(16, 6), readonly=True)
    operation_number = fields.Char(readonly=True)
    ordering_rfc = fields.Char(string="Ordering bank RFC", readonly=True)
    ordering_bank = fields.Char(string="Ordering bank", readonly=True)
    ordering_account = fields.Char(readonly=True)
    beneficiary_rfc = fields.Char(string="Beneficiary bank RFC", readonly=True)
    beneficiary_account = fields.Char(readonly=True)
    line_ids = fields.One2many(
        comodel_name="l10n_mx_sat.payment.line",
        inverse_name="payment_id",
        string="Related documents",
        readonly=True,
    )
    payment_id = fields.Many2one(
        comodel_name="account.payment",
        string="Payment",
        readonly=True,
        copy=False,
        index="btree_not_null",
    )
    state = fields.Selection(
        selection=[("pending", "To apply"), ("done", "Applied")],
        compute="_compute_state",
        store=True,
    )

    @api.depends("payment_id")
    def _compute_state(self):
        for payment in self:
            payment.state = "done" if payment.payment_id else "pending"

    def action_apply(self):
        errors = []
        for payment in self.filtered(lambda p: not p.payment_id):
            try:
                with self.env.cr.savepoint():
                    payment._apply()
            except UserError as err:
                errors.append(f"{payment.document_id.uuid}: {err.args[0]}")
        if errors:
            raise UserError("\n".join(errors))
        return True

    def _apply(self, raise_error=True):
        """Link or create the payment of each ``Pago`` node."""
        for payment in self:
            try:
                with self.env.cr.savepoint():
                    payment._apply_one()
            except UserError as err:
                if raise_error:
                    raise
                _logger.info("%s: %s", payment.document_id.uuid, err.args[0])

    def _apply_one(self):
        self.ensure_one()
        if self.payment_id:
            return self.payment_id
        document = self.document_id
        company = document.company_id
        mode = company.l10n_mx_sat_payment_mode
        if mode == "none":
            raise UserError(
                self.env._(
                    "The payment complements are not applied: choose what to do "
                    "with them in the SAT tab of the company %(company)s.",
                    company=company.display_name,
                )
            )
        if document.sat_status == "cancelled":
            raise UserError(self.env._("The payment complement is cancelled."))
        invoices = self.env["account.move"]
        for line in self.line_ids:
            invoice = line._find_invoice()
            if not invoice:
                raise UserError(
                    self.env._(
                        "The invoice %(uuid)s of the complement is not registered.",
                        uuid=line.uuid,
                    )
                )
            if invoice.state != "posted":
                raise UserError(
                    self.env._(
                        "The invoice %(name)s is not posted.", name=invoice.display_name
                    )
                )
            invoices |= invoice
        if not invoices:
            raise UserError(self.env._("The complement has no related documents."))
        partners = invoices.partner_id.commercial_partner_id
        if len(partners) > 1:
            raise UserError(
                self.env._("The related invoices belong to several partners.")
            )
        journal = self._find_journal()
        payment = self._find_existing_payment(invoices, partners, journal)
        if not payment:
            if mode != "create":
                raise UserError(
                    self.env._("No registered payment matches the complement.")
                )
            if not journal:
                raise UserError(
                    self.env._(
                        "No bank journal for the account %(account)s: add the bank "
                        "account to the company or set a fallback journal.",
                        account=self._company_account() or "-",
                    )
                )
            payment = self._create_payment(invoices, journal)
        self.write({"payment_id": payment.id})
        payment.write({"l10n_mx_sat_document_id": document.id})
        payment.message_post(
            body=self.env._(
                "SAT payment complement %(uuid)s applied to %(invoices)s.",
                uuid=document.uuid,
                invoices=", ".join(invoices.mapped("display_name")),
            )
        )
        self._after_apply(payment, invoices)
        return payment

    def _after_apply(self, payment, invoices):
        """Hook for the modules that register the CFDI on the payment."""

    def _company_account(self):
        """Bank account of the company in the complement."""
        self.ensure_one()
        return (
            self.beneficiary_account
            if self.direction == "issued"
            else self.ordering_account
        )

    def _find_journal(self):
        self.ensure_one()
        company = self.document_id.company_id
        account = sanitize_account_number(self._company_account())
        journal = self.env["account.journal"]
        if account:
            bank_account = self.env["res.partner.bank"].search(
                [
                    ("sanitized_acc_number", "=", account),
                    ("partner_id", "=", company.partner_id.id),
                ],
                limit=1,
            )
            if bank_account:
                journal = journal.search(
                    [
                        ("bank_account_id", "=", bank_account.id),
                        ("company_id", "=", company.id),
                    ],
                    limit=1,
                )
        return journal or company.l10n_mx_sat_payment_journal_id

    def _find_existing_payment(self, invoices, partner, journal):
        self.ensure_one()
        payment_type = "inbound" if self.direction == "issued" else "outbound"
        domain = [
            ("company_id", "=", self.document_id.company_id.id),
            ("partner_id", "child_of", partner.id),
            ("payment_type", "=", payment_type),
            ("state", "in", ("in_process", "paid")),
            ("l10n_mx_sat_document_id", "=", False),
            ("date", ">=", self.date - DATE_TOLERANCE),
            ("date", "<=", self.date + DATE_TOLERANCE),
            ("currency_id.name", "=", self.currency_code),
        ]
        if journal:
            domain.append(("journal_id", "=", journal.id))
        candidates = (
            self.env["account.payment"]
            .search(domain)
            .filtered(
                lambda p: float_compare(
                    p.amount, self.amount, precision_rounding=p.currency_id.rounding
                )
                == 0
            )
        )
        reconciled = candidates.filtered(lambda p: p.reconciled_invoice_ids & invoices)
        candidates = reconciled or candidates
        if len(candidates) > 1:
            raise UserError(
                self.env._(
                    "Several payments match the complement: %(payments)s.",
                    payments=", ".join(candidates.mapped("display_name")),
                )
            )
        return candidates

    def _create_payment(self, invoices, journal):
        self.ensure_one()
        document = self.document_id
        currency = self.env["res.currency"].search(
            [("name", "=", self.currency_code)], limit=1
        )
        if not currency:
            raise UserError(
                self.env._(
                    "The currency %(code)s is not active.", code=self.currency_code
                )
            )
        # ponytail: the register wizard allocates the amount in invoice order;
        # ImpPagado per invoice is not enforced when one payment covers several.
        register = (
            self.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=invoices.ids)
            .create(
                {
                    "payment_date": self.date,
                    "journal_id": journal.id,
                    "currency_id": currency.id,
                    "amount": self.amount,
                    "group_payment": True,
                    "communication": " ".join(
                        filter(
                            None,
                            [
                                f"{document.series or ''}{document.folio_number or ''}",
                                document.uuid,
                            ],
                        )
                    ),
                }
            )
        )
        return register._create_payments()


class L10nMxSatPaymentLine(models.Model):
    _name = "l10n_mx_sat.payment.line"
    _description = "Document related to a SAT payment complement"
    _order = "payment_id, id"

    payment_id = fields.Many2one(
        comodel_name="l10n_mx_sat.payment",
        required=True,
        ondelete="cascade",
        index=True,
        readonly=True,
    )
    uuid = fields.Char(string="UUID", readonly=True, index=True)
    series = fields.Char(readonly=True)
    folio = fields.Char(readonly=True)
    installment = fields.Integer(readonly=True)
    previous_balance = fields.Float(digits=(16, 6), readonly=True)
    amount_paid = fields.Float(digits=(16, 6), readonly=True)
    remaining_balance = fields.Float(digits=(16, 6), readonly=True)
    currency_code = fields.Char(string="Currency", readonly=True)
    equivalence = fields.Float(digits=(16, 10), readonly=True)
    invoice_id = fields.Many2one(
        comodel_name="account.move",
        string="Invoice",
        compute="_compute_invoice_id",
    )

    def _compute_invoice_id(self):
        for line in self:
            line.invoice_id = line._find_invoice()

    def _find_invoice(self):
        """Invoice registered for the related UUID, through its SAT document."""
        self.ensure_one()
        document = self.payment_id.document_id
        related = self.env["l10n_mx_sat.document"].search(
            [
                ("uuid", "=", self.uuid),
                ("company_id", "=", document.company_id.id),
                ("direction", "=", document.direction),
                ("document_kind", "=", "cfdi"),
            ],
            limit=1,
        )
        return related.invoice_id
