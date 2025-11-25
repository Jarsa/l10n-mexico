from odoo import models


class AccountPartialReconcile(models.Model):
    _inherit = "account.partial.reconcile"

    def _collect_tax_cash_basis_values(self):
        res = super()._collect_tax_cash_basis_values()
        if not res:
            return res
        if len(res) == 1:
            return res
        if self.debit_move_id.journal_id.type == self.credit_move_id.journal_id.type:
            if self.debit_move_id.date >= self.credit_move_id.date:
                res[self.credit_move_id.move_id.id]["partials"][0][
                    "payment_rate"
                ] = res[self.debit_move_id.move_id.id]["partials"][0]["payment_rate"]
            else:
                res[self.debit_move_id.move_id.id]["partials"][0]["payment_rate"] = res[
                    self.credit_move_id.move_id.id
                ]["partials"][0]["payment_rate"]
        return res
