1. Open a confirmed purchase order and click **Bill from SAT**.
2. The **SAT CFDIs** tab lists the received CFDIs of the vendor that are
   pending to bill: folio, date, issuer, total, currency and SAT status. Only
   CFDIs in the currency of the order, not cancelled and not linked to another
   bill are proposed. When exactly one CFDI matches the orders total it comes
   pre-selected.
3. Tick the CFDI that corresponds to the order. The **Concepts** tab shows
   one line per concept of the CFDI (vendor code, description, SAT product
   code, quantity, SAT unit, unit price, amount, discount and taxes) and
   proposes the purchase order line it corresponds to, looking for, in this
   order: the `NoIdentificacion` of the concept equal to the internal
   reference of the product or to its vendor code, the description equal to
   the one of the line or of the product (ignoring case and accents), and a
   single line with the same unit price. When several lines match, the one of
   the oldest order with a pending quantity wins.
4. When the CFDI covers several purchase orders, add them in **Purchase
   Orders** (only confirmed orders of the same vendor and currency with
   something to bill are offered); the concepts without line are proposed
   again on the new orders.
5. Review the mapping: change the **Purchase Order Line** of a concept or its
   **Quantity to Bill** (the CFDI quantity, converted to the unit of the order
   line when the SAT unit code is known). The quantities to bill cannot
   exceed the pending quantity of each order line. A concept without order
   line blocks the creation of the bill unless **Allow concepts without
   order** is ticked and a product is selected on it; it is then billed as a
   free line.
6. Click **Create Bill**. The vendor bill is created in draft with one line
   per concept (product, taxes and analytic distribution of the order line;
   quantity, unit price and discount of the CFDI), the orders as origin, the
   CFDI serie and folio as reference, its date as bill date and the XML
   attached. A warning is shown in the wizard when the amount to bill differs
   from the CFDI subtotal, and a note is posted in the bill when its total
   differs from the CFDI total.

The **Not billed** filter of **SAT > Documents** lists the received CFDIs that
still have no vendor bill.
