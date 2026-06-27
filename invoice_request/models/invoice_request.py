from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from markupsafe import Markup, escape


# ── Action metadata: (label, fa-icon, hex-color) ──────────────────────────────
_ACTION_META = {
    'submit_review':     ('Submitted for Review',             'fa-paper-plane',  '#0d6efd'),
    'submit_direct':     ('Submitted for Approval',           'fa-paper-plane',  '#0d6efd'),
    'approver_approve':  ('Approved',                         'fa-check',        '#fd7e14'),
    'chain_complete':    ('All Approvers Done — Sent to Finance', 'fa-arrow-right', '#0dcaf0'),
    'approver_reject':   ('Rejected by Approver',             'fa-times',        '#dc3545'),
    'approver_resubmit': ('Resubmitted to Requester',         'fa-undo',         '#fd7e14'),
    'manager_approve':   ('Manager Approved',                 'fa-thumbs-up',    '#0dcaf0'),
    'manager_reject':    ('Rejected by Manager',              'fa-times',        '#dc3545'),
    'manager_resubmit':  ('Resubmitted to Requester',         'fa-undo',         '#6c757d'),
    'finance_approve':   ('Finance Approved',                 'fa-check-circle', '#198754'),
    'finance_reject':    ('Rejected by Finance',              'fa-times',        '#dc3545'),
    'finance_resubmit':  ('Resubmitted to Requester',         'fa-undo',         '#6c757d'),
    'reset':             ('Reset to Draft',                   'fa-refresh',      '#6c757d'),
    'cancel':            ('Cancelled',                        'fa-ban',          '#6c757d'),
}


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
        ('in_review',         'In Review'),
        ('submitted',         'Pending Finance'),
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
        related='contract_id.analytic_account_id',
        readonly=True, store=True, tracking=True
    )
    project_id = fields.Many2one(
        'project.project', string='Project / CTR',
        related='contract_id.project_id',
        readonly=True, store=True, tracking=True
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
    current_approver_id = fields.Many2one(
        'res.users', string='Current Approver',
        compute='_compute_current_approver', store=True,
    )
    is_current_approver = fields.Boolean(
        compute='_compute_is_current_approver',
    )

    # ── Workflow Timeline ──────────────────────────────────────────────────
    log_ids = fields.One2many(
        'invoice.request.log', 'request_id', string='Workflow History'
    )
    timeline_html = fields.Html(
        compute='_compute_timeline_html', sanitize=False,
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
    @api.depends('approver_ids.status', 'state')
    def _compute_current_approver(self):
        for rec in self:
            if rec.state != 'in_review':
                rec.current_approver_id = False
                continue
            pending = rec.approver_ids.filtered(
                lambda a: a.status == 'pending'
            ).sorted('sequence')
            rec.current_approver_id = pending[0].user_id if pending else False

    @api.depends('current_approver_id', 'state')
    @api.depends_context('uid')
    def _compute_is_current_approver(self):
        uid = self.env.user.id
        for rec in self:
            rec.is_current_approver = (
                rec.state == 'in_review'
                and bool(rec.current_approver_id)
                and rec.current_approver_id.id == uid
            )

    @api.depends('line_ids.billing_amount')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.mapped('billing_amount'))

    @api.depends('log_ids', 'log_ids.label', 'log_ids.note',
                 'log_ids.user_id', 'log_ids.action_date')
    def _compute_timeline_html(self):
        for rec in self:
            logs = rec.log_ids
            if not logs:
                rec.timeline_html = Markup(
                    '<div style="padding:24px 8px; text-align:center; color:#adb5bd;">'
                    '<i class="fa fa-clock-o" style="font-size:28px; display:block; margin-bottom:8px;"></i>'
                    '<span style="font-size:12px;">No activity yet</span>'
                    '</div>'
                )
                continue

            items = Markup('')
            total = len(logs)
            for i, log in enumerate(logs):
                is_last = (i == total - 1)
                color = log.color or '#6c757d'
                icon = log.icon or 'fa-circle'
                try:
                    dt = fields.Datetime.context_timestamp(log, log.action_date)
                    date_str = dt.strftime('%d %b %Y  %H:%M')
                except Exception:
                    date_str = str(log.action_date or '-')

                user_name = escape(log.user_id.name if log.user_id else '-')
                label = escape(log.label or '')

                note_html = Markup('')
                if log.note:
                    note_html = Markup(
                        '<div style="margin-top:6px; padding:6px 8px; '
                        'background:#fff8e1; border-left:3px solid #ffc107; '
                        'border-radius:3px; font-size:11px; color:#5d4037; '
                        'word-break:break-word;">'
                        '<i class="fa fa-comment-o" style="margin-right:4px;"></i>'
                        '{}</div>'
                    ).format(escape(log.note))

                line_html = Markup('') if is_last else Markup(
                    '<div style="position:absolute; left:9px; top:22px; '
                    'bottom:-4px; width:2px; background:#e9ecef;"></div>'
                )

                items += Markup(
                    '<div style="position:relative; padding-left:34px; '
                    'padding-bottom:{pb}; min-height:38px;">'
                    '{line}'
                    '<div style="position:absolute; left:0; top:2px; width:20px; height:20px; '
                    'border-radius:50%; background:{color}; display:flex; align-items:center; '
                    'justify-content:center; box-shadow:0 0 0 3px #fff, 0 0 0 4px {color}33;">'
                    '<i class="fa {icon}" style="color:#fff; font-size:9px;"></i>'
                    '</div>'
                    '<div style="background:#fff; border:1px solid #e9ecef; border-radius:8px; '
                    'padding:8px 10px; box-shadow:0 1px 3px rgba(0,0,0,.06);">'
                    '<div style="font-weight:600; font-size:12px; color:#212529;">{label}</div>'
                    '<div style="font-size:11px; color:#6c757d; margin-top:3px;">'
                    '<i class="fa fa-user-o" style="margin-right:3px; opacity:.7;"></i>{user}'
                    '</div>'
                    '<div style="font-size:10px; color:#adb5bd; margin-top:2px;">'
                    '<i class="fa fa-clock-o" style="margin-right:3px;"></i>{date}'
                    '</div>'
                    '{note}'
                    '</div>'
                    '</div>'
                ).format(
                    pb='20px' if not is_last else '4px',
                    line=line_html,
                    color=color,
                    icon=icon,
                    label=label,
                    user=user_name,
                    date=date_str,
                    note=note_html,
                )

            rec.timeline_html = Markup(
                '<div style="padding:4px 4px 0 4px;">{}</div>'
            ).format(items)

    @api.depends('contract_id', 'state')
    def _compute_payment_summary_html(self):
        for rec in self:
            if not rec.contract_id:
                rec.payment_summary_html = Markup(
                    '<p class="text-muted">Select a contract to see payment history.</p>'
                )
                continue

            domain = [
                ('contract_id', '=', rec.contract_id.id),
                ('state', 'in', ['submitted', 'manager_approved', 'finance_approved']),
            ]
            try:
                int(rec.id)
                domain.append(('id', '!=', rec.id))
            except (TypeError, ValueError):
                pass

            related = self.search(domain, order='request_date asc')

            contract_qty = sum(rec.contract_id.line_ids.mapped('qty'))
            contract_value = sum(l.qty * l.unit_price for l in rec.contract_id.line_ids)
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
        self.line_ids = [(5, 0, 0)]

    @api.onchange('contract_id')
    def _onchange_contract_id(self):
        if self.contract_id:
            self.currency_id = self.contract_id.currency_id or self.currency_id
            lines = [(0, 0, {
                'contract_line_id': l.id,
                'description': l.description,
                # Use current approved values (reflect any approved Change Orders)
                'qty': l.current_qty or l.qty,
                'uom': l.uom,
                'unit_price': l.current_unit_price or l.unit_price,
            }) for l in self.contract_id.line_ids]
            self.line_ids = [(5, 0, 0)] + lines
        else:
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

    # ── Logging helper ─────────────────────────────────────────────────────
    def _log(self, action_code, note=None, label_override=None):
        """Create a workflow log entry on this request."""
        meta = _ACTION_META.get(action_code, ('Action', 'fa-circle', '#6c757d'))
        self.env['invoice.request.log'].create({
            'request_id': self.id,
            'label': label_override or meta[0],
            'icon': meta[1],
            'color': meta[2],
            'note': note,
        })

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
        if self.approver_ids:
            self.approver_ids.write({'status': 'pending'})
            self.write({'state': 'in_review'})
            first = self.approver_ids.sorted('sequence')[0]
            self._log('submit_review')
            self.message_post(
                body=_('Submitted for review. Pending approval from %s.') % first.user_id.name,
                partner_ids=[first.user_id.partner_id.id],
            )
        else:
            self.write({'state': 'submitted'})
            self._log('submit_direct')
            self.message_post(body=_('Invoice request submitted for Finance approval.'))

    def action_approver_approve(self):
        self.ensure_one()
        current = self.approver_ids.filtered(
            lambda a: a.user_id == self.env.user and a.status == 'pending'
        )
        if not current:
            raise ValidationError(_('You are not the current approver for this request.'))
        current[:1].write({'status': 'approved'})

        total = len(self.approver_ids)
        done = len(self.approver_ids.filtered(lambda a: a.status == 'approved'))
        step_label = _('Approved (Step %d of %d)') % (done, total)
        self._log('approver_approve', label_override=step_label)

        next_pending = self.approver_ids.filtered(
            lambda a: a.status == 'pending'
        ).sorted('sequence')

        if next_pending:
            next_a = next_pending[0]
            self.message_post(
                body=_('Approved by %s. Pending approval from %s.') % (
                    self.env.user.name, next_a.user_id.name
                ),
                partner_ids=[next_a.user_id.partner_id.id],
            )
        else:
            self.write({'state': 'submitted'})
            self._log('chain_complete')
            self.message_post(
                body=_('All approvers have approved. Forwarded to Finance for approval.')
            )

    def action_approver_reject(self):
        return self._open_wizard('approver_reject', _('Reject Invoice Request'))

    def action_approver_resubmit(self):
        return self._open_wizard('approver_resubmit', _('Resubmit to Requester'))

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
        self._log('finance_approve')
        self.message_post(body=_('Vendor bill %s created by Finance.') % bill.name)

    def action_finance_reject(self):
        return self._open_wizard('finance_reject', _('Reject Invoice Request'))

    def action_finance_resubmit(self):
        return self._open_wizard('finance_resubmit', _('Resubmit to Requester'))

    def action_cancel(self):
        return self._open_wizard('cancel', _('Cancel Invoice Request'))

    def action_reset_draft(self):
        self.write({'state': 'draft'})
        self._log('reset')
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
