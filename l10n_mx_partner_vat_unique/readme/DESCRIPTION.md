The SAT (Mexican tax authority) publishes two generic RFC that are shared by
many partners by design:

- `XAXX010101000`: sales to the general public, customers without tax id.
- `XEXX010101000`: foreign partners.

This module exempts those RFC from the unique VAT constraint of
`partner_vat_unique`, so any other VAT must still be unique while contacts
with a generic RFC can be created as many times as needed.
