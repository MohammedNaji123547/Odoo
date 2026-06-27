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
    # qty and unit_price reflect current approved values (updated by Change Orders)
    qty = fields.Float(string='Current Approved QTY')
    uom = fields.Char(string='Unit')
    unit_price = fields.Float(string='Current Agreed Rate')

    completed_qty = fields.Float(string='Completed QTY', default=0.0)
    remaining_qty = fields.Float(
        string='Remaining QTY',
        compute='_compute_remaining_qty',
    )
    billing_amount = fields.Float(
        string='Billing Amount',
        compute='_compute_billing_amount', store=True
    )
    contract_amount = fields.Float(
        string='Current Contract Amount',
        compute='_compute_billing_amount', store=True
    )

    # ── Change Order indicator ────────────────────────────────────────────────
    has_approved_co = fields.Boolean(
        string='Has CO',
        compute='_compute_co_info', store=True,
        help='True if this contract line has at least one approved Change Order.',
    )
    co_tag = fields.Char(
        string='Change Orders',
        compute='_compute_co_info', store=True,
        help='Approved Change Order numbers that modified this line.',
    )

    @api.depends('contract_line_id')
    def _compute_co_info(self):
        COLine = self.env['contract.change_order.line']
        for line in self:
            if not line.contract_line_id:
                line.has_approved_co = False
                line.co_tag = False
                continue
            co_lines = COLine.search([
                ('contract_line_id', '=', line.contract_line_id.id),
                ('change_order_id.state', '=', 'approved'),
            ], order='id desc')
            if co_lines:
                line.has_approved_co = True
                co_names = list(dict.fromkeys(co_lines.mapped('change_order_id.name')))
                line.co_tag = ' | '.join(co_names[:5])
            else:
                line.has_approved_co = False
                line.co_tag = False

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
            approved = self.search([
                ('contract_line_id', '=', line.contract_line_id.id),
                ('request_id.state', '=', 'finance_approved'),
                ('request_id', '!=', line.request_id.id if line.request_id.id else False),
            ])
            already_billed = sum(approved.mapped('completed_qty'))
            line.remaining_qty = line.qty - already_billed

    @api.onchange('contract_line_id')
    def _onchange_contract_line_id(self):
        """Populate line fields from contract line's current approved values."""
        if self.contract_line_id:
            cl = self.contract_line_id
            self.description = cl.description or '/'
            # Use current approved values (reflect any approved Change Orders)
            self.qty = cl.current_qty or cl.qty
            self.unit_price = cl.current_unit_price or cl.unit_price
            self.uom = cl.uom

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('contract_line_id'):
                cl = self.env['contract.line'].browse(vals['contract_line_id'])
                if not vals.get('description'):
                    vals['description'] = cl.description or '/'
                if not vals.get('unit_price'):
                    # Use current approved unit price (after Change Orders)
                    vals['unit_price'] = cl.current_unit_price or cl.unit_price
                if not vals.get('qty'):
                    # Use current approved qty (after Change Orders)
                    vals['qty'] = cl.current_qty or cl.qty
                if not vals.get('uom'):
                    vals['uom'] = cl.uom
        return super().create(vals_list)
