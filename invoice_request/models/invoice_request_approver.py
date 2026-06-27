from odoo import models, fields


class InvoiceRequestApprover(models.Model):
    _name = 'invoice.request.approver'
    _description = 'Invoice Request Approver'
    _order = 'sequence, id'

    request_id = fields.Many2one(
        'invoice.request', required=True, ondelete='cascade'
    )
    sequence = fields.Integer(default=10)
    user_id = fields.Many2one('res.users', string='Approver', required=True)
    status = fields.Selection([
        ('pending',  'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status', default='pending')
