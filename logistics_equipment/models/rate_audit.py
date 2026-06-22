from odoo import models, fields


class LogisticsRateAudit(models.Model):
    _name = 'logistics.rate.audit'
    _description = 'Daily Rate Customization Audit Trail'
    _order = 'create_date desc'

    request_line_id = fields.Many2one(
        'logistics.request.line', string='Request Line',
        required=True, ondelete='cascade'
    )
    request_id = fields.Many2one(
        related='request_line_id.request_id', store=True, string='Request'
    )
    equipment_id = fields.Many2one(
        related='request_line_id.equipment_id', store=True, string='Equipment'
    )
    standard_rate = fields.Float(string='Standard Rate', digits=(16, 2))
    original_rate = fields.Float(string='Previous Rate', digits=(16, 2))
    customized_rate = fields.Float(string='New Rate Applied', digits=(16, 2))
    user_id = fields.Many2one('res.users', string='Modified By', readonly=True,
                              default=lambda self: self.env.user)
    create_date = fields.Datetime(string='Date & Time', readonly=True)
