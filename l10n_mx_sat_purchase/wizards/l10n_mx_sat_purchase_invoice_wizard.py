# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from collections import defaultdict

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

from ..models.purchase_order_line import normalize_text, strip_code_prefix


class L10nMxSatPurchaseInvoiceWizard(models.TransientModel):
    _name = "l10n_mx_sat.purchase.invoice.wizard"
    _inherit = "l10n_mx_sat.document.selector.mixin"
    _description = "Create the vendor bill of purchase orders from a SAT CFDI"

    purchase_order_ids = fields.Many2many(
        comodel_name="purchase.order",
        string="Purchase Orders",
        required=True,
    )
    partner_id = fields.Many2one(compute="_compute_from_orders")
    commercial_partner_id = fields.Many2one(
        comodel_name="res.partner", compute="_compute_from_orders"
    )
    company_id = fields.Many2one(compute="_compute_from_orders")
    currency_id = fields.Many2one(compute="_compute_from_orders")
    amount_total = fields.Monetary(
        string="Orders Total", compute="_compute_from_orders"
    )
    line_ids = fields.One2many(
        comodel_name="l10n_mx_sat.purchase.invoice.wizard.line",
        inverse_name="wizard_id",
        string="SAT CFDIs",
    )
    l10n_mx_sat_document_id = fields.Many2one(
        compute="_compute_l10n_mx_sat_document_id"
    )
    available_purchase_line_ids = fields.Many2many(
        comodel_name="purchase.order.line",
        compute="_compute_available_purchase_line_ids",
        help="Lines of the selected orders that still have a quantity to bill.",
    )
    concept_ids = fields.One2many(
        comodel_name="l10n_mx_sat.purchase.invoice.wizard.concept",
        inverse_name="wizard_id",
        string="CFDI Concepts",
        compute="_compute_concept_ids",
        store=True,
        readonly=False,
    )
    concept_document_id = fields.Many2one(
        comodel_name="l10n_mx_sat.document",
        compute="_compute_concept_ids",
        store=True,
        help="CFDI the concepts were built from.",
    )
    allow_unmapped = fields.Boolean(
        string="Allow concepts without order",
        help="Bill the concepts that have no purchase order line as free lines "
        "with the product selected on each one.",
    )
    cfdi_amount_untaxed = fields.Monetary(
        string="CFDI Subtotal",
        compute="_compute_amounts",
        help="Subtotal of the CFDI after discounts.",
    )
    mapped_amount_untaxed = fields.Monetary(
        string="Amount to Bill",
        compute="_compute_amounts",
        help="Untaxed amount of the concepts with the quantities to bill.",
    )
    total_mismatch = fields.Boolean(compute="_compute_amounts")

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        order_ids = defaults.get("purchase_order_ids")
        if not order_ids or "line_ids" not in fields_list:
            return defaults
        wizard = self.new({"purchase_order_ids": order_ids})
        # Relational values of a new record are new records: keep the real ids
        documents = wizard.l10n_mx_sat_available_document_ids._origin
        matching = documents.filtered(
            lambda d: not wizard.currency_id.compare_amounts(
                d.total, wizard.amount_total
            )
        )
        defaults["line_ids"] = [
            Command.create(
                {
                    "document_id": document.id,
                    "selected": len(matching) == 1 and document == matching,
                }
            )
            for document in documents
        ]
        return defaults

    @api.depends("purchase_order_ids")
    def _compute_from_orders(self):
        for wizard in self:
            orders = wizard.purchase_order_ids
            wizard.partner_id = orders[:1].partner_id
            wizard.commercial_partner_id = orders[:1].partner_id.commercial_partner_id
            wizard.company_id = orders[:1].company_id
            wizard.currency_id = orders[:1].currency_id
            wizard.amount_total = sum(orders.mapped("amount_total"))

    @api.depends("line_ids.selected")
    def _compute_l10n_mx_sat_document_id(self):
        for wizard in self:
            selected = wizard.line_ids.filtered("selected")
            wizard.l10n_mx_sat_document_id = (
                selected.document_id if len(selected) == 1 else False
            )

    @api.depends(
        "purchase_order_ids.state", "purchase_order_ids.order_line.qty_to_invoice"
    )
    def _compute_available_purchase_line_ids(self):
        for wizard in self:
            wizard.available_purchase_line_ids = wizard._get_available_lines()

    def _get_available_lines(self):
        """Lines of the orders that can still be billed, read from the database
        (the cache of the computed field may be stale after billing)."""
        self.ensure_one()
        # The orders are real records even on a new wizard: use their lines
        lines = self.purchase_order_ids._origin.order_line
        lines.invalidate_recordset(["qty_to_invoice"])
        return lines.filtered(
            lambda line: line.order_id.state == "purchase"
            and not line.display_type
            and float_compare(
                line.qty_to_invoice, 0, precision_rounding=line.product_uom_id.rounding
            )
            > 0
        )

    @api.depends("l10n_mx_sat_document_id", "available_purchase_line_ids")
    def _compute_concept_ids(self):
        for wizard in self:
            document = wizard.l10n_mx_sat_document_id
            if document != wizard.concept_document_id:
                commands = [Command.clear()]
                if document:
                    commands += [
                        Command.create(vals) for vals in document._get_cfdi_concepts()
                    ]
                wizard.concept_ids = commands
                wizard.concept_document_id = document
            # Keep the mapping done by the user: only propose the pending concepts
            wizard._propose_purchase_lines(
                wizard.concept_ids.filtered(lambda c: not c.purchase_line_id)
            )

    @api.depends(
        "l10n_mx_sat_document_id",
        "concept_ids.purchase_line_id",
        "concept_ids.qty_to_invoice",
    )
    def _compute_amounts(self):
        for wizard in self:
            document = wizard.l10n_mx_sat_document_id
            wizard.cfdi_amount_untaxed = 0.0
            wizard.mapped_amount_untaxed = 0.0
            wizard.total_mismatch = False
            if not document:
                continue
            amounts = document._get_cfdi_amounts()
            wizard.cfdi_amount_untaxed = amounts["subtotal"] - amounts["discount"]
            wizard.mapped_amount_untaxed = sum(
                concept._get_amount_untaxed() for concept in wizard.concept_ids
            )
            wizard.total_mismatch = bool(
                wizard.currency_id.compare_amounts(
                    wizard.mapped_amount_untaxed, wizard.cfdi_amount_untaxed
                )
                if wizard.currency_id
                else float_compare(
                    wizard.mapped_amount_untaxed,
                    wizard.cfdi_amount_untaxed,
                    precision_digits=2,
                )
            )

    @api.constrains("purchase_order_ids")
    def _check_purchase_order_ids(self):
        for wizard in self:
            orders = wizard.purchase_order_ids
            if (
                len(orders.partner_id.commercial_partner_id) > 1
                or len(orders.company_id) > 1
            ):
                raise ValidationError(
                    self.env._(
                        "The purchase orders must belong to the same vendor and company"
                    )
                )
            if len(orders.currency_id) > 1:
                raise ValidationError(
                    self.env._("The purchase orders must use the same currency.")
                )

    def _l10n_mx_sat_check_document(self):
        if len(self.line_ids.filtered("selected")) > 1:
            return self.env._(
                "Select only one CFDI: each bill comes from a single CFDI."
            )
        return super()._l10n_mx_sat_check_document()

    # ------------------------------------------------------------------
    # Mapping proposal
    # ------------------------------------------------------------------

    def _get_sorted_available_lines(self):
        """Available lines, oldest order first, so ties go to the oldest pending."""
        self.ensure_one()
        return self.available_purchase_line_ids.sorted(
            key=lambda line: (
                line.order_id.date_approve or line.order_id.date_order,
                line.order_id.id,
                line.sequence,
                line.id,
            )
        )

    def _propose_purchase_lines(self, concepts):
        """Set ``purchase_line_id`` of ``concepts`` with the best matching line.

        For each concept, in the order of the CFDI, the candidates are searched
        by vendor/internal code, then by description and finally by a unique
        price; the first candidate whose pending quantity is not already taken
        by another concept wins.
        """
        self.ensure_one()
        lines = self._get_sorted_available_lines()
        if not lines or not concepts:
            return
        remaining = {line: line.qty_to_invoice for line in lines}
        for concept in self.concept_ids - concepts:
            if concept.purchase_line_id in remaining:
                remaining[concept.purchase_line_id] -= concept.qty_to_invoice
        for concept in concepts:
            for line in concept._find_candidate_lines(lines):
                quantity = concept._get_invoice_quantity_and_price(line)[0]
                if (
                    float_compare(
                        remaining[line],
                        0,
                        precision_rounding=line.product_uom_id.rounding,
                    )
                    > 0
                ):
                    concept.purchase_line_id = line
                    remaining[line] -= quantity
                    break

    # ------------------------------------------------------------------
    # Bill creation
    # ------------------------------------------------------------------

    def action_create_invoice(self):
        self.ensure_one()
        rejection = self._l10n_mx_sat_check_document()
        if rejection:
            return self._l10n_mx_sat_rejection_action(rejection)
        orders = self.purchase_order_ids
        if orders.filtered(lambda o: o.state != "purchase"):
            raise UserError(self.env._("Only confirmed purchase orders can be billed."))
        if not self.concept_ids:
            raise UserError(
                self.env._(
                    "The CFDI %s has no concepts to bill.",
                    self.l10n_mx_sat_document_id.uuid,
                )
            )
        self._check_concepts()
        document = self.l10n_mx_sat_document_id
        move = self._create_vendor_bill()
        attachment = self.env["ir.attachment"].create(
            document._prepare_vendor_bill_attachment_vals()
        )
        self._attach_cfdi(move, attachment)
        document._link_vendor_bill(move)
        self._check_bill_total(move)
        return (
            self.concept_ids.purchase_line_id.order_id or orders
        ).action_view_invoice(move)

    def _check_concepts(self):
        """Raise when the concepts cannot be billed as they are mapped."""
        self.ensure_one()
        unmapped = self.concept_ids.filtered(lambda c: not c.purchase_line_id)
        if unmapped and not self.allow_unmapped:
            raise UserError(
                self.env._(
                    "These CFDI concepts have no purchase order line:\n%(concepts)s\n"
                    "Map them to a line or tick 'Allow concepts without order'.",
                    concepts="\n".join(f"- {c.description}" for c in unmapped),
                )
            )
        without_product = unmapped.filtered(lambda c: not c.product_id)
        if without_product:
            raise UserError(
                self.env._(
                    "Select a product for the concepts without purchase order line:\n"
                    "%(concepts)s",
                    concepts="\n".join(f"- {c.description}" for c in without_product),
                )
            )
        quantities = defaultdict(float)
        for concept in self.concept_ids:
            line = concept.purchase_line_id
            rounding = (line.product_uom_id or concept.product_id.uom_id).rounding
            if (
                float_compare(concept.qty_to_invoice, 0, precision_rounding=rounding)
                <= 0
            ):
                raise UserError(
                    self.env._(
                        "The quantity to bill of the concept '%s' must be positive.",
                        concept.description,
                    )
                )
            if line:
                quantities[line] += concept.qty_to_invoice
        available = self._get_available_lines()
        for line, quantity in quantities.items():
            if line not in available:
                raise UserError(
                    self.env._(
                        "The purchase order line '%s' has nothing left to bill.",
                        line.display_name,
                    )
                )
            if (
                float_compare(
                    quantity,
                    line.qty_to_invoice,
                    precision_rounding=line.product_uom_id.rounding,
                )
                > 0
            ):
                raise UserError(
                    self.env._(
                        "The quantity to bill of '%(line)s' (%(quantity)s %(uom)s) "
                        "exceeds its pending quantity (%(pending)s %(uom)s).",
                        line=line.display_name,
                        quantity=quantity,
                        pending=line.qty_to_invoice,
                        uom=line.product_uom_id.name,
                    )
                )

    def _prepare_vendor_bill_vals(self):
        self.ensure_one()
        document = self.l10n_mx_sat_document_id
        orders = self.concept_ids.purchase_line_id.order_id or self.purchase_order_ids
        vals = orders[:1].with_company(self.company_id)._prepare_invoice()
        vals.update(
            {
                "invoice_origin": ", ".join(orders.mapped("name")),
                "ref": "-".join(filter(None, [document.series, document.folio_number]))
                or document.uuid,
                "invoice_date": document.issue_date and document.issue_date.date(),
                "invoice_line_ids": [
                    Command.create(concept._prepare_invoice_line_vals(sequence))
                    for sequence, concept in enumerate(self.concept_ids, start=1)
                ],
            }
        )
        uuid_field = self.env["account.move"]._fields.get("l10n_mx_cfdi_uuid")
        if uuid_field and not uuid_field.compute:
            # Plain field of l10n_mx_sat_vendor_bill; l10n_mx_edi computes its own
            vals["l10n_mx_cfdi_uuid"] = document.uuid
        return vals

    def _create_vendor_bill(self):
        self.ensure_one()
        vals = self._prepare_vendor_bill_vals()
        return (
            self.env["account.move"]
            .with_context(default_move_type="in_invoice")
            .with_company(self.company_id)
            .create(vals)
        )

    def _attach_cfdi(self, move, attachment):
        """Link the XML to the bill the same way ``purchase`` does on upload,
        so the CFDI decoders of the localization process it."""
        move.with_context(skip_is_manually_modified=True)._extend_with_attachments(
            move._to_files_data(attachment), new=True
        )
        move.message_post(attachment_ids=attachment.ids)
        attachment.write({"res_model": "account.move", "res_id": move.id})

    def _check_bill_total(self, move):
        """Warn in the chatter when the bill total differs from the CFDI total."""
        document = self.l10n_mx_sat_document_id
        if not move.currency_id.compare_amounts(move.amount_total, document.total):
            return False
        move.message_post(
            body=self.env._(
                "The total of the bill (%(bill)s) differs from the total of the "
                "CFDI %(uuid)s (%(cfdi)s). Review the quantities and taxes before "
                "posting it.",
                bill=move.currency_id.format(move.amount_total),
                uuid=document.uuid,
                cfdi=move.currency_id.format(document.total),
            )
        )
        return True


class L10nMxSatPurchaseInvoiceWizardLine(models.TransientModel):
    _name = "l10n_mx_sat.purchase.invoice.wizard.line"
    _description = "SAT CFDI proposed for the vendor bill of a purchase order"
    _order = "issue_date desc, id"

    wizard_id = fields.Many2one(
        comodel_name="l10n_mx_sat.purchase.invoice.wizard",
        required=True,
        ondelete="cascade",
    )
    document_id = fields.Many2one(
        comodel_name="l10n_mx_sat.document",
        string="SAT CFDI",
        required=True,
        readonly=True,
    )
    selected = fields.Boolean(string="Select")
    uuid = fields.Char(related="document_id.uuid")
    series = fields.Char(related="document_id.series")
    folio_number = fields.Char(related="document_id.folio_number")
    issuer_name = fields.Char(related="document_id.issuer_name")
    issue_date = fields.Datetime(related="document_id.issue_date")
    total = fields.Float(related="document_id.total")
    currency_code = fields.Char(related="document_id.currency_code")
    sat_status = fields.Selection(related="document_id.sat_status")


class L10nMxSatPurchaseInvoiceWizardConcept(models.TransientModel):
    _name = "l10n_mx_sat.purchase.invoice.wizard.concept"
    _description = "Concept of a SAT CFDI mapped to a purchase order line"
    _order = "sequence, id"

    wizard_id = fields.Many2one(
        comodel_name="l10n_mx_sat.purchase.invoice.wizard",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=1)
    no_identificacion = fields.Char(string="Vendor Code", readonly=True)
    description = fields.Char(readonly=True)
    product_service_code = fields.Char(string="SAT Product Code", readonly=True)
    quantity = fields.Float(
        string="CFDI Quantity", digits="Product Unit", readonly=True
    )
    unit_code = fields.Char(string="SAT Unit", readonly=True)
    price_unit = fields.Float(
        string="CFDI Unit Price", digits="Product Price", readonly=True
    )
    amount = fields.Float(string="CFDI Amount", readonly=True)
    discount_amount = fields.Float(string="CFDI Discount", readonly=True)
    tax_amount = fields.Float(string="CFDI Taxes", readonly=True)
    tax_summary = fields.Char(string="Taxes", readonly=True)
    purchase_line_id = fields.Many2one(
        comodel_name="purchase.order.line", string="Purchase Order Line"
    )
    purchase_order_id = fields.Many2one(
        related="purchase_line_id.order_id", string="Purchase Order"
    )
    purchase_uom_id = fields.Many2one(
        related="purchase_line_id.product_uom_id", string="Order Unit"
    )
    purchase_qty_pending = fields.Float(
        related="purchase_line_id.qty_to_invoice", string="Pending Quantity"
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        compute="_compute_product_id",
        store=True,
        readonly=False,
        help="Product of the purchase order line, or the product to bill when "
        "the concept has no line.",
    )
    qty_to_invoice = fields.Float(
        string="Quantity to Bill",
        digits="Product Unit",
        compute="_compute_qty_to_invoice",
        store=True,
        readonly=False,
        help="Quantity of the CFDI in the unit of the purchase order line.",
    )

    @api.depends("purchase_line_id")
    def _compute_product_id(self):
        for concept in self.filtered("purchase_line_id"):
            concept.product_id = concept.purchase_line_id.product_id

    @api.depends("purchase_line_id", "quantity", "unit_code")
    def _compute_qty_to_invoice(self):
        for concept in self:
            concept.qty_to_invoice = concept._get_invoice_quantity_and_price()[0]

    def _get_uom_from_unit_code(self):
        """Unit of measure matching the SAT ``ClaveUnidad`` of the concept, if
        the UNSPSC codes of ``product_unspsc`` are installed."""
        self.ensure_one()
        Uom = self.env["uom.uom"]
        if not self.unit_code or "unspsc_code_id" not in Uom._fields:
            return Uom
        return Uom.search([("unspsc_code_id.code", "=", self.unit_code)], limit=1)

    def _get_invoice_quantity_and_price(self, line=None):
        """Quantity and unit price of the concept in the unit of ``line`` (the
        mapped purchase line by default). The CFDI values are kept when the
        SAT unit is unknown or not convertible."""
        self.ensure_one()
        line = line or self.purchase_line_id
        quantity, price_unit = self.quantity, self.price_unit
        uom = self._get_uom_from_unit_code()
        line_uom = line.product_uom_id
        if uom and line_uom and uom != line_uom and uom._has_common_reference(line_uom):
            converted = uom._compute_quantity(quantity, line_uom, round=False)
            if not float_is_zero(converted, precision_rounding=line_uom.rounding):
                price_unit = price_unit * quantity / converted
                quantity = converted
        return quantity, price_unit

    def _get_discount_percent(self):
        self.ensure_one()
        if not self.amount or not self.discount_amount:
            return 0.0
        return self.discount_amount / self.amount * 100

    def _get_amount_untaxed(self):
        """Untaxed amount of the concept with the quantity to bill."""
        self.ensure_one()
        price_unit = self._get_invoice_quantity_and_price()[1]
        return (
            self.qty_to_invoice * price_unit * (1 - self._get_discount_percent() / 100)
        )

    def _find_candidate_lines(self, lines):
        """Purchase lines matching the concept, best criterion first.

        1. ``NoIdentificacion`` equal to the internal reference of the product
           or to the vendor code of the product for this vendor.
        2. Description equal (normalized) to the line description, the product
           name or the vendor product name.
        3. A single available line with the same unit price.

        When several lines match by code or description (same product ordered
        several times), the ones with the same unit price are preferred.
        """
        self.ensure_one()
        wizard = self.wizard_id
        vendor = wizard.commercial_partner_id
        currency = wizard.currency_id
        price_matches = lines.filtered(
            lambda line: not currency.compare_amounts(line.price_unit, self.price_unit)
        )
        code = (self.no_identificacion or "").strip().upper()
        if code:
            matches = lines.filtered(
                lambda line: (line.product_id.default_code or "").strip().upper()
                == code
                or code in line._l10n_mx_sat_get_vendor_codes(vendor)
            )
            if matches:
                return (matches & price_matches) or matches
        description = normalize_text(strip_code_prefix(self.description))
        if description:
            matches = lines.filtered(
                lambda line: description in line._l10n_mx_sat_get_descriptions(vendor)
            )
            if matches:
                return (matches & price_matches) or matches
        if len(price_matches) == 1:
            return price_matches
        return lines.browse()

    def _prepare_invoice_line_vals(self, sequence):
        """Values of the ``account.move.line`` billing this concept."""
        self.ensure_one()
        line = self.purchase_line_id
        price_unit = self._get_invoice_quantity_and_price()[1]
        if line:
            vals = line._prepare_account_move_line()
        else:
            vals = {
                "display_type": "product",
                "product_id": self.product_id.id,
                "name": self.description,
            }
        vals.update(
            {
                "sequence": sequence,
                "quantity": self.qty_to_invoice,
                "price_unit": price_unit,
                "discount": self._get_discount_percent(),
            }
        )
        return vals
