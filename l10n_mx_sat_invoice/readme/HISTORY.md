## 19.0.1.0.2

- Creating a single invoice opens its form view again: the action was
  returned without views and the web client loaded the list view of the
  invoices as a form (an error with `account_move_tier_validation`:
  `Name 'validation_status' is not defined`).

## 19.0.1.0.1

- Creating an invoice from a SAT CFDI no longer fails with a missing
  `documents.document` record when Documents is installed: the context of the
  wizard (`default_document_ids`) is now really removed before creating the
  invoice and its XML attachment.
