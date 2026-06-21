from odoo import models, fields, api


class ChangeOrderLine(models.Model):
    _name = 'contract.change_order.line'
    _description = 'Change Order Line'
    _order = 'sequence'

    change_order_id = fields.Many2one(
        'contract.change_order', required=True, ondelete='cascade'
    )
    sequence = fields.Integer(default=10)

    # ── Link to original contract line ────────────────────────────────────────
    contract_line_id = fields.Many2one(
        'contract.line', string='Work Item', required=True,
        domain="[('contract_id', '=', parent.contract_id)]",
    )

    # ── Read-only: pulled from the original contract line ─────────────────────
    original_description = fields.Char(
        string='Item Work Name',
        related='contract_line_id.description', readonly=True, store=True,
    )
    original_qty = fields.Float(
        string='Original Quantity',
        related='contract_line_id.qty', readonly=True, store=True,
    )
    original_unit_price = fields.Float(
        string='Unit Price',
        related='contract_line_id.unit_price', readonly=True, store=True,
    )
    original_total = fields.Float(
        string='Original Item Total Value',
        compute='_compute_original_total', store=True,
    )

    # ── Change inputs ─────────────────────────────────────────────────────────
    change_type = fields.Selection([
        ('change_qty',       'Change Quantity'),
        ('change_price',     'Change Price'),
        ('change_qty_price', 'Change Quantity & Price'),
    ], string='Change Type', required=True)

    change_qty = fields.Float(
        string='Change Quantity',
        help='Positive = increase, negative = decrease.',
    )
    new_unit_price = fields.Float(string='New Unit Price')

    # ── Computed outputs ──────────────────────────────────────────────────────
    revised_qty = fields.Float(
        string='Revised Quantity',
        compute='_compute_change_fields', store=True,
    )
    change_value = fields.Float(
        string='Change Value',
        compute='_compute_change_fields', store=True,
    )
    change_percentage = fields.Float(
        string='Change %',
        compute='_compute_change_fields', store=True, digits=(16, 4),
    )
    cumulative_change_percentage = fields.Float(
        string='Cumulative Change %',
        compute='_compute_cumulative', store=False, digits=(16, 4),
    )

    # ── Currency (from contract) ───────────────────────────────────────────────
    currency_id = fields.Many2one(
        related='change_order_id.currency_id', readonly=True,
    )

    # ─────────────────────────────────────────────────────────────────────────
    @api.depends('original_qty', 'original_unit_price')
    def _compute_original_total(self):
        for line in self:
            line.original_total = line.original_qty * line.original_unit_price

    @api.depends('change_type', 'change_qty', 'new_unit_price',
                 'original_qty', 'original_unit_price', 'original_total',
                 'change_order_id.contract_id.value')
    def _compute_change_fields(self):
        for line in self:
            contract_value = line.change_order_id.contract_id.value or 0.0
            ctype = line.change_type

            if ctype == 'change_qty':
                # Change Value = Change Qty × Original Unit Price
                cv = line.change_qty * line.original_unit_price
                rq = line.original_qty + line.change_qty
                np = line.original_unit_price

            elif ctype == 'change_price':
                # Change Value = (New Unit Price − Original Unit Price) × Original Qty
                cv = (line.new_unit_price - line.original_unit_price) * line.original_qty
                rq = line.original_qty
                np = line.new_unit_price

            elif ctype == 'change_qty_price':
                # Revised Qty = Original Qty + Change Qty
                # Change Value = (Revised Qty × New Unit Price) − Original Item Total
                rq = line.original_qty + line.change_qty
                cv = (rq * line.new_unit_price) - line.original_total
                np = line.new_unit_price

            else:
                cv = 0.0
                rq = line.original_qty
                np = line.original_unit_price

            line.revised_qty = rq
            line.change_value = cv
            line.change_percentage = (cv / contract_value * 100) if contract_value else 0.0

    @api.depends('change_percentage', 'change_order_id.contract_id',
                 'change_order_id.state')
    def _compute_cumulative(self):
        for line in self:
            contract = line.change_order_id.contract_id
            if not contract:
                line.cumulative_change_percentage = line.change_percentage
                continue

            # Sum change % from all OTHER approved COs on the same contract
            approved_cos = self.env['contract.change_order'].search([
                ('contract_id', '=', contract.id),
                ('state', '=', 'approved'),
                ('id', '!=', line.change_order_id.id),
            ])
            prev_pct = sum(
                co_line.change_percentage
                for co in approved_cos
                for co_line in co.line_ids
            )
            line.cumulative_change_percentage = line.change_percentage + prev_pct
