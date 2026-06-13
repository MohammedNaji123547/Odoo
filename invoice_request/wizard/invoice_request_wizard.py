from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class InvoiceRequestWizard(models.TransientModel):
    _name = 'invoice.request.wizard'
    _description = 'Invoice Request Action Wizard'

    request_id = fields.Many2one('invoice.request', required=True)
    action_code = fields.Char()
    action_label = fields.Char()
    reason = fields.Text(string='Reason', required=True)

    def action_confirm(self):
        self.ensure_one()
        if not self.reason:
            raise ValidationError(_('Please provide a reason.'))

        request = self.request_id
        code = self.action_code

        if code == 'reject':
            # Generic reject (manager or finance based on current state)
            log_code = 'manager_reject' if request.state == 'submitted' else 'finance_reject'
            request.write({'state': 'rejected', 'rejection_reason': self.reason})
            request._log(log_code, note=self.reason)
            request.message_post(
                body=_('Rejected by %s: %s') % (self.env.user.name, self.reason)
            )

        elif code == 'manager_reject':
            request.write({'state': 'rejected', 'rejection_reason': self.reason})
            request._log('manager_reject', note=self.reason)
            request.message_post(
                body=_('Rejected by manager %s: %s') % (self.env.user.name, self.reason)
            )

        elif code == 'finance_reject':
            request.write({'state': 'rejected', 'rejection_reason': self.reason})
            request._log('finance_reject', note=self.reason)
            request.message_post(
                body=_('Rejected by Finance %s: %s') % (self.env.user.name, self.reason)
            )

        elif code == 'cancel':
            request.write({'state': 'cancelled', 'rejection_reason': self.reason})
            request._log('cancel', note=self.reason)
            request.message_post(
                body=_('Cancelled by %s: %s') % (self.env.user.name, self.reason)
            )

        elif code in ('resubmit', 'manager_resubmit'):
            request.write({'state': 'draft', 'rejection_reason': self.reason})
            request._log('manager_resubmit', note=self.reason)
            request.message_post(
                body=_('Resubmitted to requester by %s: %s') % (self.env.user.name, self.reason)
            )

        elif code == 'finance_resubmit':
            request.write({'state': 'draft', 'rejection_reason': self.reason})
            request._log('finance_resubmit', note=self.reason)
            request.message_post(
                body=_('Resubmitted to requester by Finance %s: %s') % (self.env.user.name, self.reason)
            )

        elif code == 'approver_reject':
            current = request.approver_ids.filtered(
                lambda a: a.user_id == self.env.user and a.status == 'pending'
            )
            if current:
                current[:1].write({'status': 'rejected'})
            request.write({'state': 'rejected', 'rejection_reason': self.reason})
            request._log('approver_reject', note=self.reason)
            request.message_post(
                body=_('Rejected by approver %s: %s') % (self.env.user.name, self.reason)
            )

        elif code == 'approver_resubmit':
            request.approver_ids.write({'status': 'pending'})
            request.write({'state': 'draft', 'rejection_reason': self.reason})
            request._log('approver_resubmit', note=self.reason)
            request.message_post(
                body=_('Resubmitted to requester by approver %s: %s') % (self.env.user.name, self.reason)
            )

        return {'type': 'ir.actions.act_window_close'}
