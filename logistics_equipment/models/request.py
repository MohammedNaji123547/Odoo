from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class LogisticsRequest(models.Model):
    _name = 'logistics.request'
    _description = 'Equipment Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'
    _rec_name = 'name'

    # ── Identification ────────────────────────────────────────────────────────
    name = fields.Char(
        string='Request Number', required=True, copy=False,
        readonly=True, default=lambda self: _('New'), tracking=True
    )
    state = fields.Selection([
        ('draft',                   'Draft'),
        ('logistics_review',        'Logistics Review'),
        ('attendance_confirmation', 'Attendance Confirmation'),
        ('completed',               'Completed'),
        ('cancelled',               'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False)

    # ── Requester Info (auto-populated) ───────────────────────────────────────
    requester_id = fields.Many2one(
        'res.users', string='Requester',
        default=lambda self: self.env.user,
        readonly=True, tracking=True
    )
    requester_name = fields.Char(
        string='Name', compute='_compute_requester_info', store=True
    )
    department_id = fields.Many2one(
        'hr.department', string='Department',
        compute='_compute_requester_info', store=True
    )
    job_position = fields.Char(
        string='Position', compute='_compute_requester_info', store=True
    )
    requester_email = fields.Char(
        string='Email', compute='_compute_requester_info', store=True
    )

    # ── Request metadata ──────────────────────────────────────────────────────
    request_date = fields.Date(
        string='Request Date', default=fields.Date.today, readonly=True, tracking=True
    )
    notes = fields.Text(string='Notes / Justification')

    # ── Lines ─────────────────────────────────────────────────────────────────
    line_ids = fields.One2many(
        'logistics.request.line', 'request_id', string='Equipment Lines'
    )

    # ── Summary counters ──────────────────────────────────────────────────────
    total_lines = fields.Integer(
        string='Total Items', compute='_compute_summary', store=True
    )
    available_lines = fields.Integer(
        string='Available Items', compute='_compute_summary', store=True
    )
    attendance_count = fields.Integer(
        string='Attendance Records', compute='_compute_attendance_count'
    )
    pending_attendance_count = fields.Integer(
        string='Pending Attendance', compute='_compute_attendance_count'
    )

    # ─────────────────────────────────────────────────────────────────────────
    @api.depends('requester_id')
    def _compute_requester_info(self):
        for rec in self:
            user = rec.requester_id
            rec.requester_name  = user.name or ''
            rec.requester_email = user.email or ''
            employee = self.env['hr.employee'].search(
                [('user_id', '=', user.id)], limit=1
            )
            if employee:
                rec.department_id = employee.department_id
                rec.job_position  = employee.job_id.name or employee.job_title or ''
            else:
                rec.department_id = False
                rec.job_position  = ''

    @api.depends('line_ids.availability_status')
    def _compute_summary(self):
        for rec in self:
            rec.total_lines     = len(rec.line_ids)
            rec.available_lines = len(
                rec.line_ids.filtered(lambda l: l.availability_status == 'available')
            )

    def _compute_attendance_count(self):
        for rec in self:
            attendances = self.env['logistics.attendance'].search(
                [('request_id', '=', rec.id)]
            )
            rec.attendance_count         = len(attendances)
            rec.pending_attendance_count = len(
                attendances.filtered(lambda a: a.status == 'pending')
            )

    # ── CRUD ──────────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('logistics.request') or _('New')
                )
        return super().create(vals_list)

    # ── Workflow actions ───────────────────────────────────────────────────────
    def action_submit_logistics(self):
        """Draft → Logistics Review"""
        for rec in self:
            if not rec.line_ids:
                raise ValidationError(_('Please add at least one equipment line before submitting.'))
            rec.write({'state': 'logistics_review'})
            rec.message_post(body=_('Submitted for Logistics Review.'))

    def action_submit_attendance(self):
        """Logistics Review → Attendance Confirmation + generate attendance records"""
        for rec in self:
            available = rec.line_ids.filtered(
                lambda l: l.availability_status == 'available'
            )
            if not available:
                raise ValidationError(
                    _('No equipment lines are marked as Available. '
                      'Please update availability status before proceeding.')
                )
            rec._generate_attendance_records()
            rec.write({'state': 'attendance_confirmation'})
            rec.message_post(
                body=_('Moved to Attendance Confirmation. %d attendance records generated.') % (
                    rec.attendance_count
                )
            )

    def action_complete(self):
        """Mark request as Completed"""
        for rec in self:
            pending = self.env['logistics.attendance'].search([
                ('request_id', '=', rec.id),
                ('status', '=', 'pending'),
            ])
            if pending:
                raise UserError(_(
                    'There are %d pending attendance records. '
                    'Please confirm all attendance before completing, '
                    'or use Force Complete.'
                ) % len(pending))
            rec.write({'state': 'completed'})
            rec.message_post(body=_('Request marked as Completed.'))

    def action_force_complete(self):
        """Force complete even with pending attendance (Management only)"""
        self.write({'state': 'completed'})
        self.message_post(body=_('Request force-completed by %s.') % self.env.user.name)

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        self.message_post(body=_('Request cancelled.'))

    def action_reset_draft(self):
        self.write({'state': 'draft'})
        self.message_post(body=_('Reset to Draft.'))

    def action_view_attendance(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Attendance Records — %s') % self.name,
            'res_model': 'logistics.attendance',
            'view_mode': 'tree,form',
            'domain': [('request_id', '=', self.id)],
            'context': {'default_request_id': self.id},
        }

    # ── Attendance generation ─────────────────────────────────────────────────
    def _generate_attendance_records(self):
        """Auto-generate one attendance record per equipment line per day."""
        Attendance = self.env['logistics.attendance']
        for rec in self:
            # Remove any previously generated (draft) records first
            Attendance.search([
                ('request_id', '=', rec.id),
                ('status', '=', 'pending'),
            ]).unlink()

            available_lines = rec.line_ids.filtered(
                lambda l: l.availability_status == 'available'
            )
            for line in available_lines:
                if not line.start_date or not line.end_date:
                    continue
                if line.end_date < line.start_date:
                    continue
                current = line.start_date
                while current <= line.end_date:
                    Attendance.create({
                        'request_id':     rec.id,
                        'request_line_id': line.id,
                        'equipment_id':   line.equipment_id.id,
                        'supplier_id':    line.supplier_id.id or False,
                        'attendance_date': current,
                        'planned_qty':    line.available_qty or line.requested_qty,
                        'daily_rate':     line.daily_rate,
                        'status':         'pending',
                    })
                    from datetime import timedelta
                    current += timedelta(days=1)
