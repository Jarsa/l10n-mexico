This module reads the CFDI payment complements (`pago20:Pagos`) downloaded from
the SAT by `l10n_mx_sat` and applies them to the invoices they pay: the payment
already registered in Odoo is linked to the complement, or a new payment is
created and reconciled with the invoices when none exists.

The bank journal of a new payment is found through the bank account of the
company written in the complement (`CtaBeneficiario` for issued complements,
`CtaOrdenante` for received ones), with an optional fallback journal.
