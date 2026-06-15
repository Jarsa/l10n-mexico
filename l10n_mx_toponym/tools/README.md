# Maintainer tools

## regenerate_res_city_zip_csv.py

Refreshes `static/data/res.city.zip.csv` from a new SEPOMEX national catalog.

The SAT `c_CodigoPostal` catalog only maps postal codes to state / municipality
/ locality — it does **not** contain colonies. Colony names and codes come from
the SEPOMEX catalog published by Correos de México (`CPdescarga.txt`), so that
is the source this tool consumes.

### Usage

1. Download the current `CPdescarga.txt` from Correos de México.
2. Run the tool in an Odoo shell against a development database that already has
   `l10n_mx_edi_extended` and `l10n_mx_toponym` installed (cities and localities
   must exist so the colonies can be linked):

   ```bash
   SEPOMEX_TXT=~/Downloads/CPdescarga.txt \
   python odoo-bin shell -c odoo-server.conf -d <devdb> \
       < l10n_mx_toponym/tools/regenerate_res_city_zip_csv.py
   ```

3. Review the regenerated `static/data/res.city.zip.csv`, bump the module
   version in `__manifest__.py`, and add a `migrations/<new-version>/post-migrate.py`
   (copy the existing one) so installed databases load the new postal codes on
   update.

The load is additive: it only inserts `(city_id, postal_code, colony_code)`
combinations that are missing, so it never duplicates rows nor disturbs partner
`zip_id` references.
