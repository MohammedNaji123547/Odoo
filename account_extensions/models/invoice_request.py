from odoo import models


class InvoiceRequest(models.Model):
    _inherit = 'invoice.request'

    def action_finance_approve(self):
        res = super().action_finance_approve()
        for rec in self:
            if not rec.vendor_bill_id:
                continue
            vals = {'invoice_request_id': rec.id}
            if rec.contract_id:
                vals['contract_id'] = rec.contract_id.id
            if rec.period_from:
                vals['period_from'] = rec.period_from
            if rec.period_to:
                vals['period_to'] = rec.period_to
            if rec.analytic_account_id:
                vals['cost_center_id'] = rec.analytic_account_id.id
            rec.vendor_bill_id.write(vals)
        return res
