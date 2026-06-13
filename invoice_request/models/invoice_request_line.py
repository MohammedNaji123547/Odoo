from odoo import models, fields, api


class InvoiceRequestLine(models.Model):
    _name = 'invoice.request.line'
    _description = 'Invoice Request Line'
    _order = 'sequence, id'

    request_id = fields.Many2one(
        'invoice.request', string='Invoice Request',
        required=True, ondelete='cascade'
    )
    sequence = fields.Integer(default=10)
    contract_line_id = fields.Many2one(
        'contract.line', string='Contract Item', ondelete='set null'
    )

    description = fields.Char(string='Description of Work / Service', required=True)
    qty = fields.Float(string='Contract QTY')
    uom = fields.Char(string='Unit')
    unit_price = fields.Float(string='Agreed Rate')

    completed_qty = fields.Float(string='Completed QTY', default=0.0)
    billing_amount = fields.Float(
        string='Billing Amount',
        compute='_compute_billing_amount', store=True
    )
    # Contract total for this line (qty × unit_price) — reference only
    contract_amount = fields.Float(
        string='Contract Amount',
        compute='_compute_billing_amount', store=True
    )

    @api.depends('qty', 'completed_qty', 'unit_price')
    def _compute_billing_amount(self):
        for line in self:
            line.billing_amount = line.completed_qty * line.unit_price
            line.contract_amount = line.qty * line.unit_price

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Recover unit_price from contract line if lost (readonly field)
            if not vals.get('unit_price') and vals.get('contract_line_id'):
                cl = self.env['contract.line'].browse(vals['contract_line_id'])
                vals['unit_price'] = cl.unit_price
        return super().create(vals_list)
