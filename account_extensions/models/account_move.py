from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ── Shared fields (both bill and invoice) ─────────────────────────────────
    cost_center_id = fields.Many2one(
        'account.analytic.account',
        string='Cost Center',
        tracking=True,
    )
    period_from = fields.Date(string='Period From', tracking=True)
    period_to   = fields.Date(string='Period To',   tracking=True)

    # ── Vendor Bill fields ────────────────────────────────────────────────────
    invoice_request_id = fields.Many2one(
        'invoice.request',
        string='Invoice Request',
        domain=[('state', '=', 'finance_approved')],
        tracking=True,
        help="Link to an approved Invoice Request. "
             "Selecting one will auto-fill the contract, cost center, and period.",
    )

    # ── Customer Invoice fields ───────────────────────────────────────────────
    contract_id = fields.Many2one(
        'contract.contract',
        string='Contract',
        domain=[('state', 'in', ['active', 'completed'])],
        tracking=True,
    )
    project_id = fields.Many2one(
        'project.project',
        string='Project / CTR',
        tracking=True,
    )

    # ── Onchange: auto-fill from Invoice Request ──────────────────────────────
    @api.onchange('invoice_request_id')
    def _onchange_invoice_request_id(self):
        req = self.invoice_request_id
        if req:
            self.contract_id  = req.contract_id
            self.period_from  = req.period_from
            self.period_to    = req.period_to
            # Pull cost center from the linked contract's analytic account
            if req.contract_id and req.contract_id.analytic_account_id:
                self.cost_center_id = req.contract_id.analytic_account_id
        else:
            self.contract_id    = False
            self.period_from    = False
            self.period_to      = False
            self.cost_center_id = False

    # ── Onchange: auto-fill cost center from contract (customer invoice) ──────
    @api.onchange('contract_id')
    def _onchange_contract_id(self):
        if self.contract_id and self.contract_id.analytic_account_id:
            self.cost_center_id = self.contract_id.analytic_account_id
        if self.contract_id and self.contract_id.project_id:
            self.project_id = self.contract_id.project_id
