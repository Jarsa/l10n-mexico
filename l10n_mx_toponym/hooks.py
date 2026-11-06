# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import csv
from os.path import dirname, join, realpath


def _native_catalog_available(env):
    """Whether l10n_mx_edi_extended provides the res.city / locality catalogs.

    That module ships the very same catalogs, so loading ours on top of them
    breaks res_city_name_state_country_uniq. Checking whether the tables are
    already populated is not enough: when this module happens to be installed
    first the tables are still empty, and the clash only shows up later, when
    the native module loads its own CSV. Looking at the module state instead
    covers both orders of installation.
    """
    return bool(
        env["ir.module.module"].search_count(
            [
                ("name", "=", "l10n_mx_edi_extended"),
                ("state", "in", ("installed", "to install", "to upgrade")),
            ]
        )
    )


def post_init_hook(env):
    mx_country = env["res.country"].search([("code", "=", "MX")])

    # ==== Load res.city ====

    native_catalog = _native_catalog_available(env)

    res_city_vals_list = []
    if not native_catalog and not env["res.city"].search_count(
        [("country_id", "=", mx_country.id)]
    ):
        csv_path = join(dirname(realpath(__file__)), "static/data", "res.city.csv")
        with open(csv_path) as csv_file:
            for row in csv.DictReader(
                csv_file,
                delimiter="|",
                fieldnames=["l10n_mx_edi_code", "name", "state_xml_id"],
            ):
                state = env.ref(
                    "base.{}".format(row["state_xml_id"]), raise_if_not_found=False
                )
                res_city_vals_list.append(
                    {
                        "l10n_mx_edi_code": row["l10n_mx_edi_code"],
                        "name": row["name"],
                        "state_id": state.id if state else False,
                        "country_id": mx_country.id,
                    }
                )

    cities = env["res.city"].create(res_city_vals_list)

    if cities:
        env.cr.execute(
            """
            INSERT INTO ir_model_data (name, res_id, module, model, noupdate)
                SELECT
                    'res_city_mx_' || lower(res_country_state.code) ||
                        '_' || res_city.l10n_mx_edi_code,
                    res_city.id,
                    'l10n_mx_toponym',
                    'res.city',
                    TRUE
                FROM res_city
                JOIN res_country_state ON res_country_state.id = res_city.state_id
                WHERE res_city.id IN %s
        """,
            [tuple(cities.ids)],
        )

    # ==== Load l10n_mx_edi.res.locality ====

    locality_vals_list = []
    if not native_catalog and not env["l10n_mx_edi.res.locality"].search_count([]):
        csv_path = join(
            dirname(realpath(__file__)), "static/data", "l10n_mx_edi.res.locality.csv"
        )
        with open(csv_path) as csv_file:
            for row in csv.DictReader(
                csv_file, delimiter="|", fieldnames=["code", "name", "state_xml_id"]
            ):
                state = env.ref(
                    "base.{}".format(row["state_xml_id"]), raise_if_not_found=False
                )
                locality_vals_list.append(
                    {
                        "code": row["code"],
                        "name": row["name"],
                        "state_id": state.id if state else False,
                        "country_id": mx_country.id,
                    }
                )

        localities = env["l10n_mx_edi.res.locality"].create(locality_vals_list)

        if localities:
            env.cr.execute(
                """
                INSERT INTO ir_model_data (name, res_id, module, model, noupdate)
                    SELECT
                        'res_locality_mx_' || lower(res_country_state.code) || '_' ||
                            l10n_mx_edi_res_locality.code,
                        l10n_mx_edi_res_locality.id,
                        'l10n_mx_toponym',
                        'l10n_mx_edi.res.locality',
                        TRUE
                    FROM l10n_mx_edi_res_locality
                    JOIN res_country_state ON
                    res_country_state.id = l10n_mx_edi_res_locality.state_id
                    WHERE l10n_mx_edi_res_locality.id IN %s
            """,
                [tuple(localities.ids)],
            )

    # ==== Load res.city.zip from Correos de México (needs network) ====

    env["res.city.zip"]._sepomex_refresh(raise_on_error=False)
