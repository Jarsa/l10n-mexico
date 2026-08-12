# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import csv
from os.path import dirname, join, realpath

# Cities and localities may be owned by the native l10n_mx_edi_extended (which
# loads them with the same naming convention) or by this module, depending on
# which one created them first. Resolve trying both, native first.
_REF_MODULES = ("l10n_mx_edi_extended", "l10n_mx_toponym")

_CITY_ZIP_FIELDS = [
    "l10n_mx_edi_colony_code",
    "name",
    "l10n_mx_edi_colony",
    "city_xml_id",
    "locality_xml_id",
]


def _resolve_ref(env, xml_id):
    if not xml_id:
        return None
    for module in _REF_MODULES:
        rec = env.ref(f"{module}.{xml_id}", raise_if_not_found=False)
        if rec:
            return rec
    return None


def _load_res_city_zip(env):
    """Additively load res.city.zip from the shipped catalog.

    Inserts only the (city_id, name, colony_code) combinations missing from the
    database, so it is safe both on install and on every update without
    duplicating rows or touching partner zip_id references. Cities are resolved
    by xml id (native or own module); for updates, a postal code already present
    is reused to place brand new colonies of an already-known zip.
    """
    csv_path = join(dirname(realpath(__file__)), "static/data", "res.city.zip.csv")

    env.cr.execute(
        "SELECT city_id, name, COALESCE(l10n_mx_edi_colony_code, '') FROM res_city_zip"
    )
    existing = set()
    cp_to_city = {}
    for city_id, name, colony_code in env.cr.fetchall():
        existing.add((city_id, name, colony_code))
        cp_to_city.setdefault(name, city_id)

    to_create = []
    seen_new = set()
    with open(csv_path) as csv_file:
        for row in csv.DictReader(csv_file, delimiter="|", fieldnames=_CITY_ZIP_FIELDS):
            city = _resolve_ref(env, row["city_xml_id"])
            city_id = city.id if city else cp_to_city.get(row["name"])
            if not city_id:
                continue
            colony_code = row["l10n_mx_edi_colony_code"] or ""
            key = (city_id, row["name"], colony_code)
            if key in existing or key in seen_new:
                continue
            seen_new.add(key)
            locality = _resolve_ref(env, row["locality_xml_id"])
            to_create.append(
                {
                    "l10n_mx_edi_colony_code": row["l10n_mx_edi_colony_code"],
                    "name": row["name"],
                    "l10n_mx_edi_colony": row["l10n_mx_edi_colony"],
                    "city_id": city_id,
                    "l10n_mx_edi_locality_id": locality.id if locality else False,
                }
            )

    if not to_create:
        return
    new_records = env["res.city.zip"].create(to_create)
    env.cr.execute(
        """
        INSERT INTO ir_model_data (name, res_id, module, model, noupdate)
            SELECT
                'res_city_zip_mx_' || lower(res_country_state.code) || '_' ||
                    res_city.l10n_mx_edi_code || '_' ||
                    COALESCE(res_city_zip.l10n_mx_edi_colony_code, '') || '_' ||
                    res_city_zip.name,
                res_city_zip.id,
                'l10n_mx_toponym',
                'res.city.zip',
                TRUE
            FROM res_city_zip
            JOIN res_city ON res_city.id = res_city_zip.city_id
            JOIN res_country_state ON res_country_state.id = res_city.state_id
            WHERE res_city_zip.id IN %s
            ON CONFLICT (module, name) DO NOTHING
    """,
        [tuple(new_records.ids)],
    )


def post_init_hook(env):
    mx_country = env["res.country"].search([("code", "=", "MX")])

    # ==== Load res.city ====

    res_city_vals_list = []
    if not env["res.city"].search_count([("country_id", "=", mx_country.id)]):
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
    if not env["l10n_mx_edi.res.locality"].search_count([]):
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

    # ==== Load res.city.zip (additive) ====

    _load_res_city_zip(env)
