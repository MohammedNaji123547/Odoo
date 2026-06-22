from odoo import models, fields, api


class ContractLine(models.Model):
    _name = 'contract.line'
    _description = 'Contract Line Item'
    _rec_name = 'description'

    contract_id = fields.Many2one(
        'contract.contract', required=True, ondelete='cascade'
    )
    frame_line_id = fields.Many2one('contract.line', ondelete='set null')
    sequence = fields.Integer(default=10)
    description = fields.Char(string='Description', required=True)

    # ── Original values (never changed after contract activation) ─────────────
    qty = fields.Float(string='Quantity', default=0.0)
    uom = fields.Char(string='Unit')
    unit_price = fields.Float(string='Agreed Rate')
    subtotal = fields.Float(compute='_compute_subtotal', store=True)

    # ── Current approved values (updated after each approved Change Order) ─────
    current_qty = fields.Float(
        string='Current Approved Qty', default=0.0,
        help='Quantity after all approved Change Orders. Used as baseline for new COs.',
    )
    current_unit_price = fields.Float(
        string='Current Approved Unit Price', default=0.0,
        help='Unit price after all approved Change Orders. Used as baseline for new COs.',
    )
    current_total = fields.Float(
        string='Current Total',
        compute='_compute_current_total', store=True,
    )

    @api.depends('qty', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.qty * line.unit_price

    @api.depends('current_qty', 'current_unit_price')
    def _compute_current_total(self):
        for line in self:
            line.current_total = line.current_qty * line.current_unit_price

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # If unit_price was lost (readonly field not sent by client),
            # recover it from the linked frame agreement line
            if not vals.get('unit_price') and vals.get('frame_line_id'):
                frame_line = self.browse(vals['frame_line_id'])
                vals['unit_price'] = frame_line.unit_price
            # Initialise current values from original values on first creation
            if not vals.get('current_qty'):
                vals['current_qty'] = vals.get('qty', 0.0)
            if not vals.get('current_unit_price'):
                vals['current_unit_price'] = vals.get('unit_price', 0.0)
        return super().create(vals_list)