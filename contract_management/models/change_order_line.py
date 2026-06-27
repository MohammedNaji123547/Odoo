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

    # ── Original values (read-only, for audit & reference only) ──────────────
    original_description = fields.Char(
        string='Work Item Name',
        related='contract_line_id.description', readonly=True, store=True,
    )
    original_qty = fields.Float(
        string='Original Qty',
        related='contract_line_id.qty', readonly=True, store=True,
    )
    original_unit_price = fields.Float(
        string='Original Unit Price',
        related='contract_line_id.unit_price', readonly=True, store=True,
    )
    original_total = fields.Float(
        string='Original Total',
        compute='_compute_original_total', store=True,
    )

    # ── Baseline values (current approved values at time CO was created) ──────
    # These are the basis for all calculations — NOT the original values.
    baseline_qty = fields.Float(
        string='Current Approved Qty',
        readonly=True, store=True,
        help='Current approved quantity at time this CO line was created.',
    )
    baseline_unit_price = fields.Float(
        string='Current Approved Unit Price',
        readonly=True, store=True,
        help='Current approved unit price at time this CO line was created.',
    )
    baseline_total = fields.Float(
        string='Current Total',
        compute='_compute_baseline_total', store=True,
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

    @api.depends('baseline_qty', 'baseline_unit_price')
    def _compute_baseline_total(self):
        for line in self:
            line.baseline_total = line.baseline_qty * line.baseline_unit_price

    @api.onchange('contract_line_id')
    def _onchange_contract_line_id(self):
        """Populate baseline values from the contract line's current approved values."""
        if self.contract_line_id:
            cl = self.contract_line_id
            # Use current approved values as baseline (fall back to original if not yet set)
            self.baseline_qty = cl.current_qty or cl.qty
            self.baseline_unit_price = cl.current_unit_price or cl.unit_price

    @api.depends('change_type', 'change_qty', 'new_unit_price',
                 'baseline_qty', 'baseline_unit_price', 'baseline_total',
                 'change_order_id.contract_id.lines_total')
    def _compute_change_fields(self):
        for line in self:
            contract = line.change_order_id.contract_id
            contract_value = contract.lines_total or 0.0
            ctype = line.change_type

            # Use baseline (current approved) values — never original values
            bq = line.baseline_qty or line.original_qty   # safety fallback for legacy records
            bp = line.baseline_unit_price or line.original_unit_price

            if ctype == 'change_qty':
                # Change Value = Change Qty × Current Approved Unit Price
                cv = line.change_qty * bp
                rq = bq + line.change_qty

            elif ctype == 'change_price':
                # Change Value = (New Unit Price − Current Approved Unit Price) × Current Approved Qty
                cv = (line.new_unit_price - bp) * bq
                rq = bq

            elif ctype == 'change_qty_price':
                # Revised Qty = Current Approved Qty + Change Qty
                # Change Value = (Revised Qty × New Unit Price) − Current Total
                rq = bq + line.change_qty
                cv = (rq * line.new_unit_price) - (bq * bp)

            else:
                cv = 0.0
                rq = bq

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

            co_id = line.change_order_id._origin.id
            domain = [
                ('contract_id', '=', contract.id),
                ('state', '=', 'approved'),
            ]
            if co_id:
                domain.append(('id', '!=', co_id))
            approved_cos = self.env['contract.change_order'].search(domain)
            prev_pct = sum(
                co_line.change_percentage
                for co in approved_cos
                for co_line in co.line_ids
            )
            line.cumulative_change_percentage = line.change_percentage + prev_pct
