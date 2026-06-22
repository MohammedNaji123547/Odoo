from odoo import models, fields, api, _

STANDARD_HOURS = 10.0  # Standard working hours per day


class LogisticsAttendance(models.Model):
    _name = 'logistics.attendance'
    _description = 'Equipment Daily Attendance'
    _order = 'attendance_date, equipment_id'
    _rec_name = 'display_name'

    # ── Links ─────────────────────────────────────────────────────────────────
    request_id = fields.Many2one(
        'logistics.request', string='Request', required=True,
        ondelete='cascade', index=True
    )
    request_line_id = fields.Many2one(
        'logistics.request.line', string='Request Line', ondelete='cascade'
    )
    equipment_id = fields.Many2one(
        'logistics.equipment', string='Equipment', required=True, ondelete='restrict'
    )
    supplier_id = fields.Many2one(
        'res.partner', string='Supplier'
    )

    # ── Plan (set at generation time) ─────────────────────────────────────────
    attendance_date = fields.Date(string='Date', required=True)
    planned_qty = fields.Float(string='Planned Qty', digits=(16, 2))
    daily_rate = fields.Float(string='Daily Rate', digits=(16, 2))

    # ── Actual (filled by Logistics Team) ────────────────────────────────────
    status = fields.Selection([
        ('pending', 'Pending'),
        ('present', 'Present'),
        ('absent',  'Absent'),
        ('partial', 'Partial'),
    ], string='Attendance Status', default='pending', required=True)
    actual_qty = fields.Float(string='Actual Qty Attended', digits=(16, 2))
    working_hours = fields.Float(string='Working Hours', digits=(16, 2))
    remarks = fields.Char(string='Remarks')

    # ── Computed ──────────────────────────────────────────────────────────────
    hourly_rate = fields.Float(
        string='Hourly Rate', compute='_compute_costs', store=True, digits=(16, 2)
    )
    overtime_hours = fields.Float(
        string='Overtime Hours', compute='_compute_costs', store=True, digits=(16, 2)
    )
    overtime_cost = fields.Float(
        string='Overtime Cost', compute='_compute_costs', store=True, digits=(16, 2)
    )
    daily_cost = fields.Float(
        string='Daily Cost', compute='_compute_costs', store=True, digits=(16, 2)
    )
    total_cost = fields.Float(
        string='Total Cost', compute='_compute_costs', store=True, digits=(16, 2)
    )
    currency_id = fields.Many2one(
        related='equipment_id.currency_id', readonly=True
    )
    equipment_category_id = fields.Many2one(
        related='equipment_id.category_id', string='Category',
        store=True, readonly=True
    )
    attendance_rate = fields.Float(
        string='Attendance Rate %',
        compute='_compute_attendance_rate', store=True,
        digits=(5, 1), group_operator='avg',
    )
    display_name = fields.Char(
        compute='_compute_display_name', store=True
    )

    @api.depends('actual_qty', 'planned_qty', 'status')
    def _compute_attendance_rate(self):
        for rec in self:
            if rec.status == 'absent' or not rec.planned_qty:
                rec.attendance_rate = 0.0
            else:
                rec.attendance_rate = min(100.0, (rec.actual_qty / rec.planned_qty) * 100.0)

    @api.depends('equipment_id', 'attendance_date')
    def _compute_display_name(self):
        for rec in self:
            eq = rec.equipment_id.name or '?'
            dt = str(rec.attendance_date) if rec.attendance_date else '?'
            rec.display_name = f"{eq} / {dt}"

    @api.depends('daily_rate', 'working_hours', 'actual_qty', 'status')
    def _compute_costs(self):
        for rec in self:
            if rec.status == 'absent':
                rec.hourly_rate   = 0.0
                rec.overtime_hours = 0.0
                rec.overtime_cost  = 0.0
                rec.daily_cost     = 0.0
                rec.total_cost     = 0.0
                continue

            rate = rec.daily_rate or 0.0
            hrs  = rec.working_hours or 0.0
            qty  = rec.actual_qty if rec.status in ('present', 'partial') else 0.0

            hourly        = rate / STANDARD_HOURS if STANDARD_HOURS else 0.0
            ot_hours      = max(0.0, hrs - STANDARD_HOURS)
            ot_cost       = ot_hours * hourly
            d_cost        = rate + ot_cost   # per unit
            total         = d_cost * qty

            rec.hourly_rate    = hourly
            rec.overtime_hours = ot_hours
            rec.overtime_cost  = ot_cost
            rec.daily_cost     = d_cost
            rec.total_cost     = total

    # ── Confirm action (single record) ────────────────────────────────────────
    def action_confirm_present(self):
        """Quick confirm: Present, actual = planned, hours = 10"""
        for rec in self:
            rec.write({
                'status':       'present',
                'actual_qty':   rec.planned_qty,
                'working_hours': STANDARD_HOURS,
            })
