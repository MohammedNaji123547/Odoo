{
    'name': 'Invoice Request',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Invoicing',
    'summary': 'Request vendor invoice creation from Finance',
    'description': '''
        Allows operational teams to submit invoicing requests for
        contractors and vendors. Requests flow through manager approval
        then Finance, who auto-creates the vendor bill in Odoo Accounting.
        Designed to link to multiple operational modules (contracts,
        work orders, purchase orders, etc.).
    ''',
    'author': 'Your Company',
    'depends': ['base', 'mail', 'account', 'contract_management'],
    'data': [
        'security/res_groups.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'wizard/views/invoice_request_wizard_views.xml',
        'views/invoice_request_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'OPL-1',
}
