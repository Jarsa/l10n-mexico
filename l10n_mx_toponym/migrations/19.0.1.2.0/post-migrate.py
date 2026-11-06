# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""First refresh of the zip catalog from Correos de México on existing
databases: the colonies already loaded are kept (their ir_model_data rows
have noupdate), only the missing ones are added. Without network it just logs
a warning and the monthly cron retries."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["res.city.zip"]._sepomex_refresh(raise_on_error=False)
