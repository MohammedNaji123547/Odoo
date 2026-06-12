from odoo import models, fields, _
from markupsafe import Markup, escape


class ContractJustificationWizard(models.TransientModel):
    _name = 'contract.justification.wizard'
    _description = 'Contract Action Justification'

    contract_id = fields.Many2one('contract.contract', required=True)
    action_code = fields.Char(required=True)
    action_label = fields.Char(string='Action')
    justification = fields.Text(string='Justification / Reason', required=True)

    def action_confirm(self):
        contract = self.contract_id
        contract.message_post(
            body=Markup('<b>Action: %s</b><br/><b>Reason:</b> %s') % (
                escape(self.action_label or ''),
                escape(self.justification or ''),
            ),
            message_type='comment',
        )
        
        if self.action_code == 'cancel':
            contract.state = 'cancelled'
        elif self.action_code == 'resubmit_requestor':
            contract.state = 'draft'
        elif self.action_code == 'resubmit_contracting':
            contract.state = 'evaluation'
        return {'type': 'ir.actions.act_window_close'}