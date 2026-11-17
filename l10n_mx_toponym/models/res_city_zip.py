# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import csv
import io
import logging

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

_logger = logging.getLogger(__name__)

# Catálogo Nacional de Códigos Postales, Correos de México (datos abiertos).
SEPOMEX_URL = "https://www.correosdemexico.gob.mx/datosabiertos/cp/cpdescarga.txt"
SEPOMEX_URL_PARAM = "l10n_mx_toponym.sepomex_url"
SEPOMEX_LAST_UPDATE_PARAM = "l10n_mx_toponym.sepomex_last_update"
SEPOMEX_FIELDS = [
    "d_codigo",
    "d_asenta",
    "d_tipo_asenta",
    "D_mnpio",
    "d_estado",
    "d_ciudad",
    "d_CP",
    "c_estado",
    "c_oficina",
    "c_CP",
    "c_tipo_asenta",
    "c_mnpio",
    "id_asenta_cpcons",
    "d_zona",
    "c_cve_ciudad",
]
# SEPOMEX numeric state code -> SAT alpha codes used in res.country.state
# (Mexico City is CMX in current databases, DF in older ones).
SEPOMEX_STATE_TO_SAT = {
    "01": "AGU",
    "02": "BCN",
    "03": "BCS",
    "04": "CAM",
    "05": "COA",
    "06": "COL",
    "07": "CHP",
    "08": "CHH",
    "09": ("CMX", "DF"),
    "10": "DUR",
    "11": "GUA",
    "12": "GRO",
    "13": "HID",
    "14": "JAL",
    "15": "MEX",
    "16": "MIC",
    "17": "MOR",
    "18": "NAY",
    "19": "NLE",
    "20": "OAX",
    "21": "PUE",
    "22": "QUE",
    "23": "ROO",
    "24": "SLP",
    "25": "SIN",
    "26": "SON",
    "27": "TAB",
    "28": "TAM",
    "29": "TLA",
    "30": "VER",
    "31": "YUC",
    "32": "ZAC",
}


class ResCityZip(models.Model):
    _inherit = "res.city.zip"
    _rec_names_search = (
        "name",
        "l10n_mx_edi_colony",
        "city_id",
        "state_id",
        "country_id",
    )

    l10n_mx_edi_colony = fields.Char(
        string="Colony",
    )
    l10n_mx_edi_colony_code = fields.Char(
        string="Colony Code",
    )
    l10n_mx_edi_locality_id = fields.Many2one(
        comodel_name="l10n_mx_edi.res.locality",
        string="Locality",
    )

    _name_city_uniq = models.Constraint(
        "UNIQUE(name, city_id, l10n_mx_edi_colony_code)",
        "You already have a zip with that code in the same city. "
        "The zip code must be unique within its city",
    )

    @api.depends(
        "name",
        "l10n_mx_edi_colony",
        "city_id",
        "city_id.name",
        "city_id.state_id",
        "city_id.state_id.name",
        "city_id.country_id",
        "city_id.country_id.name",
    )
    def _compute_display_name(self):
        """'ZIP, colony, city, state, country': the colony is what tells apart
        the entries of one postal code, so it shows in every Many2one."""
        for rec in self:
            parts = [rec.name]
            if rec.l10n_mx_edi_colony:
                parts.append(rec.l10n_mx_edi_colony)
            parts.append(rec.city_id.name)
            if rec.city_id.state_id:
                parts.append(rec.city_id.state_id.name)
            if rec.city_id.country_id:
                parts.append(rec.city_id.country_id.name)
            rec.display_name = ", ".join(part for part in parts if part)

    @api.model
    def _search_display_name(self, operator, value):
        """Match the city, state and country through a subquery on res.city.

        By default each of them joins res_city inside the OR with the zip
        columns; with the whole catalog of Correos de México PostgreSQL then
        compares every zip with every city, and a zip code typed in a Many2one
        takes tens of seconds.
        """
        if operator in Domain.NEGATIVE_OPERATORS or not isinstance(value, str):
            return super()._search_display_name(operator, value)
        if not value and operator.endswith("like") and "=" not in operator:
            return super()._search_display_name(operator, value)
        cities = self.env["res.city"]._search(
            Domain("display_name", operator, value)
            | Domain("state_id.display_name", operator, value)
            | Domain("country_id.display_name", operator, value)
        )
        return (
            Domain("name", operator, value)
            | Domain("l10n_mx_edi_colony", operator, value)
            | Domain("city_id", "in", cities)
        )

    # ------------------------------------------------------------ SEPOMEX
    @api.model
    def _sepomex_download(self):
        """Text of the national zip catalog of Correos de México."""
        url = (
            self.env["ir.config_parameter"].sudo().get_str(SEPOMEX_URL_PARAM)
            or SEPOMEX_URL
        )
        response = requests.get(url, timeout=180)
        response.raise_for_status()
        return response.content.decode("latin-1")

    @api.model
    def _sepomex_rows(self, text):
        """Rows of the catalog: the first line is the legal notice, the second
        the header; the data is pipe-delimited."""
        lines = io.StringIO(text)
        next(lines, None)
        reader = csv.DictReader(lines, delimiter="|", fieldnames=SEPOMEX_FIELDS)
        next(reader, None)
        for row in reader:
            if (row.get("d_codigo") or "").strip():
                yield row

    @api.model
    def _sepomex_load(self, rows):
        """Additively create the (city, zip, colony code) entries of ``rows``
        missing from the database; returns (created, skipped).

        Existing entries and the partners pointing at them are never touched.
        The city comes from an entry of the same postal code or from the SAT
        municipality (SEPOMEX state + municipality codes); the locality from an
        entry of the same postal code.
        """
        self.env.cr.execute(
            """
            SELECT city_id, name, COALESCE(l10n_mx_edi_colony_code, ''),
                   l10n_mx_edi_locality_id
            FROM res_city_zip
            """
        )
        existing = set()
        cp_to_city = {}
        cp_to_locality = {}
        for city_id, name, colony_code, locality_id in self.env.cr.fetchall():
            existing.add((city_id, name, colony_code))
            cp_to_city.setdefault(name, city_id)
            if locality_id:
                cp_to_locality.setdefault(name, locality_id)
        self.env.cr.execute(
            """
            SELECT st.code, ci.l10n_mx_edi_code, ci.id
            FROM res_city ci
            JOIN res_country_state st ON st.id = ci.state_id
            JOIN res_country co ON co.id = st.country_id
            WHERE co.code = 'MX' AND ci.l10n_mx_edi_code IS NOT NULL
            """
        )
        state_mnpio_to_city = {}
        for state_code, mnpio, city_id in self.env.cr.fetchall():
            state_mnpio_to_city.setdefault((state_code, mnpio), city_id)

        to_create = []
        seen = set()
        skipped = 0
        for row in rows:
            cp = row["d_codigo"].strip()
            colony_code = (row.get("id_asenta_cpcons") or "").strip()
            city_id = cp_to_city.get(cp)
            if not city_id:
                codes = SEPOMEX_STATE_TO_SAT.get(
                    (row.get("c_estado") or "").strip(), ()
                )
                if isinstance(codes, str):
                    codes = (codes,)
                mnpio = (row.get("c_mnpio") or "").strip()
                for sat_state in codes:
                    city_id = state_mnpio_to_city.get((sat_state, mnpio))
                    if city_id:
                        break
            if not city_id:
                skipped += 1
                continue
            key = (city_id, cp, colony_code)
            if key in existing or key in seen:
                continue
            seen.add(key)
            to_create.append(
                {
                    "name": cp,
                    "l10n_mx_edi_colony": (row.get("d_asenta") or "").strip(),
                    "l10n_mx_edi_colony_code": colony_code,
                    "city_id": city_id,
                    "l10n_mx_edi_locality_id": cp_to_locality.get(cp, False),
                }
            )
        if not to_create:
            return 0, skipped
        records = self.sudo().create(to_create)
        self.env.cr.execute(
            """
            INSERT INTO ir_model_data (name, res_id, module, model, noupdate)
                SELECT
                    'res_city_zip_mx_' || lower(res_country_state.code) || '_' ||
                        res_city.l10n_mx_edi_code || '_' ||
                        COALESCE(res_city_zip.l10n_mx_edi_colony_code, '') || '_' ||
                        res_city_zip.name,
                    res_city_zip.id, 'l10n_mx_toponym', 'res.city.zip', TRUE
                FROM res_city_zip
                JOIN res_city ON res_city.id = res_city_zip.city_id
                JOIN res_country_state ON res_country_state.id = res_city.state_id
                WHERE res_city_zip.id IN %s
                ON CONFLICT (module, name) DO NOTHING
            """,
            [tuple(records.ids)],
        )
        return len(records), skipped

    @api.model
    def _sepomex_refresh(self, raise_on_error=True):
        """Download the catalog and load what is missing; returns (created,
        skipped) or None when the download failed and errors are not raised."""
        try:
            text = self._sepomex_download()
        except (requests.RequestException, OSError) as error:
            _logger.warning("SEPOMEX catalog not downloaded: %s", error)
            if raise_on_error:
                raise UserError(
                    self.env._(
                        "The zip catalog could not be downloaded from Correos de "
                        "México: %s",
                        error,
                    )
                ) from error
            return None
        created, skipped = self._sepomex_load(self._sepomex_rows(text))
        self.env["ir.config_parameter"].sudo().set_str(
            SEPOMEX_LAST_UPDATE_PARAM, fields.Datetime.to_string(fields.Datetime.now())
        )
        _logger.info(
            "SEPOMEX catalog loaded: %d new entries, %d without a known city",
            created,
            skipped,
        )
        return created, skipped

    @api.model
    def _cron_sepomex_refresh(self):
        self._sepomex_refresh(raise_on_error=False)

    def action_sepomex_refresh(self):
        created, skipped = self._sepomex_refresh()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": self.env._("Zip catalog updated"),
                "message": self.env._(
                    "%(created)s new entries loaded from Correos de México; "
                    "%(skipped)s skipped because their municipality is unknown.",
                    created=created,
                    skipped=skipped,
                ),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
