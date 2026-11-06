1. Go to **SAT > Documents** and filter the CFDIs **Without invoice**.
2. Select the CFDIs of one direction (issued or received) and choose
   **Actions > Create Invoices**, or open a CFDI and click **Create Invoice**.
3. Check the journal and the account proposed by the wizard and click
   **Create Invoices**. The account is used by the lines whose product has no
   income/expense account and by the local taxes.
4. Review the draft invoices: the chatter tells when the total differs from
   the CFDI, and the **SAT CFDI** field of the invoice links back to the
   document.

Only valid CFDIs of type I (invoice) or E (credit note) with XML and without
invoice can be imported. A missing tax (for instance a withholding not
configured) stops the import with a message telling which tax to configure.
