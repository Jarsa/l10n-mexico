# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

{
    "name": "Mexico - Invoices from SAT CFDIs",
    "version": "19.0.1.0.2",
    "category": "Accounting/Localizations",
    "summary": "Create customer invoices and vendor bills from the CFDIs "
    "downloaded from the SAT",
    "author": "Jarsa, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/l10n-mexico",
    "license": "AGPL-3",
    "depends": ["l10n_mx", "l10n_mx_sat"],
    "data": [
        "security/ir.model.access.csv",
        "wizards/l10n_mx_sat_invoice_wizard_views.xml",
        "views/l10n_mx_sat_document_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "development_status": "Alpha",
    "maintainers": ["alan196"],
}
