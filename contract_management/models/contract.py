from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from markupsafe import Markup, escape


# ── Action metadata: (label, fa-icon, hex-color) ──────────────────────────────
_ACTION_META = {
    'submit_review':       ('Submitted for Review',              'fa-paper-plane',  '#0d6efd'),
    'reviewed_rfq':        ('Reviewed — Sent to RFQ',            'fa-eye',          '#6f42c1'),
    'reviewed_approval':   ('Reviewed — Sent for Approval',      'fa-eye',          '#6f42c1'),
    'rfq_proceed':         ('RFQ Processed — Evaluation',        'fa-forward',      '#fd7e14'),
    'proceed_approval':    ('Submitted for Approval',            'fa-check-square', '#0d6efd'),
    'approver_approve':    ('Approved',                          'fa-check',        '#fd7e14'),
    'chain_complete':      ('All Approvers Done — Finalization', 'fa-trophy',       '#198754'),
    'approver_reject':     ('Rejected by Approver',              'fa-times',        '#dc3545'),
    'resubmit_contracting':('Resubmitted to Contracting',        'fa-undo',         '#fd7e14'),
    'resubmit_requestor':  ('Resubmitted to Requester',          'fa-undo',         '#6c757d'),
    'finalization':        ('Finalized — Contract Active',       'fa-flag',         '#198754'),
    'completed':           ('Contract Completed',                'fa-check-circle', '#198754'),
    'cancel':              ('Cancelled / Rejected',              'fa-ban',          '#dc3545'),
}


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
        ('rfq_processing', 'RFQ Processing'),
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

    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Cost Center', tracking=True
    )
    project_id = fields.Many2one(
        'project.project', string='Project / CTR', tracking=True
    )

    partner_id = fields.Many2one('res.partner', string='Counterparty', tracking=True)
    evaluated_partner_ids = fields.Many2many(
        'res.partner',
        compute='_compute_evaluated_partners',
        string='Evaluated Partners',
    )

    contractor_id = fields.Many2one('res.partner', string='Contractor', tracking=True)
    parent_frame_id = fields.Many2one(
        'contract.contract', string='Parent Frame Agreement', tracking=True
    )

    responsible_id = fields.Many2one(
        'res.users', string='Requester',
        default=lambda self: self.env.user, tracking=True
    )
    description = fields.Html(string='Description')

    attachment_ids = fields.Many2many(
        'ir.attachment', 'contract_doc_rel', 'contract_id', 'attachment_id',
        string='BOQ & Technical Documents'
    )
    signed_copy_ids = fields.Many2many(
        'ir.attachment', 'contract_signed_rel', 'contract_id', 'attachment_id',
        string='Signed Contract Copy'
    )

    line_ids = fields.One2many('contract.line', 'contract_id', string='Work Items')
    change_order_ids = fields.One2many(
        'contract.change_order', 'contract_id', string='Change Orders'
    )
    change_order_count = fields.Integer(
        compute='_compute_change_order_count'
    )
    lines_total = fields.Monetary(
        string='Lines Total', compute='_compute_lines_total', store=True
    )
    evaluation_ids = fields.One2many('contract.evaluation', 'contract_id', string='Evaluations')

    # ── Approvers ──────────────────────────────────────────────────────────
    approver_ids = fields.One2many('contract.approver', 'contract_id', string='Approvers')
    current_approver_id = fields.Many2one(
        'res.users', string='Current Approver',
        compute='_compute_current_approver', store=True,
    )
    is_current_approver = fields.Boolean(
        compute='_compute_is_current_approver',
    )

    # ── Workflow Timeline ──────────────────────────────────────────────────
    log_ids = fields.One2many('contract.log', 'contract_id', string='Workflow History')
    timeline_html = fields.Html(
        compute='_compute_timeline_html', sanitize=False,
    )

    # ── Evaluation comparison ──────────────────────────────────────────────
    eval_comparison_html = fields.Html(
        string='Evaluation Comparison',
        compute='_compute_eval_comparison_html',
        sanitize=False,
    )

    # ── Computed ───────────────────────────────────────────────────────────
    def _compute_change_order_count(self):
        for rec in self:
            rec.change_order_count = len(rec.change_order_ids)

    @api.depends('line_ids.subtotal')
    def _compute_lines_total(self):
        for rec in self:
            rec.lines_total = sum(rec.line_ids.mapped('subtotal'))

    @api.depends('evaluation_ids.partner_id')
    def _compute_evaluated_partners(self):
        for rec in self:
            rec.evaluated_partner_ids = rec.evaluation_ids.mapped('partner_id')

    @api.depends('approver_ids.status', 'state')
    def _compute_current_approver(self):
        for rec in self:
            if rec.state != 'pending_approval':
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
                rec.state == 'pending_approval'
                and bool(rec.current_approver_id)
                and rec.current_approver_id.id == uid
            )

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

    @api.depends(
        'evaluation_ids', 'evaluation_ids.partner_id', 'evaluation_ids.is_recommended',
        'evaluation_ids.total_amount', 'evaluation_ids.line_ids',
        'evaluation_ids.line_ids.description', 'evaluation_ids.line_ids.qty',
        'evaluation_ids.line_ids.uom', 'evaluation_ids.line_ids.unit_rate',
        'evaluation_ids.line_ids.total', 'evaluation_ids.line_ids.profitability',
    )
    def _compute_eval_comparison_html(self):
        for rec in self:
            evals = rec.evaluation_ids
            if not evals:
                rec.eval_comparison_html = Markup('<p class="text-muted">No evaluations added yet.</p>')
                continue

            parts = [Markup(
                '<div class="table-responsive">'
                '<table class="table table-sm table-bordered table-striped">'
            )]

            parts.append(Markup('<thead><tr><th>Description</th><th>QTY</th><th>Unit</th>'))
            for ev in evals:
                badge = (Markup(' <span class="badge text-bg-success">Recommended</span>')
                         if ev.is_recommended else Markup(''))
                parts.append(Markup('<th colspan="3" class="text-center">%s%s</th>') % (
                    escape(ev.partner_id.name or ''), badge
                ))
            parts.append(Markup('</tr>'))

            parts.append(Markup('<tr><th></th><th></th><th></th>'))
            for _ in evals:
                parts.append(Markup('<th>Rate</th><th>Total</th><th>Profit %</th>'))
            parts.append(Markup('</tr></thead><tbody>'))

            all_items = {}
            for ev in evals:
                for line in ev.line_ids:
                    key = (line.contract_line_id.id
                           if line.contract_line_id
                           else ('d_' + (line.description or '')))
                    if key not in all_items:
                        all_items[key] = {
                            'desc': line.description or '',
                            'qty': line.qty,
                            'uom': line.uom or '',
                        }

            for key, item in all_items.items():
                parts.append(Markup('<tr><td>%s</td><td>%.2f</td><td>%s</td>') % (
                    escape(item['desc']), item['qty'], escape(item['uom'])
                ))
                for ev in evals:
                    line = next((
                        l for l in ev.line_ids
                        if (l.contract_line_id.id if l.contract_line_id
                            else ('d_' + (l.description or ''))) == key
                    ), None)
                    if line:
                        css = ('text-success' if line.profitability > 0
                               else 'text-danger' if line.profitability < 0 else '')
                        parts.append(Markup('<td>%.2f</td><td>%.2f</td>'
                                            '<td class="%s">%.1f%%</td>') % (
                            line.unit_rate, line.total, escape(css), line.profitability
                        ))
                    else:
                        parts.append(Markup('<td>-</td><td>-</td><td>-</td>'))
                parts.append(Markup('</tr>'))

            parts.append(Markup('<tr class="table-warning fw-bold"><td colspan="3">TOTAL</td>'))
            for ev in evals:
                parts.append(Markup('<td colspan="2">%.2f</td><td></td>') % ev.total_amount)
            parts.append(Markup('</tr></tbody></table></div>'))

            rec.eval_comparison_html = Markup('').join(parts)

    # ── CRUD ───────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if (vals.get('contract_type') == 'unit_rate_ctr'
                    and vals.get('parent_frame_id')
                    and not vals.get('partner_id')):
                frame = self.env['contract.contract'].browse(vals['parent_frame_id'])
                if frame.partner_id:
                    vals['partner_id'] = frame.partner_id.id
            if vals.get('name', _('New')) == _('New'):
                ctype = vals.get('contract_type', '')
                seq_map = {
                    'frame_msa': 'contract.frame_msa',
                    'lump_sum_ctr': 'contract.lump_sum_ctr',
                    'daywork_tm': 'contract.daywork_tm',
                }
                if ctype in seq_map:
                    vals['name'] = (
                        self.env['ir.sequence'].next_by_code(seq_map[ctype]) or _('New')
                    )
                elif ctype == 'unit_rate_ctr':
                    parent_id = vals.get('parent_frame_id')
                    if parent_id:
                        parent = self.env['contract.contract'].browse(parent_id)
                        count = self.search_count([
                            ('contract_type', '=', 'unit_rate_ctr'),
                            ('parent_frame_id', '=', parent_id),
                        ])
                        vals['name'] = f"CTR-{parent.name}-{count + 1:02d}"
                    else:
                        vals['name'] = _('New')
        return super().create(vals_list)

    def write(self, vals):
        if 'parent_frame_id' in vals and vals.get('parent_frame_id'):
            frame = self.env['contract.contract'].browse(vals['parent_frame_id'])
            if frame.partner_id:
                for rec in self:
                    if rec.contract_type == 'unit_rate_ctr':
                        vals = dict(vals, partner_id=frame.partner_id.id)
                        break
        res = super().write(vals)
        if 'responsible_id' in vals:
            for rec in self:
                if rec.responsible_id and rec.responsible_id.partner_id:
                    existing = rec.message_follower_ids.mapped('partner_id').ids
                    if rec.responsible_id.partner_id.id not in existing:
                        rec.message_subscribe(partner_ids=[rec.responsible_id.partner_id.id])
        return res

    # ── Onchange ───────────────────────────────────────────────────────────
    @api.onchange('parent_frame_id')
    def _onchange_parent_frame_id(self):
        if self.parent_frame_id:
            self.partner_id = self.parent_frame_id.partner_id
            lines = [(0, 0, {
                'description': l.description,
                'uom': l.uom,
                'unit_price': l.unit_price,
                'frame_line_id': l.id,
                'qty': 0.0,
            }) for l in self.parent_frame_id.line_ids]
            self.line_ids = [(5, 0, 0)] + lines
        else:
            self.partner_id = False
            self.line_ids = [(5, 0, 0)]

    @api.onchange('contractor_id')
    def _onchange_contractor_id(self):
        self.parent_frame_id = False
        self.line_ids = [(5, 0, 0)]

    # ── Validation ─────────────────────────────────────────────────────────
    def _check_attachments(self):
        if not self.attachment_ids:
            raise ValidationError(_('BOQ & Technical Documents are mandatory. Please attach before submitting.'))

    def _check_approvers(self):
        if not self.approver_ids:
            raise ValidationError(_('Please add at least one approver before proceeding to approval.'))

    # ── Logging helper ─────────────────────────────────────────────────────
    def _log(self, action_code, note=None, label_override=None):
        meta = _ACTION_META.get(action_code, ('Action', 'fa-circle', '#6c757d'))
        self.env['contract.log'].create({
            'contract_id': self.id,
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
            'res_model': 'contract.justification.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_contract_id': self.id,
                'default_action_code': action_code,
                'default_action_label': label,
            }
        }

    # ── Workflow actions ───────────────────────────────────────────────────
    def action_submit_review(self):
        self._check_attachments()
        self.state = 'review'
        self._log('submit_review')
        self.message_post(body=_('Submitted for review.'))

    def action_reviewed(self):
        if self.contract_type == 'unit_rate_ctr':
            self._check_approvers()
            self.approver_ids.write({'status': 'pending'})
            self.state = 'pending_approval'
            first = self.approver_ids.sorted('sequence')[0]
            self._log('reviewed_approval')
            self._notify_approvers()
            self.message_post(
                body=_('Reviewed. Pending approval from %s.') % first.user_id.name,
                partner_ids=[first.user_id.partner_id.id],
            )
        else:
            self.state = 'rfq_processing'
            self._log('reviewed_rfq')
            self.message_post(body=_('Reviewed. Proceeding to RFQ.'))

    def action_resubmit_requestor(self):
        return self._open_wizard('resubmit_requestor', 'Resubmit to Requestor')

    def action_rfq_proceed(self):
        self.state = 'evaluation'
        self._log('rfq_proceed')
        self.message_post(body=_('RFQ processed. Proceeding to Evaluation.'))

    def action_rfq_cancel(self):
        return self._open_wizard('cancel', 'Cancel Contract')

    def _notify_approvers(self):
        """Schedule a To-Do activity for each approver (used by tests)."""
        for approver in self.approver_ids:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=approver.user_id.id,
                note=_('Your approval is required for contract: %s') % self.name,
            )

    def action_proceed_approval(self):
        if not self.evaluation_ids:
            raise ValidationError(_('Please add at least one commercial evaluation before proceeding.'))
        self._check_approvers()
        self.approver_ids.write({'status': 'pending'})
        self.state = 'pending_approval'
        first = self.approver_ids.sorted('sequence')[0]
        self._log('proceed_approval')
        self._notify_approvers()
        self.message_post(
            body=_('Submitted for approval. Pending approval from %s.') % first.user_id.name,
            partner_ids=[first.user_id.partner_id.id],
        )

    def action_evaluation_cancel(self):
        return self._open_wizard('cancel', 'Cancel Contract')

    def action_evaluation_resubmit_requestor(self):
        return self._open_wizard('resubmit_requestor', 'Resubmit to Requestor')

    # ── Sequential approver actions ────────────────────────────────────────
    def action_approver_approve(self):
        self.ensure_one()
        current = self.approver_ids.filtered(
            lambda a: a.user_id == self.env.user and a.status == 'pending'
        )
        if not current:
            raise ValidationError(_('You are not the current approver for this contract.'))
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
            self.state = 'finalization'
            self._log('chain_complete')
            self.message_post(
                body=_('All approvers have approved. Contract moved to Finalization.')
            )

    def action_approver_reject(self):
        return self._open_wizard('approver_reject', _('Reject Contract'))

    def action_approver_resubmit_contracting(self):
        return self._open_wizard('resubmit_contracting', _('Resubmit to Contracting'))

    def action_approver_resubmit_requester(self):
        return self._open_wizard('resubmit_requestor', _('Resubmit to Requester'))

    # ── Backward-compatible shims (used by tests) ──────────────────────────
    def action_approve(self):
        """Approve as the first pending approver (no current-user check — for tests)."""
        for rec in self:
            pending = rec.approver_ids.filtered(
                lambda a: a.status == 'pending'
            ).sorted('sequence')
            if pending:
                pending[:1].write({'status': 'approved'})
                total = len(rec.approver_ids)
                done = len(rec.approver_ids.filtered(lambda a: a.status == 'approved'))
                rec._log('approver_approve',
                         label_override=_('Approved (Step %d of %d)') % (done, total))
                still_pending = rec.approver_ids.filtered(lambda a: a.status == 'pending')
                if not still_pending:
                    rec.state = 'finalization'
                    rec._log('chain_complete')
            else:
                rec.state = 'finalization'
                rec._log('chain_complete')

    def action_reject(self):
        """Backward-compatible alias for approver reject wizard."""
        return self._open_wizard('approver_reject', _('Reject Contract'))

    # ── Finalization & beyond ──────────────────────────────────────────────
    def action_finalization_proceed(self):
        if not self.signed_copy_ids:
            raise ValidationError(_('Please attach the signed contract copy.'))
        if not self.partner_id:
            raise ValidationError(_('Please set the Counterparty.'))
        self.state = 'active'
        self._log('finalization')
        self.message_post(body=_('Contract finalized and is now Active.'))

    def action_finalization_cancel(self):
        return self._open_wizard('cancel', 'Cancel Contract')

    def action_active_proceed(self):
        self.state = 'completed'
        self._log('completed')
        self.message_post(body=_('Contract marked as Completed.'))
