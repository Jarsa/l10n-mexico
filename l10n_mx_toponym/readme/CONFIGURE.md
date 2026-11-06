1.  Go to *Settings / Users & Companies / Companies*.
2.  Select the Mexican Company
3.  Be sure that you select Mexico as country.
4.  Go to *Contacts / Configuration / Localization / Countries*.
5.  Locate the Mexico.
6.  Be sure Enfoce cities is active.
7.  Be sure that the Input View is
    'l10n_mx_toponym.res.partner.address.form'

## Zip catalog (Correos de México)

The zip codes and colonies are not shipped with the module: they are
downloaded from the *Catálogo Nacional de Códigos Postales* published by
Correos de México (`cpdescarga.txt`, open data) when the module is installed
and then every month by the scheduled action *Mexico: update the zip catalog
from Correos de México*. The load is additive: only the (city, zip, colony)
entries missing from the database are created, so the zips already used by
contacts are never changed or removed.

- To refresh on demand, open *Contacts / Configuration / Localization /
  Zips* and press *Update from Correos de México* (administrators).
- The system parameter `l10n_mx_toponym.sepomex_url` overrides the download
  URL; `l10n_mx_toponym.sepomex_last_update` keeps the date of the last load.
- Without network access at install time the catalog stays empty and a
  warning is logged; the scheduled action loads it as soon as the file can be
  downloaded.
- Cities and localities keep coming from the SAT catalogs (shipped with the
  module or with `l10n_mx_edi_extended`); a colony whose municipality is not
  in those catalogs is skipped and counted in the log.
