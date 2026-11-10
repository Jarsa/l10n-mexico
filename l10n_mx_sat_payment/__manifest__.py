# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "Mexico - Payments from SAT payment complements",
    "summary": "Link or create the payments of the CFDI payment complements "
    "downloaded from the SAT",
    "version": "19.0.1.0.1",
    "category": "Accounting/Localizations",
    "website": "https://github.com/OCA/l10n-mexico",
    "author": "Jarsa, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "depends": ["l10n_mx_sat_invoice"],
    "data": [
        "security/ir.model.access.csv",
        "views/l10n_mx_sat_payment_views.xml",
        "views/l10n_mx_sat_document_views.xml",
        "views/account_payment_views.xml",
        "views/res_company_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "development_status": "Alpha",
    "maintainers": ["alan196"],
    "installable": True,
}
