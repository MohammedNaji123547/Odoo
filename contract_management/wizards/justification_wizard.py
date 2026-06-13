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
        code = self.action_code
        reason = self.justification

        contract.message_post(
            body=Markup('<b>Action: %s</b><br/><b>Reason:</b> %s') % (
                escape(self.action_label or ''),
                escape(reason or ''),
            ),
            message_type='comment',
        )

        if code == 'cancel':
            contract.state = 'cancelled'
            contract._log('cancel', note=reason)

        elif code == 'resubmit_requestor':
            contract.state = 'draft'
            contract.approver_ids.write({'status': 'pending'})
            contract._log('resubmit_requestor', note=reason)

        elif code == 'resubmit_contracting':
            contract.state = 'evaluation'
            contract.approver_ids.write({'status': 'pending'})
            contract._log('resubmit_contracting', note=reason)

        elif code == 'approver_reject':
            current = contract.approver_ids.filtered(
                lambda a: a.user_id == self.env.user and a.status == 'pending'
            )
            if current:
                current[:1].write({'status': 'rejected'})
            contract.state = 'cancelled'
            contract._log('approver_reject', note=reason)

        return {'type': 'ir.actions.act_window_close'}
