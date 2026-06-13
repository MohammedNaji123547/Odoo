from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class InvoiceRequest(models.Model):
    _name = 'invoice.request'
    _description = 'Invoice Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(
        string='Request Number', required=True, copy=False,
        readonly=True, default=lambda self: _('New'), tracking=True
    )
    state = fields.Selection([
        ('draft',             'Draft'),
        ('submitted',         'Submitted'),
        ('manager_approved',  'Manager Approved'),
        ('finance_approved',  'Finance Approved'),
        ('rejected',          'Rejected'),
        ('cancelled',         'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False)

    # ── Requester ──────────────────────────────────────────────────────────
    requester_id = fields.Many2one(
        'res.users', string='Requester',
        default=lambda self: self.env.user,
        readonly=True, tracking=True
    )

    # ── Vendor (selected first) ────────────────────────────────────────────
    partner_id = fields.Many2one(
        'res.partner', string='Vendor / Contractor',
        required=True, tracking=True
    )

    # ── Source document (filtered by vendor) ───────────────────────────────
    contract_id = fields.Many2one(
        'contract.contract', string='Contract',
        tracking=True,
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Cost Center',
        readonly=True, tracking=True
    )
    project_id = fields.Many2one(
        'project.project', string='Project / CTR',
        readonly=True, tracking=True
    )

    # ── Currency ───────────────────────────────────────────────────────────
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id
    )

    # ── Dates ──────────────────────────────────────────────────────────────
    request_date = fields.Date(
        string='Request Date',
        default=fields.Date.today, readonly=True, tracking=True
    )
    invoice_date = fields.Date(
        string='Invoice Date', tracking=True
    )

    # ── Lines & Totals ─────────────────────────────────────────────────────
    line_ids = fields.One2many(
        'invoice.request.line', 'request_id', string='Invoice Lines'
    )
    total_amount = fields.Monetary(
        string='Total Amount',
        compute='_compute_total_amount', store=True
    )

    # ── Approvers ──────────────────────────────────────────────────────────
    approver_ids = fields.One2many(
        'invoice.request.approver', 'request_id', string='Approvers'
    )

    # ── Attachments ────────────────────────────────────────────────────────
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'invoice_request_attachment_rel',
        'request_id', 'attachment_id',
        string='Attachments'
    )

    # ── Notes ──────────────────────────────────────────────────────────────
    notes = fields.Text(string='Notes / Justification')

    # ── Linked Bill ────────────────────────────────────────────────────────
    vendor_bill_id = fields.Many2one(
        'account.move', string='Vendor Bill',
        readonly=True, copy=False, tracking=True
    )
    bill_state = fields.Selection(
        related='vendor_bill_id.payment_state',
        string='Bill Payment Status', readonly=True
    )

    # ── Approval tracking ──────────────────────────────────────────────────
    manager_id = fields.Many2one(
        'res.users', string='Approved by Manager',
        readonly=True, tracking=True
    )
    finance_user_id = fields.Many2one(
        'res.users', string='Processed by Finance',
        readonly=True, tracking=True
    )
    rejection_reason = fields.Text(
        string='Rejection / Cancellation Reason', readonly=True
    )

    # ── Computed ───────────────────────────────────────────────────────────
    @api.depends('line_ids.subtotal')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.mapped('subtotal'))

    # ── Onchange: clear contract when vendor changes ───────────────────────
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        self.contract_id = False
        self.analytic_account_id = False
        self.project_id = False
        self.line_ids = [(5, 0, 0)]

    # ── Onchange: populate everything from contract ────────────────────────
    @api.onchange('contract_id')
    def _onchange_contract_id(self):
        if self.contract_id:
            self.currency_id = self.contract_id.currency_id or self.currency_id
            self.analytic_account_id = self.contract_id.analytic_account_id
            self.project_id = self.contract_id.project_id
            lines = [(0, 0, {
                'contract_line_id': l.id,
                'description': l.description,
                'qty': l.qty,
                'uom': l.uom,
                'unit_price': l.unit_price,
            }) for l in self.contract_id.line_ids]
            self.line_ids = [(5, 0, 0)] + lines
        else:
            self.analytic_account_id = False
            self.project_id = False
            self.line_ids = [(5, 0, 0)]

    # ── CRUD ───────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('invoice.request')
                    or _('New')
                )
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if 'requester_id' in vals:
            for rec in self:
                if rec.requester_id and rec.requester_id.partner_id:
                    existing = rec.message_follower_ids.mapped('partner_id').ids
                    if rec.requester_id.partner_id.id not in existing:
                        rec.message_subscribe(
                            partner_ids=[rec.requester_id.partner_id.id]
                        )
        return res

    # ── Wizard helper ──────────────────────────────────────────────────────
    def _open_wizard(self, action_code, label):
        return {
            'type': 'ir.actions.act_window',
            'name': label,
            'res_model': 'invoice.request.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_request_id': self.id,
                'default_action_code': action_code,
                'default_action_label': label,
            }
        }

    # ── Validation ─────────────────────────────────────────────────────────
    def _check_lines(self):
        if not self.line_ids:
            raise ValidationError(
                _('Please add at least one invoice line before submitting.')
            )

    # ── Workflow actions ───────────────────────────────────────────────────
    def action_submit(self):
        self._check_lines()
        self.write({'state': 'submitted'})
        self.message_post(body=_('Invoice request submitted for manager approval.'))

    def action_manager_approve(self):
        self.write({
            'state': 'manager_approved',
            'manager_id': self.env.user.id,
        })
        self.message_post(
            body=_('Approved by manager %s. Forwarded to Finance.') % self.env.user.name
        )

    def action_manager_reject(self):
        return self._open_wizard('reject', _('Reject Invoice Request'))

    def action_finance_approve(self):
        self.ensure_one()
        expense_account = self.env['account.account'].search([
            ('account_type', '=', 'expense'),
            ('company_id', '=', self.env.company.id),
            ('deprecated', '=', False),
        ], limit=1)
        invoice_lines = []
        for line in self.line_ids:
            line_vals = {
                'name': line.description,
                'quantity': line.qty,
                'price_unit': line.unit_price,
            }
            if expense_account:
                line_vals['account_id'] = expense_account.id
            invoice_lines.append((0, 0, line_vals))
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': self.invoice_date or fields.Date.today(),
            'ref': self.name,
            'narration': self.notes or '',
            'currency_id': self.currency_id.id,
            'invoice_line_ids': invoice_lines,
        })
        self.write({
            'state': 'finance_approved',
            'finance_user_id': self.env.user.id,
            'vendor_bill_id': bill.id,
        })
        self.message_post(
            body=_('Vendor bill %s created by Finance.') % bill.name
        )

    def action_finance_reject(self):
        return self._open_wizard('reject', _('Reject Invoice Request'))

    def action_cancel(self):
        return self._open_wizard('cancel', _('Cancel Invoice Request'))

    def action_reset_draft(self):
        self.write({'state': 'draft'})
        self.message_post(body=_('Reset to Draft.'))

    def action_open_bill(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bill'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.vendor_bill_id.id,
        }
