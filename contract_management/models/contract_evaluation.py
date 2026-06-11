from odoo import models, fields, api


class ContractEvaluation(models.Model):
    _name = 'contract.evaluation'
    _description = 'Commercial Evaluation'

    contract_id = fields.Many2one(
        'contract.contract', required=True, ondelete='cascade'
    )
    partner_id = fields.Many2one('res.partner', string='Contractor', required=True)
    is_recommended = fields.Boolean(string='Recommended')
    is_lowest = fields.Boolean(compute='_compute_is_lowest', store=False)
    notes = fields.Text(string='Notes / Remarks')
    line_ids = fields.One2many('contract.evaluation.line', 'evaluation_id', string='Lines')
    total_amount = fields.Float(string='Total Amount', compute='_compute_total', store=True)

    @api.depends('line_ids.total')
    def _compute_total(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.mapped('total'))

    def _compute_is_lowest(self):
        for rec in self:
            others = self.search([('contract_id', '=', rec.contract_id.id)])
            min_val = min(others.mapped('total_amount'), default=0)
            rec.is_lowest = rec.total_amount == min_val and min_val > 0


class ContractEvaluationLine(models.Model):
    _name = 'contract.evaluation.line'
    _description = 'Evaluation Line'

    evaluation_id = fields.Many2one('contract.evaluation', required=True, ondelete='cascade')
    contract_line_id = fields.Many2one('contract.line', string='BOQ Item')
    description = fields.Char(string='Description')
    qty = fields.Float(string='Quantity')
    uom = fields.Char(string='Unit')
    unit_rate = fields.Float(string='Unit Rate (Bid)')
    awarded_rate = fields.Float(string='Awarded Rate (Optional)')
    total = fields.Float(compute='_compute_total', store=True)
    profitability = fields.Float(compute='_compute_profitability', store=True, string='Profit %')

    @api.onchange('contract_line_id')
    def _onchange_contract_line_id(self):
        if self.contract_line_id:
            self.description = self.contract_line_id.description
            self.qty = self.contract_line_id.qty
            self.uom = self.contract_line_id.uom

    @api.depends('qty', 'unit_rate')
    def _compute_total(self):
        for line in self:
            line.total = line.qty * line.unit_rate

    @api.depends('unit_rate', 'awarded_rate')
    def _compute_profitability(self):
        for line in self:
            if line.unit_rate:
                line.profitability = ((line.awarded_rate - line.unit_rate) / line.unit_rate) * 100
            else:
                line.profitability = 0.0