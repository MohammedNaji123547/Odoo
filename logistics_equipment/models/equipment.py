from odoo import models, fields, api


class LogisticsEquipmentCategory(models.Model):
    _name = 'logistics.equipment.category'
    _description = 'Equipment Category'
    _rec_name = 'name'
    _order = 'name'

    name = fields.Char(string='Category Name', required=True)
    description = fields.Text(string='Description')
    equipment_ids = fields.One2many(
        'logistics.equipment', 'category_id', string='Equipment'
    )
    equipment_count = fields.Integer(
        string='Equipment Count', compute='_compute_equipment_count'
    )

    @api.depends('equipment_ids')
    def _compute_equipment_count(self):
        for rec in self:
            rec.equipment_count = len(rec.equipment_ids)


class LogisticsEquipment(models.Model):
    _name = 'logistics.equipment'
    _description = 'Equipment Master List'
    _rec_name = 'name'
    _order = 'category_id, name'

    name = fields.Char(string='Equipment Name', required=True)
    category_id = fields.Many2one(
        'logistics.equipment.category', string='Category', required=True, ondelete='restrict'
    )
    standard_daily_rate = fields.Float(
        string='Standard Daily Rate', digits=(16, 2), default=0.0
    )
    default_supplier_id = fields.Many2one(
        'res.partner', string='Default Supplier',
        domain="[('supplier_rank', '>', 0)]"
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id
    )
    status = fields.Selection([
        ('active',   'Active'),
        ('inactive', 'Inactive'),
    ], string='Status', default='active', required=True)
    notes = fields.Text(string='Notes')

    # Computed: hourly rate derived from standard daily rate
    standard_hourly_rate = fields.Float(
        string='Standard Hourly Rate',
        compute='_compute_standard_hourly_rate', store=True, digits=(16, 2)
    )

    @api.depends('standard_daily_rate')
    def _compute_standard_hourly_rate(self):
        for rec in self:
            rec.standard_hourly_rate = rec.standard_daily_rate / 10.0

    def name_get(self):
        result = []
        for rec in self:
            name = f"[{rec.category_id.name}] {rec.name}" if rec.category_id else rec.name
            result.append((rec.id, name))
        return result
