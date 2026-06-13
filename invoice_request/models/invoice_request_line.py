from odoo import models, fields, api
from odoo.exceptions import ValidationError


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
    remaining_qty = fields.Float(
        string='Remaining QTY',
        compute='_compute_remaining_qty',
    )
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

    @api.depends('contract_line_id', 'qty', 'request_id.state')
    def _compute_remaining_qty(self):
        for line in self:
            if not line.contract_line_id:
                line.remaining_qty = line.qty
                continue
            # Sum completed_qty from all finance-approved requests for this contract line
            # excluding lines from the current request
            approved = self.search([
                ('contract_line_id', '=', line.contract_line_id.id),
                ('request_id.state', '=', 'finance_approved'),
                ('request_id', '!=', line.request_id.id if line.request_id.id else False),
            ])
            already_billed = sum(approved.mapped('completed_qty'))
            line.remaining_qty = line.qty - already_billed

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Recover fields from contract line if lost (readonly fields not sent by client)
            if vals.get('contract_line_id'):
                cl = self.env['contract.line'].browse(vals['contract_line_id'])
                if not vals.get('description'):
                    vals['description'] = cl.description or '/'
                if not vals.get('unit_price'):
                    vals['unit_price'] = cl.unit_price
                if not vals.get('qty'):
                    vals['qty'] = cl.qty
                if not vals.get('uom'):
                    vals['uom'] = cl.uom
        return super().create(vals_list)
