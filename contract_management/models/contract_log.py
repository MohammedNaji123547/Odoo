from odoo import models, fields


class ContractLog(models.Model):
    _name = 'contract.log'
    _description = 'Contract Workflow Log'
    _order = 'action_date asc, id asc'

    contract_id = fields.Many2one(
        'contract.contract', required=True, ondelete='cascade', index=True
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
    icon = fields.Char(readonly=True)
    color = fields.Char(readonly=True)
