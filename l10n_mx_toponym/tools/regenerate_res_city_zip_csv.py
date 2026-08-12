# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Maintainer tool: refresh static/data/res.city.zip.csv from a new SEPOMEX file.

Run it in an Odoo shell against a development database that already has the
cities/localities loaded (i.e. l10n_mx_edi_extended and this module installed).
It additively inserts the colonies present in the SEPOMEX national catalog
(CPdescarga.txt, pipe-delimited, latin-1) and then dumps the full res.city.zip
table back into the module's CSV, so the shipped catalog matches the source.

    SEPOMEX_TXT=~/Downloads/CPdescarga.txt \
    /path/to/python /path/to/odoo-bin shell -c odoo-server.conf -d <devdb>

    >>> from odoo.addons.l10n_mx_toponym.tools import regenerate_res_city_zip_csv
    >>> regenerate_res_city_zip_csv.regenerate(env)

After running, review and commit the regenerated CSV and bump the module
version; existing installs pick up the new postal codes through the
migrations/<version>/post-migrate.py script.
"""

import csv
import logging
import os
from os.path import dirname, expanduser, join, realpath

_logger = logging.getLogger(__name__)

# SEPOMEX numeric state code -> SAT alpha code used in res.country.state.
SEPOMEX_STATE_TO_SAT = {
    "01": "AGU",
    "02": "BCN",
    "03": "BCS",
    "04": "CAM",
    "05": "COA",
    "06": "COL",
    "07": "CHP",
    "08": "CHH",
    "09": "DF",
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

CSV_PATH = join(dirname(dirname(realpath(__file__))), "static/data", "res.city.zip.csv")


def _load_sepomex(env, txt_path):
    """Additively insert the SEPOMEX colonies missing from res.city.zip."""
    env.cr.execute(
        "SELECT city_id, name, COALESCE(l10n_mx_edi_colony_code, '') FROM res_city_zip"
    )
    existing = set()
    cp_to_city = {}
    for city_id, name, colony_code in env.cr.fetchall():
        existing.add((city_id, name, colony_code))
        cp_to_city.setdefault(name, city_id)

    env.cr.execute(
        """
        SELECT st.code, ci.l10n_mx_edi_code, ci.id
        FROM res_city ci
        JOIN res_country_state st ON st.id = ci.state_id
        JOIN res_country co ON co.id = st.country_id
        WHERE co.code = 'MX' AND ci.l10n_mx_edi_code IS NOT NULL
        """
    )
    state_mnpio_to_city = {}
    for state_code, mnpio, city_id in env.cr.fetchall():
        state_mnpio_to_city.setdefault((state_code, mnpio), city_id)

    to_create = []
    seen_new = set()
    skipped = 0
    with open(txt_path, encoding="latin-1") as fh:
        next(fh)  # disclaimer
        reader = csv.DictReader(fh, delimiter="|", fieldnames=SEPOMEX_FIELDS)
        next(reader)  # header
        for row in reader:
            cp = (row["d_codigo"] or "").strip()
            if not cp:
                continue
            colony_code = (row["id_asenta_cpcons"] or "").strip()
            city_id = cp_to_city.get(cp)
            if not city_id:
                sat_state = SEPOMEX_STATE_TO_SAT.get((row["c_estado"] or "").strip())
                city_id = state_mnpio_to_city.get(
                    (sat_state, (row["c_mnpio"] or "").strip())
                )
            if not city_id:
                skipped += 1
                continue
            key = (city_id, cp, colony_code)
            if key in existing or key in seen_new:
                continue
            seen_new.add(key)
            to_create.append(
                {
                    "name": cp,
                    "l10n_mx_edi_colony": (row["d_asenta"] or "").strip(),
                    "l10n_mx_edi_colony_code": colony_code,
                    "city_id": city_id,
                }
            )

    if to_create:
        new_records = env["res.city.zip"].create(to_create)
        env.cr.execute(
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
            [tuple(new_records.ids)],
        )
        env.cr.commit()
    _logger.info(
        "Inserted %d new colonies (skipped %d without a resolvable city).",
        len(to_create),
        skipped,
    )


def _dump_csv(env):
    """Dump the full res.city.zip table back into the module CSV."""
    env.cr.execute(
        """
        SELECT
            COALESCE(z.l10n_mx_edi_colony_code, '') || '|' || z.name || '|' ||
            COALESCE(z.l10n_mx_edi_colony, '') || '|' || COALESCE(cd.name, '') || '|' ||
            COALESCE(ld.name, '')
        FROM res_city_zip z
        LEFT JOIN LATERAL (
            SELECT name FROM ir_model_data
            WHERE model = 'res.city' AND res_id = z.city_id LIMIT 1
        ) cd ON TRUE
        LEFT JOIN LATERAL (
            SELECT name FROM ir_model_data
            WHERE model = 'l10n_mx_edi.res.locality'
                AND res_id = z.l10n_mx_edi_locality_id LIMIT 1
        ) ld ON TRUE
        ORDER BY z.name, z.l10n_mx_edi_colony_code, z.l10n_mx_edi_colony
        """
    )
    with open(CSV_PATH, "w", encoding="utf-8") as out:
        for (line,) in env.cr.fetchall():
            out.write(line + "\n")
    _logger.info("Wrote %s", CSV_PATH)


def regenerate(env):
    txt_path = expanduser(os.environ["SEPOMEX_TXT"])
    _logger.info("SEPOMEX source: %s", txt_path)
    _load_sepomex(env, txt_path)
    _dump_csv(env)
