from odoo import models, fields, api


class ContractLine(models.Model):
    _name = 'contract.line'
    _description = 'Contract Line Item'

    contract_id = fields.Many2one(
        'contract.contract', required=True, ondelete='cascade'
    )
    frame_line_id = fields.Many2one('contract.line', ondelete='set null')
    sequence = fields.Integer(default=10)
    description = fields.Char(string='Description', required=True)
    qty = fields.Float(string='Quantity', default=0.0)
    uom = fields.Char(string='Unit')
    unit_price = fields.Float(string='Agreed Rate')
    subtotal = fields.Float(compute='_compute_subtotal', store=True)

    @api.depends('qty', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.qty * line.unit_price