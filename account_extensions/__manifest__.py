{
    'name': 'Account Extensions',
    'version': '17.0.1.0.0',
    'summary': 'Extends Vendor Bills and Customer Invoices with cost center, contract, invoice request, and period fields.',
    'category': 'Accounting',
    'author': 'Custom',
    'depends': [
        'account',
        'contract_management',
        'invoice_request',
        'project',
    ],
    'data': [
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
