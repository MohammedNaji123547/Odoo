from odoo import models, fields


class ChangeOrderApprover(models.Model):
    _name = 'contract.change_order.approver'
    _description = 'Change Order Approver'
    _order = 'sequence'

    change_order_id = fields.Many2one(
        'contract.change_order', required=True, ondelete='cascade'
    )
    sequence = fields.Integer(default=10)
    user_id = fields.Many2one('res.users', string='Approver', required=True)
    status = fields.Selection([
        ('pending',  'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='pending')
