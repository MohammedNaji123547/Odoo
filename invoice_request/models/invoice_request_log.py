from odoo import models, fields


class InvoiceRequestLog(models.Model):
    _name = 'invoice.request.log'
    _description = 'Invoice Request Workflow Log'
    _order = 'action_date asc, id asc'

    request_id = fields.Many2one(
        'invoice.request', required=True, ondelete='cascade', index=True
    )
    user_id = fields.Many2one(
        'res.users', string='Performed By',
        default=lambda self: self.env.user, readonly=True
    )
    action_date = fields.Datetime(
        string='Date & Time',
        default=fields.Datetime.now, readonly=True
    )
    label = fields.Char(string='Action', readonly=True)
    note = fields.Text(string='Note / Justification', readonly=True)
    icon = fields.Char(readonly=True)   # FontAwesome class e.g. 'fa-check'
    color = fields.Char(readonly=True)  # Hex color e.g. '#198754'
