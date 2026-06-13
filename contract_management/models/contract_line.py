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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # If unit_price was lost (readonly field not sent by client),
            # recover it from the linked frame agreement line
            if not vals.get('unit_price') and vals.get('frame_line_id'):
                frame_line = self.browse(vals['frame_line_id'])
                vals['unit_price'] = frame_line.unit_price
        return super().create(vals_list)