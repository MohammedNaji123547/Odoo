from odoo import models, fields, api


class ContractLine(models.Model):
    _name = 'contract.line'
    _description = 'Contract Line Item'

    contract_id = fields.Many2one(
        'contract.contract', string='Contract',
        required=True, ondelete='cascade'
    )
    sequence = fields.Integer(string='Seq.', default=10)
    description = fields.Char(string='Description', required=True)
    qty = fields.Float(string='Quantity', default=1.0)
    uom = fields.Char(string='Unit')
    unit_price = fields.Float(string='Unit Price')
    subtotal = fields.Float(
        string='Subtotal', compute='_compute_subtotal', store=True
    )

    @api.depends('qty', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.qty * line.unit_price