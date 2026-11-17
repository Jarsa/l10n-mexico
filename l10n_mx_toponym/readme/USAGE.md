1.  Access a partner record
2.  Fill the field *Location completion*
3.  Information about country, state, city, colony, colony code,
    locality and zip will be filled automatically

The zip fields search by zip code, colony, city, state or country, and show
the colony in the name of each entry (`01000, San Ángel, Álvaro Obregón,
Ciudad de México, México`).

Modules that stamp addresses (for instance a Carta Porte complement) can
call `res.partner._l10n_mx_toponym_get_address_errors()` to know whether a
Mexican address is consistent with the catalog: existing ZIP code, colony
code that belongs to the ZIP code, matching city and state, and a city
with its SAT municipality code.
