{
    'name': 'Contract Management',
    'version': '17.0.1.0.0',
    'category': 'Legal',
    'summary': 'Manage company contracts',
    'author': 'Your Company',
    'depends': ['base', 'contacts', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/contract_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}