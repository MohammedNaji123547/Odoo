from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from markupsafe import Markup, escape


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

    # ── Source document (filtered by vendor, no frame agreements) ──────────
    contract_id = fields.Many2one(
        'contract.contract', string='Contract', tracking=True,
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
    invoice_date = fields.Date(string='Invoice Date', tracking=True)
    period_from = fields.Date(string='Period From', tracking=True)
    period_to = fields.Date(string='Period To', tracking=True)

    # ── Lines & Totals ─────────────────────────────────────────────────────
    line_ids = fields.One2many(
        'invoice.request.line', 'request_id', string='Invoice Lines'
    )
    total_amount = fields.Monetary(
        string='Total Billing Amount',
        compute='_compute_total_amount', store=True
    )

    # ── Payment Summary ────────────────────────────────────────────────────
    payment_summary_html = fields.Html(
        string='Payment Summary',
        compute='_compute_payment_summary_html',
        sanitize=False,
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
    @api.depends('line_ids.billing_amount')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.mapped('billing_amount'))

    @api.depends('contract_id', 'state')
    def _compute_payment_summary_html(self):
        for rec in self:
            if not rec.contract_id:
                rec.payment_summary_html = Markup(
                    '<p class="text-muted">Select a contract to see payment history.</p>'
                )
                continue

            # Exclude the current record when saved
            domain = [
                ('contract_id', '=', rec.contract_id.id),
                ('state', 'in', ['submitted', 'manager_approved', 'finance_approved']),
            ]
            current_id = rec.id if rec.id and not isinstance(rec.id, type(rec.id)) else False
            try:
                int(rec.id)
                domain.append(('id', '!=', rec.id))
            except (TypeError, ValueError):
                pass

            related = self.search(domain, order='request_date asc')

            # Contract totals
            contract_qty = sum(rec.contract_id.line_ids.mapped('qty'))
            contract_value = sum(l.qty * l.unit_price for l in rec.contract_id.line_ids)

            # Billed totals from related requests
            total_completed = sum(
                l.completed_qty for r in related for l in r.line_ids
            )
            total_billed = sum(r.total_amount for r in related)
            remained_qty = contract_qty - total_completed
            remained_value = contract_value - total_billed

            state_colors = {
                'submitted': 'warning',
                'manager_approved': 'info',
                'finance_approved': 'success',
            }
            state_labels = dict(self._fields['state'].selection)

            rows = Markup('')
            for r in related:
                period = Markup('{} → {}').format(
                    escape(str(r.period_from or '-')),
                    escape(str(r.period_to or '-')),
                )
                r_qty = sum(r.line_ids.mapped('completed_qty'))
                badge = state_colors.get(r.state, 'secondary')
                label = escape(state_labels.get(r.state, r.state))
                rows += Markup(
                    '<tr>'
                    '<td>{}</td><td>{}</td><td>{}</td>'
                    '<td class="text-end">{:.2f}</td>'
                    '<td class="text-end">{:.2f}</td>'
                    '<td><span class="badge bg-{}">{}</span></td>'
                    '</tr>'
                ).format(
                    escape(r.name), escape(str(r.request_date or '-')),
                    period, r_qty, r.total_amount, badge, label,
                )

            if not related:
                rows = Markup(
                    '<tr><td colspan="6" class="text-center text-muted">'
                    'No previous billing history for this contract.'
                    '</td></tr>'
                )

            rec.payment_summary_html = Markup('''
<div class="table-responsive mt-2">
<table class="table table-sm table-bordered table-striped">
  <thead class="table-dark text-center">
    <tr>
      <th>Request #</th><th>Date</th><th>Period</th>
      <th>Completed QTY</th><th>Billed Amount</th><th>Status</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
  <tfoot class="fw-bold">
    <tr class="table-warning">
      <td colspan="3">Total Billed</td>
      <td class="text-end">{cqty:.2f}</td>
      <td class="text-end">{tbilled:.2f}</td>
      <td></td>
    </tr>
    <tr class="table-secondary">
      <td colspan="3">Contract Total</td>
      <td class="text-end">{tqty:.2f}</td>
      <td class="text-end">{tval:.2f}</td>
      <td></td>
    </tr>
    <tr class="table-danger">
      <td colspan="3">Remaining</td>
      <td class="text-end">{rqty:.2f}</td>
      <td class="text-end">{rval:.2f}</td>
      <td></td>
    </tr>
  </tfoot>
</table>
</div>''').format(
                rows=rows,
                cqty=total_completed, tbilled=total_billed,
                tqty=contract_qty, tval=contract_value,
                rqty=remained_qty, rval=remained_value,
            )

    # ── Onchange ───────────────────────────────────────────────────────────
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        self.contract_id = False
        self.analytic_account_id = False
        self.project_id = False
        self.line_ids = [(5, 0, 0)]

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

    def _check_completed_qtys(self):
        for line in self.line_ids:
            if line.completed_qty > line.remaining_qty + 0.001:
                raise ValidationError(_(
                    'Completed QTY (%.2f) exceeds Remaining QTY (%.2f) for item "%s".'
                ) % (line.completed_qty, line.remaining_qty, line.description or ''))

    # ── Workflow actions ───────────────────────────────────────────────────
    def action_submit(self):
        self._check_lines()
        self._check_completed_qtys()
        self.write({'state': 'submitted'})
        self.message_post(body=_('Invoice request submitted for manager approval.'))

    def action_manager_approve(self):
        self.write({'state': 'manager_approved', 'manager_id': self.env.user.id})
        self.message_post(
            body=_('Approved by manager %s. Forwarded to Finance.') % self.env.user.name
        )

    def action_manager_reject(self):
        return self._open_wizard('reject', _('Reject Invoice Request'))

    def action_manager_resubmit(self):
        return self._open_wizard('resubmit', _('Resubmit to Requester'))

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
                'quantity': line.completed_qty or line.qty,
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
        self.message_post(body=_('Vendor bill %s created by Finance.') % bill.name)

    def action_finance_reject(self):
        return self._open_wizard('reject', _('Reject Invoice Request'))

    def action_finance_resubmit(self):
        return self._open_wizard('resubmit', _('Resubmit to Requester'))

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
