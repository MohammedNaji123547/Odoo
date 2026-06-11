from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ContractContract(models.Model):
    _name = 'contract.contract'
    _description = 'Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(
        string='Contract Number', required=True, copy=False,
        readonly=True, default=lambda self: _('New'), tracking=True
    )
    title = fields.Char(string='Title', required=True, tracking=True)
    contract_type = fields.Selection([
        ('frame_msa', 'Frame Agreement / MSA'),
        ('lump_sum_ctr', 'Lump Sum CTR'),
        ('unit_rate_ctr', 'Unit Rate CTR / Call-Off'),
        ('daywork_tm', 'Daywork / T&M CTR'),
    ], string='Contract Type', required=True, tracking=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('review', 'Under Review'),
        ('rfq_prep', 'RFQ Preparation'),
        ('rfq_issued', 'RFQ Issued'),
        ('evaluation', 'Evaluation'),
        ('pending_approval', 'Pending Approval'),
        ('finalization', 'Finalization'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False)

    start_date = fields.Date(string='Start Date', tracking=True)
    end_date = fields.Date(string='End Date', tracking=True)
    value = fields.Monetary(string='Contract Value', tracking=True)
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id
    )

    # Counterparty — only set in Finalization
    partner_id = fields.Many2one('res.partner', string='Counterparty', tracking=True)

    # Unit Rate CTR fields
    contractor_id = fields.Many2one('res.partner', string='Contractor', tracking=True)
    parent_frame_id = fields.Many2one(
        'contract.contract', string='Parent Frame Agreement', tracking=True
    )

    responsible_id = fields.Many2one(
        'res.users', string='Responsible Person',
        default=lambda self: self.env.user, tracking=True
    )
    description = fields.Html(string='Description')

    # Mandatory BOQ/technical attachments
    attachment_ids = fields.Many2many(
        'ir.attachment', 'contract_doc_rel', 'contract_id', 'attachment_id',
        string='BOQ & Technical Documents'
    )
    # Signed copy
    signed_copy_ids = fields.Many2many(
        'ir.attachment', 'contract_signed_rel', 'contract_id', 'attachment_id',
        string='Signed Contract Copy'
    )

    line_ids = fields.One2many('contract.line', 'contract_id', string='Work Items')
    lines_total = fields.Monetary(
        string='Lines Total', compute='_compute_lines_total', store=True
    )
    evaluation_ids = fields.One2many('contract.evaluation', 'contract_id', string='Evaluations')
    approver_ids = fields.One2many('contract.approver', 'contract_id', string='Approvers')

    @api.depends('line_ids.subtotal')
    def _compute_lines_total(self):
        for rec in self:
            rec.lines_total = sum(rec.line_ids.mapped('subtotal'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('contract.contract') or _('New')
        return super().create(vals_list)

    @api.onchange('parent_frame_id')
    def _onchange_parent_frame_id(self):
        if self.parent_frame_id:
            self.line_ids = [(5, 0, 0)]
            self.line_ids = [(0, 0, {
                'description': l.description,
                'uom': l.uom,
                'unit_price': l.unit_price,
                'frame_line_id': l.id,
                'qty': 0.0,
            }) for l in self.parent_frame_id.line_ids]

    def _check_attachments(self):
        if not self.attachment_ids:
            raise ValidationError(_('BOQ & Technical Documents are mandatory. Please attach before submitting.'))

    def _check_approvers(self):
        if not self.approver_ids:
            raise ValidationError(_('Please add at least one approver before requesting approval.'))

    def _open_wizard(self, action_code, label):
        return {
            'type': 'ir.actions.act_window',
            'name': label,
            'res_model': 'contract.justification.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_contract_id': self.id,
                'default_action_code': action_code,
                'default_action_label': label,
            }
        }

    def _notify_approvers(self):
        for approver in self.approver_ids:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=approver.user_id.id,
                note=_('Your approval is required for contract: %s') % self.name,
            )

    # ── DRAFT
    def action_submit_review(self):
        self._check_attachments()
        self.state = 'review'

    # ── UNDER REVIEW
    def action_reviewed(self):
        if self.contract_type == 'unit_rate_ctr':
            self._check_approvers()
            self.state = 'pending_approval'
            self._notify_approvers()
        else:
            self.state = 'rfq_prep'

    def action_resubmit_requestor(self):
        return self._open_wizard('resubmit_requestor', 'Resubmit to Requestor')

    # ── RFQ PREPARATION
    def action_rfq_proceed(self):
        self.state = 'rfq_issued'

    def action_rfq_cancel(self):
        return self._open_wizard('cancel', 'Cancel Contract')

    # ── RFQ ISSUED
    def action_rfq_issued_proceed(self):
        self.state = 'evaluation'

    def action_rfq_issued_cancel(self):
        return self._open_wizard('cancel', 'Cancel Contract')

    # ── EVALUATION
    def action_proceed_approval(self):
        if not self.evaluation_ids:
            raise ValidationError(_('Please add at least one commercial evaluation before proceeding.'))
        self._check_approvers()
        self.state = 'pending_approval'
        self._notify_approvers()

    def action_evaluation_cancel(self):
        return self._open_wizard('cancel', 'Cancel Contract')

    def action_evaluation_resubmit_requestor(self):
        return self._open_wizard('resubmit_requestor', 'Resubmit to Requestor')

    # ── PENDING APPROVAL
    def action_approve(self):
        self.state = 'finalization'

    def action_reject(self):
        return self._open_wizard('cancel', 'Reject Contract')

    def action_resubmit_contracting(self):
        return self._open_wizard('resubmit_contracting', 'Resubmit to Contracting')

    def action_approval_resubmit_requester(self):
        return self._open_wizard('resubmit_requestor', 'Resubmit to Requester')

    # ── FINALIZATION
    def action_finalization_proceed(self):
        if not self.signed_copy_ids:
            raise ValidationError(_('Please attach the signed contract copy.'))
        if not self.partner_id:
            raise ValidationError(_('Please set the Counterparty.'))
        self.state = 'active'

    def action_finalization_cancel(self):
        return self._open_wizard('cancel', 'Cancel Contract')

    # ── ACTIVE
    def action_active_proceed(self):
        self.state = 'completed'