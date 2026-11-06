This module creates customer invoices and vendor bills from the CFDIs
downloaded from the SAT by `l10n_mx_sat`, without the Enterprise Mexican
localization.

From the list or the form of **SAT > Documents**, **Create Invoice** opens a
wizard that asks for the journal and the account and creates one draft invoice
per CFDI:

- Issued CFDIs become customer invoices or credit notes, received CFDIs become
  vendor bills or refunds, according to the voucher type (I or E).
- The partner is found by RFC (or created), the currency, date, series and
  folio are taken from the CFDI and the XML is attached to the invoice.
- Each concept becomes a line with its product (matched by code or name), its
  income/expense account or the account of the wizard, its discount and the
  Odoo taxes matching the CFDI taxes (SAT tax type, factor type and rate),
  withholdings included.
- Fuel concepts, whose IEPS is not broken down, are split in a line with the
  VAT base and an untaxed line with the IEPS; the same applies to the
  operations of a fuel account statement complement (ECC 1.2).
- Concepts where the IEPS applies to part of the base (e.g. telecommunications)
  are split in a line with IEPS and VAT and a line with VAT only.
- Local taxes (ImpuestosLocales complement) become untaxed lines.
- The chatter warns when the total of the invoice differs from the CFDI and
  lists the related CFDIs of credit notes.

The SAT document keeps a link to the invoice so a CFDI cannot be imported
twice. The Enterprise localization (`l10n_mx_edi`) is supported by the bridge
module `l10n_mx_sat_invoice_enterprise`.
