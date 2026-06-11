from odoo import models, fields


class ContractApprover(models.Model):
    _name = 'contract.approver'
    _description = 'Contract Approver'
    _order = 'sequence'

    contract_id = fields.Many2one('contract.contract', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    user_id = fields.Many2one('res.users', string='Approver', required=True)
    status = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='pending')