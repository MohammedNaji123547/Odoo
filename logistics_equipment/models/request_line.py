from odoo import models, fields, api, _


class LogisticsRequestLine(models.Model):
    _name = 'logistics.request.line'
    _description = 'Equipment Request Line'
    _order = 'sequence, id'

    request_id = fields.Many2one(
        'logistics.request', required=True, ondelete='cascade'
    )
    sequence = fields.Integer(default=10)

    # ── Requester fields (editable in Draft) ──────────────────────────────────
    equipment_id = fields.Many2one(
        'logistics.equipment', string='Vehicle / Equipment',
        required=True, ondelete='restrict',
        domain="[('status', '=', 'active')]"
    )
    equipment_category = fields.Char(
        string='Category', related='equipment_id.category_id.name', readonly=True
    )
    requested_qty = fields.Float(string='Requested Qty', default=1.0)
    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Cost Center'
    )
    project_id = fields.Many2one(
        'project.project', string='Project / CTR'
    )
    start_date = fields.Date(string='Start Date')
    end_date = fields.Date(string='End Date')
    required_days = fields.Integer(
        string='Required Period (Days)',
        compute='_compute_required_days', store=True
    )
    requester_remarks = fields.Char(string='Remarks')

    # ── Logistics Review fields (editable in Logistics Review) ────────────────
    availability_status = fields.Selection([
        ('available',     'Available'),
        ('not_available', 'Not Available'),
    ], string='Availability Status')
    available_qty = fields.Float(string='Available Qty')
    supplier_id = fields.Many2one(
        'res.partner', string='Assigned Contractor / Supplier',
        domain="[('supplier_rank', '>', 0)]"
    )
    customized_price = fields.Selection([
        ('no',  'No'),
        ('yes', 'Yes'),
    ], string='Customized Price', default='no')
    daily_rate = fields.Float(
        string='Daily Rate', digits=(16, 2),
        compute='_compute_daily_rate', store=True, readonly=False
    )
    logistics_remarks = fields.Char(string='Logistics Remarks')

    # ── Computed ──────────────────────────────────────────────────────────────
    planned_cost = fields.Float(
        string='Planned Cost',
        compute='_compute_planned_cost', store=True, digits=(16, 2)
    )
    currency_id = fields.Many2one(
        related='equipment_id.currency_id', readonly=True
    )

    @api.depends('start_date', 'end_date')
    def _compute_required_days(self):
        for line in self:
            if line.start_date and line.end_date and line.end_date >= line.start_date:
                line.required_days = (line.end_date - line.start_date).days + 1
            else:
                line.required_days = 0

    @api.depends('equipment_id', 'customized_price')
    def _compute_daily_rate(self):
        for line in self:
            if line.customized_price == 'yes':
                # Keep whatever the user entered — don't overwrite
                if not line.daily_rate:
                    line.daily_rate = line.equipment_id.standard_daily_rate
            else:
                line.daily_rate = line.equipment_id.standard_daily_rate if line.equipment_id else 0.0

    @api.depends('available_qty', 'requested_qty', 'daily_rate', 'required_days')
    def _compute_planned_cost(self):
        for line in self:
            qty = line.available_qty or line.requested_qty
            line.planned_cost = qty * line.daily_rate * line.required_days

    @api.onchange('equipment_id')
    def _onchange_equipment_id(self):
        if self.equipment_id:
            if self.customized_price != 'yes':
                self.daily_rate = self.equipment_id.standard_daily_rate
            if self.equipment_id.default_supplier_id and not self.supplier_id:
                self.supplier_id = self.equipment_id.default_supplier_id

    @api.onchange('customized_price')
    def _onchange_customized_price(self):
        if self.customized_price == 'no' and self.equipment_id:
            # Reset to standard rate and log audit if it was customized
            original_rate = self.daily_rate
            self.daily_rate = self.equipment_id.standard_daily_rate
            if original_rate and original_rate != self.equipment_id.standard_daily_rate:
                self._create_rate_audit(original_rate, self.equipment_id.standard_daily_rate)

    def _create_rate_audit(self, original_rate, new_rate):
        self.env['logistics.rate.audit'].create({
            'request_line_id': self._origin.id,
            'standard_rate':   self.equipment_id.standard_daily_rate,
            'original_rate':   original_rate,
            'customized_rate': new_rate,
            'user_id':         self.env.user.id,
        })

    def write(self, vals):
        """Audit trail when daily_rate changes on a customized-price line."""
        for line in self:
            if (
                'daily_rate' in vals
                and line.customized_price == 'yes'
                and vals['daily_rate'] != line.daily_rate
            ):
                self.env['logistics.rate.audit'].create({
                    'request_line_id': line.id,
                    'standard_rate':   line.equipment_id.standard_daily_rate,
                    'original_rate':   line.daily_rate,
                    'customized_rate': vals['daily_rate'],
                    'user_id':         self.env.user.id,
                })
        return super().write(vals)
