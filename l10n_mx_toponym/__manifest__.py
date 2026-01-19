# Copyright 2021 Jarsa - Alan Ramos
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Toponyms for Mexico",
    "version": "17.0.1.0.1",
    "depends": ["base_address_extended", "base_location"],
    "author": ("Jarsa,Odoo Community Association (OCA)"),
    "license": "AGPL-3",
    "summary": """Add toponyms to Mexico""",
    "website": "https://github.com/OCA/l10n-mexico",
    "post_init_hook": "post_init_hook",
    "data": [
        "security/ir.model.access.csv",
        "views/res_company_views.xml",
        "views/res_partner_views.xml",
        "views/res_city_zip_view.xml",
        "data/res_country_data.xml",
    ],
    "maintainers": ["alan196"],
}
