from odoo import models, fields, api, _


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
        ('unit_rate_ctr', 'Unit Rate CTR'),
        ('daywork_tm', 'Daywork / T&M CTR'),
        ('epc', 'EPC Contract'),
    ], string='Contract Type', required=True, tracking=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('review', 'Under Review'),
        ('rfq_prep', 'RFQ Preparation'),
        ('rfq_issued', 'RFQ Issued'),
        ('evaluation', 'Evaluation'),
        ('pending_approval', 'Pending Approval'),
        ('rejected', 'Rejected'),
        ('re_tendering', 'Re-Tendering'),
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
    partner_id = fields.Many2one(
        'res.partner', string='Counterparty', required=True, tracking=True
    )
    responsible_id = fields.Many2one(
        'res.users', string='Responsible Person',
        default=lambda self: self.env.user, tracking=True
    )
    description = fields.Html(string='Description')
    line_ids = fields.One2many('contract.line', 'contract_id', string='Work Items')
    lines_total = fields.Monetary(
        string='Lines Total', compute='_compute_lines_total', store=True
    )

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

    def action_submit_review(self):
        self.state = 'review'
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            user_id=self.responsible_id.id,
            note=_('Please review contract: %s') % self.name,
        )

    def action_approve_review(self):
        self.state = 'rfq_prep'

    def action_issue_rfq(self):
        self.state = 'rfq_issued'

    def action_receive_quotations(self):
        self.state = 'evaluation'

    def action_request_approval(self):
        self.state = 'pending_approval'
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            user_id=self.responsible_id.id,
            note=_('Management approval required for: %s') % self.name,
        )

    def action_approve(self):
        self.state = 'finalization'

    def action_reject(self):
        self.state = 'rejected'

    def action_re_tender(self):
        self.state = 're_tendering'

    def action_upload_signed(self):
        self.state = 'active'

    def action_complete(self):
        self.state = 'completed'

    def action_cancel(self):
        self.state = 'cancelled'

    def action_reset_draft(self):
        self.state = 'draft'