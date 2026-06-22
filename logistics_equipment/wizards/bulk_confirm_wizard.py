from odoo import models, fields, api, _
from odoo.exceptions import UserError

STANDARD_HOURS = 10.0


class BulkConfirmWizard(models.TransientModel):
    _name = 'logistics.bulk.confirm.wizard'
    _description = 'Bulk Confirm Attendance Wizard'

    attendance_ids = fields.Many2many(
        'logistics.attendance', string='Attendance Records'
    )
    record_count = fields.Integer(
        string='Records to Confirm', compute='_compute_record_count'
    )
    working_hours = fields.Float(
        string='Working Hours', default=STANDARD_HOURS,
        help='Applied to all selected records. Default = 10 (standard day).'
    )

    @api.depends('attendance_ids')
    def _compute_record_count(self):
        for rec in self:
            rec.record_count = len(rec.attendance_ids)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        if active_ids:
            res['attendance_ids'] = [(6, 0, active_ids)]
        return res

    def action_confirm(self):
        if not self.attendance_ids:
            raise UserError(_('No attendance records selected.'))
        for att in self.attendance_ids:
            att.write({
                'status':        'present',
                'actual_qty':    att.planned_qty,
                'working_hours': self.working_hours,
            })
        return {'type': 'ir.actions.act_window_close'}
