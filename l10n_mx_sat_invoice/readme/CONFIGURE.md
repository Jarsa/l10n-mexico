Configure the FIEL credentials and the download of issued and received CFDIs
in `l10n_mx_sat` (**Settings > Companies > SAT** tab).

The taxes of the company must have the **SAT Tax Type** (IVA, ISR, IEPS), the
**Factor Type** (Tasa, Cuota, Exento) and the rate of the CFDI taxes; the
Mexican chart of accounts provides them. The default sale and purchase taxes
of the company are preferred when several taxes match.

Products are matched by internal reference (``NoIdentificacion``) or name;
their income/expense account is used when set, otherwise the account chosen in
the wizard.
