This module adds toponyms for Mexico.

It allow you to ease capture for contact using zip code and get the
following information:

- Colony
- Colony Code
- Locality
- City
- State

The zip catalog (*Contacts / Configuration / Localization / Zips*) lists
the colony of each entry and the name of a zip shows it too
(`01000, San Ángel, Álvaro Obregón, Ciudad de México, México`), so the right
colony can be picked and searched in every zip field.

It creates a partner View related to country in order to show the fields
only if Mexico is the company country.

Cities and localities come from the SAT catalogs; the zip codes and colonies
are downloaded from the national catalog of Correos de México and refreshed
every month by a scheduled action, so the module does not ship them.
