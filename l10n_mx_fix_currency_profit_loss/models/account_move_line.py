# Copyright 2025 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move.line"

    def _prepare_exchange_difference_move_vals(
        self, amounts_list, company=None, exchange_date=None, **kwargs
    ):
        res = super()._prepare_exchange_difference_move_vals(
            amounts_list, company, exchange_date, **kwargs
        )
        tax_account_ids = (
            self.env["account.tax"]
            .search([("tax_exigibility", "=", "on_payment")])
            .mapped("cash_basis_transition_account_id")
            .ids
        )
        if (
            not res["to_reconcile"]
            or res["to_reconcile"][0][0].account_id.id not in tax_account_ids
        ):
            return res
        income_account_id = self.company_id.income_currency_exchange_account_id.id
        expense_account_id = self.company_id.expense_currency_exchange_account_id.id
        for line in res.get("move_values", {}).get("line_ids", []):
            if line[2].get("account_id") == income_account_id:
                line[2]["account_id"] = expense_account_id
            elif line[2].get("account_id") == expense_account_id:
                line[2]["account_id"] = income_account_id
        return res
