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
