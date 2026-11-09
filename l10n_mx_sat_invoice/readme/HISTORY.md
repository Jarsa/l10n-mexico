## 19.0.1.0.1

- Creating an invoice from a SAT CFDI no longer fails with a missing
  `documents.document` record when Documents is installed: the context of the
  wizard (`default_document_ids`) is now really removed before creating the
  invoice and its XML attachment.
