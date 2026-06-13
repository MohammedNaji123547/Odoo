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
    qty = fields.Float(string='Quantity', default=1.0)
    uom = fields.Char(string='Unit of Measure')
    unit_price = fields.Float(string='Unit Price')
    subtotal = fields.Float(
        string='Subtotal', compute='_compute_subtotal', store=True
    )

    period_from = fields.Date(string='Period From')
    period_to = fields.Date(string='Period To')

    @api.depends('qty', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.qty * line.unit_price

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Recover unit_price from contract line if lost (readonly field)
            if not vals.get('unit_price') and vals.get('contract_line_id'):
                cl = self.env['contract.line'].browse(vals['contract_line_id'])
                vals['unit_price'] = cl.unit_price
        return super().create(vals_list)
