# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Load postal codes added to the shipped catalog into existing databases.

Runs on update; reuses the additive loader so only colonies missing from the
database are inserted, leaving every existing res.city.zip (and the partner
zip_id references pointing at them) untouched.
"""

from odoo import SUPERUSER_ID, api

from odoo.addons.l10n_mx_toponym.hooks import _load_res_city_zip


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _load_res_city_zip(env)
