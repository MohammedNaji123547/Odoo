from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ChangeOrder(models.Model):
    _name = 'contract.change_order'
    _description = 'Contract Change Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, name desc'

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(
        string='Change Order', required=True, copy=False, readonly=True,
        default='New',
    )
    date = fields.Date(
        string='Date', default=fields.Date.today, tracking=True,
    )
    state = fields.Selection([
        ('draft',            'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('approved',         'Approved'),
        ('rejected',         'Rejected'),
    ], default='draft', string='Status', tracking=True)

    # ── Contract link ─────────────────────────────────────────────────────────
    partner_id = fields.Many2one(
        'res.partner', string='Contractor', tracking=True,
    )
    contract_id = fields.Many2one(
        'contract.contract', string='Contract', required=True,
        domain="[('contract_type', 'in', ['lump_sum_ctr', 'unit_rate_ctr']), "
               "('state', 'in', ['active', 'completed']), "
               "('partner_id', '=', partner_id)]",
        tracking=True,
    )
    contract_type = fields.Selection(
        related='contract_id.contract_type', readonly=True, store=True,
    )
    original_contract_value = fields.Monetary(
        string='Original Contract Value',
        compute='_compute_original_contract_value', store=True,
    )

    @api.depends('contract_id.lines_total')
    def _compute_original_contract_value(self):
        for co in self:
            co.original_contract_value = co.contract_id.lines_total or 0.0
    currency_id = fields.Many2one(
        related='contract_id.currency_id', readonly=True,
    )

    # ── Reason / justification ────────────────────────────────────────────────
    reason = fields.Text(string='Reason / Justification', tracking=True)

    # ── Lines & approvers ────────────────────────────────────────────────────
    line_ids = fields.One2many(
        'contract.change_order.line', 'change_order_id', string='Change Items',
    )
    approver_ids = fields.One2many(
        'contract.change_order.approver', 'change_order_id', string='Approvers',
    )
    attachment_ids = fields.Many2many(
        'ir.attachment', string='Supporting Documents',
    )

    # ── Approver chain state ──────────────────────────────────────────────────
    current_approver_id = fields.Many2one(
        'res.users', string='Current Approver',
        compute='_compute_current_approver', store=True,
    )
    is_current_approver = fields.Boolean(
        compute='_compute_is_current_approver',
    )

    # ── Totals ────────────────────────────────────────────────────────────────
    total_change_value = fields.Monetary(
        string='Total Change Value',
        compute='_compute_totals', store=True,
    )
    total_change_percentage = fields.Float(
        string='Total Change %',
        compute='_compute_totals', store=True, digits=(16, 4),
    )
    cumulative_change_percentage = fields.Float(
        string='Cumulative Change %',
        compute='_compute_cumulative_total', digits=(16, 4),
    )

    # ── Created by ────────────────────────────────────────────────────────────
    created_by_id = fields.Many2one(
        'res.users', string='Created By',
        default=lambda self: self.env.user, readonly=True,
    )

    # ── Change Order History HTML ─────────────────────────────────────────────
    co_history_html = fields.Html(
        string='Change Order History',
        compute='_compute_co_history_html',
        sanitize=False,
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Compute: current approver
    # ─────────────────────────────────────────────────────────────────────────
    @api.depends('approver_ids.status', 'state')
    def _compute_current_approver(self):
        for co in self:
            if co.state != 'pending_approval':
                co.current_approver_id = False
                continue
            pending = co.approver_ids.filtered(
                lambda a: a.status == 'pending'
            ).sorted('sequence')
            co.current_approver_id = pending[:1].user_id if pending else False

    @api.depends_context('uid')
    def _compute_is_current_approver(self):
        uid = self.env.uid
        for co in self:
            co.is_current_approver = (
                co.state == 'pending_approval'
                and co.current_approver_id.id == uid
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Compute: totals
    # ─────────────────────────────────────────────────────────────────────────
    @api.depends('line_ids.change_value', 'line_ids.change_percentage')
    def _compute_totals(self):
        for co in self:
            co.total_change_value = sum(co.line_ids.mapped('change_value'))
            co.total_change_percentage = sum(co.line_ids.mapped('change_percentage'))

    @api.depends('contract_id', 'contract_id.change_order_ids.state',
                 'contract_id.change_order_ids.line_ids')
    def _compute_co_history_html(self):
        _CHANGE_TYPE_LABEL = {
            'change_qty':       'Change Quantity',
            'change_price':     'Change Price',
            'change_qty_price': 'Change Qty &amp; Price',
        }
        _STATE_BADGE = {
            'approved':         ('<span style="background:#28a745;color:#fff;padding:2px 8px;'
                                 'border-radius:4px;font-size:11px;">Approved</span>'),
            'pending_approval': ('<span style="background:#fd7e14;color:#fff;padding:2px 8px;'
                                 'border-radius:4px;font-size:11px;">Pending</span>'),
            'rejected':         ('<span style="background:#dc3545;color:#fff;padding:2px 8px;'
                                 'border-radius:4px;font-size:11px;">Rejected</span>'),
            'draft':            ('<span style="background:#6c757d;color:#fff;padding:2px 8px;'
                                 'border-radius:4px;font-size:11px;">Draft</span>'),
        }
        for co in self:
            contract = co.contract_id
            if not contract or not contract._origin.id:
                co.co_history_html = ''
                continue

            approved_cos = self.env['contract.change_order'].search([
                ('contract_id', '=', contract._origin.id),
                ('state', '=', 'approved'),
            ], order='date asc, name asc')

            if not approved_cos:
                co.co_history_html = (
                    '<p style="color:#6c757d;padding:8px 0;">No approved Change Orders for this contract yet.</p>'
                )
                continue

            rows = ''
            for aco in approved_cos:
                for line in aco.line_ids:
                    change_detail = ''
                    if line.change_type == 'change_qty':
                        change_detail = f'Qty: {line.change_qty:+.2f}'
                    elif line.change_type == 'change_price':
                        change_detail = f'Price: → {line.new_unit_price:.2f}'
                    elif line.change_type == 'change_qty_price':
                        change_detail = f'Qty: {line.change_qty:+.2f} / Price: → {line.new_unit_price:.2f}'

                    rows += (
                        f'<tr>'
                        f'<td>{aco.name}</td>'
                        f'<td>{aco.date or "-"}</td>'
                        f'<td>{line.original_description or "-"}</td>'
                        f'<td style="text-align:right">{line.original_qty:.2f}</td>'
                        f'<td style="text-align:right">{line.original_unit_price:.2f}</td>'
                        f'<td>{_CHANGE_TYPE_LABEL.get(line.change_type, "-")}</td>'
                        f'<td>{change_detail}</td>'
                        f'<td style="text-align:right">{line.change_value:.2f}</td>'
                        f'<td style="text-align:right">{line.change_percentage:.2f}%</td>'
                        f'<td style="text-align:right;{"color:#dc3545;font-weight:bold;" if line.cumulative_change_percentage > 20 else ""}">'
                        f'{line.cumulative_change_percentage:.2f}%</td>'
                        f'<td>{aco.created_by_id.name or "-"}</td>'
                        f'<td>{_STATE_BADGE.get(aco.state, aco.state)}</td>'
                        f'</tr>'
                    )

            html = (
                '<div style="margin-top:4px;">'
                '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
                '<thead>'
                '<tr style="background:#2c3e50;color:#fff;">'
                '<th style="padding:8px;text-align:left;">CO Number</th>'
                '<th style="padding:8px;text-align:left;">Date</th>'
                '<th style="padding:8px;text-align:left;">Work Item</th>'
                '<th style="padding:8px;text-align:right;">Orig. Qty</th>'
                '<th style="padding:8px;text-align:right;">Orig. Unit Price</th>'
                '<th style="padding:8px;text-align:left;">Change Type</th>'
                '<th style="padding:8px;text-align:left;">Change Details</th>'
                '<th style="padding:8px;text-align:right;">Change Value</th>'
                '<th style="padding:8px;text-align:right;">Change %</th>'
                '<th style="padding:8px;text-align:right;">Cumulative %</th>'
                '<th style="padding:8px;text-align:left;">Created By</th>'
                '<th style="padding:8px;text-align:left;">Status</th>'
                '</tr>'
                '</thead>'
                f'<tbody>{rows}</tbody>'
                '</table>'
                '</div>'
            )
            co.co_history_html = html

    @api.depends('total_change_percentage', 'contract_id')
    def _compute_cumulative_total(self):
        for co in self:
            if not co.contract_id:
                co.cumulative_change_percentage = co.total_change_percentage
                continue
            # Exclude current record safely — NewId objects cannot be used in SQL
            co_id = co._origin.id
            domain = [
                ('contract_id', '=', co.contract_id.id),
                ('state', '=', 'approved'),
            ]
            if co_id:
                domain.append(('id', '!=', co_id))
            approved_cos = self.env['contract.change_order'].search(domain)
            prev_pct = sum(
                approved.total_change_percentage for approved in approved_cos
            )
            co.cumulative_change_percentage = co.total_change_percentage + prev_pct

    # ─────────────────────────────────────────────────────────────────────────
    # Onchange
    # ─────────────────────────────────────────────────────────────────────────
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        self.contract_id = False

    @api.onchange('contract_id')
    def _onchange_contract_id(self):
        if self.contract_id and not self.partner_id:
            self.partner_id = self.contract_id.partner_id

    # ─────────────────────────────────────────────────────────────────────────
    # Sequence
    # ─────────────────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                seq = self.env['ir.sequence'].next_by_code(
                    'contract.change_order'
                ) or 'New'
                contract_id = vals.get('contract_id')
                if contract_id:
                    contract = self.env['contract.contract'].browse(contract_id)
                    vals['name'] = f"{seq}-{contract.name}"
                else:
                    vals['name'] = seq
        return super().create(vals_list)

    # ─────────────────────────────────────────────────────────────────────────
    # Workflow actions
    # ─────────────────────────────────────────────────────────────────────────
    def action_submit(self):
        for co in self:
            if not co.line_ids:
                raise UserError(_('Please add at least one change item before submitting.'))
            if not co.approver_ids:
                raise UserError(_('Please add at least one approver before submitting.'))

            # 20% cumulative validation
            co._compute_cumulative_total()
            if co.cumulative_change_percentage > 20.0:
                raise ValidationError(_(
                    'The cumulative change exceeds 20%% of the original contract amount '
                    '(current: %.2f%%). According to company policy, a new contract must be created.'
                ) % co.cumulative_change_percentage)

            co.approver_ids.write({'status': 'pending'})
            co.state = 'pending_approval'
            co._notify_next_approver()
            co.message_post(body=_('Change Order submitted for approval.'))

    def action_approve(self):
        """Called by the current approver."""
        for co in self:
            if not co.is_current_approver:
                raise UserError(_('It is not your turn to approve this Change Order.'))
            pending = co.approver_ids.filtered(
                lambda a: a.status == 'pending'
            ).sorted('sequence')
            if not pending:
                continue
            current = pending[:1]
            total = len(co.approver_ids)
            done = len(co.approver_ids.filtered(lambda a: a.status == 'approved')) + 1
            current.write({'status': 'approved'})
            co.message_post(
                body=_('Approved by %s (Step %d of %d).') % (
                    co.env.user.name, done, total
                )
            )
            # Check if more approvers remain
            still_pending = co.approver_ids.filtered(lambda a: a.status == 'pending')
            if still_pending:
                co._notify_next_approver()
            else:
                co.state = 'approved'
                co.message_post(body=_('Change Order fully approved.'))

    def action_reject(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reject Change Order'),
            'res_model': 'contract.justification.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_action': 'co_reject',
                'default_co_id': self.id,
            },
        }

    def action_resubmit_requester(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Resubmit to Requester'),
            'res_model': 'contract.justification.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_action': 'co_resubmit',
                'default_co_id': self.id,
            },
        }

    def action_reset_draft(self):
        for co in self:
            co.approver_ids.write({'status': 'pending'})
            co.state = 'draft'

    def _do_reject(self, reason):
        """Called from the rejection wizard."""
        for co in self:
            co.state = 'rejected'
            co.message_post(
                body=_('Rejected by %s. Reason: %s') % (
                    self.env.user.name, reason or '—'
                )
            )

    def _notify_next_approver(self):
        for co in self:
            pending = co.approver_ids.filtered(
                lambda a: a.status == 'pending'
            ).sorted('sequence')
            if pending:
                co.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=pending[:1].user_id.id,
                    note=_('Your approval is required for Change Order: %s') % co.name,
                )
