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
        if self.action_code == 'reject':
            request.write({
                'state': 'rejected',
                'rejection_reason': self.reason,
            })
            request.message_post(
                body=_('Rejected by %s: %s') % (self.env.user.name, self.reason)
            )
        elif self.action_code == 'cancel':
            request.write({
                'state': 'cancelled',
                'rejection_reason': self.reason,
            })
            request.message_post(
                body=_('Cancelled by %s: %s') % (self.env.user.name, self.reason)
            )
        elif self.action_code == 'resubmit':
            request.write({'state': 'draft', 'rejection_reason': self.reason})
            request.message_post(
                body=_('Resubmitted to requester by %s: %s') % (self.env.user.name, self.reason)
            )
        return {'type': 'ir.actions.act_window_close'}
