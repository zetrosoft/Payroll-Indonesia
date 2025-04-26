# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-26 10:00:00 by dannyaudian

from __future__ import unicode_literals
from payroll_indonesia.fixtures.after_migrate import process_fixtures
from payroll_indonesia.hooks.before_fixtures import before_fixtures

app_name = "payroll_indonesia"
app_title = ["Payroll Indonesia"]  # List bukan string
app_publisher = "PT. Innovasi Terbaik Bangsa" 
app_description = "Payroll module for Indonesian companies with local regulatory features"
app_email = "danny.a.pratama@cao-group.co.id"
app_license = "GPL-3"
app_version = "0.0.1"
required_apps = ["erpnext", "hrms"]

# JS files for doctypes - Corrected paths
doctype_js = {
    "Employee": "payroll_indonesia/public/js/employee.js",
    "Salary Slip": "payroll_indonesia/public/js/salary_slip.js",
    "Payroll Entry": "payroll_indonesia/public/js/payroll_entry.js",
    "PPh TER Table": "payroll_indonesia/payroll_indonesia/doctype/pph_ter_table/pph_ter_table.js",
    "BPJS Payment Summary": "payroll_indonesia/payroll_indonesia/doctype/bpjs_payment_summary/bpjs_payment_summary.js",
    "PPh 21 Settings": "payroll_indonesia/public/js/pph_21_settings.js",
    "BPJS Settings": "payroll_indonesia/payroll_indonesia/doctype/bpjs_settings/bpjs_settings.js"
}

# List view JS - Corrected paths
doctype_list_js = {
    "PPh TER Table": "payroll_indonesia/payroll_indonesia/doctype/pph_ter_table/pph_ter_table_list.js",
    "BPJS Payment Summary": "payroll_indonesia/payroll_indonesia/doctype/bpjs_payment_summary/bpjs_payment_summary_list.js",
    "Employee Tax Summary": "payroll_indonesia/public/js/employee_tax_summary_list.js"
}

# Installation
after_install = "payroll_indonesia.fixtures.setup.after_install"

# DocType Class Override
override_doctype_class = {
    "Salary Slip": "payroll_indonesia.override.salary_slip.CustomSalarySlip",
    "Payroll Entry": "payroll_indonesia.override.payroll_entry.CustomPayrollEntry",
    "Salary Structure": "payroll_indonesia.override.salary_structure.CustomSalaryStructure"
}

# Document Events
doc_events = {
    "Employee": {
        "validate": "payroll_indonesia.override.employee.validate",
        "on_update": "payroll_indonesia.override.employee.on_update"
    },
    "Salary Slip": {
        "validate": "payroll_indonesia.override.salary_slip_functions.validate_salary_slip",
        "on_submit": "payroll_indonesia.override.salary_slip_functions.on_submit_salary_slip",
        "after_insert": "payroll_indonesia.override.salary_slip_functions.after_insert_salary_slip"
    },
    "PPh 21 Settings": {
        "on_update": "payroll_indonesia.payroll_indonesia.tax.pph21_settings.on_update"
    },
    "BPJS Settings": {
        "on_update": "payroll_indonesia.payroll_indonesia.bpjs.bpjs_settings.on_update"
    },  
    "Payroll Entry": {
        "before_validate": "payroll_indonesia.override.payroll_entry_functions.before_validate",
        "validate": "payroll_indonesia.override.payroll_entry_functions.validate_payroll_entry",
        "on_submit": "payroll_indonesia.override.payroll_entry_functions.on_submit"
    }
}

# Fixtures (organized by load order)
fixtures = [
    # Basic Setup
    {
        "dt": "Custom Field",
        "filters": [
            ["dt", "in", ["Employee", "Salary Slip", "Payroll Entry"]]
        ]
    },
    "Client Script",
    {
        "dt": "Property Setter",
        "filters": [
            ["doc_type", "in", ["Employee", "Payroll Entry"]]
        ]
    },
    
    # Income Tax Slab
    {
        "dt": "Income Tax Slab",
        "filters": [
            ["currency", "=", "IDR"]
        ]
    },
    
    # Master Data - First Level (Groups)
    {
        "dt": "Supplier Group",
        "filters": [
            ["supplier_group_name", "=", "Government"]
        ]
    },
    
    # Master Data - Second Level (Dependent Items)
    {
        "dt": "Supplier",
        "filters": [
            ["name", "=", "BPJS"]
        ]
    },
    {
        "dt": "Tax Category",
        "filters": [
            ["name", "=", "Government"]
        ]
    },
    
    # Payroll Indonesia Settings - Using DocType Names
    "BPJS Settings",
    "PPh 21 Settings",
    "PPh 21 Tax Bracket",
    "PPh 21 TER Table",
    "PPh 21 PTKP",
    
    # Master Data - Payroll
    "Golongan",
    "Jabatan",
    
    # Tracking & Component DocTypes
    "Employee Tax Summary",
    "Payroll Log",
    "BPJS Payment Component",
    
    # Salary Components (need to load before structure)
    {
        "dt": "Salary Component",
        "filters": [
            ["name", "in", [
                "Gaji Pokok", "Tunjangan Makan", "Tunjangan Transport", 
                "Insentif", "Bonus", "PPh 21",
                "BPJS JHT Employee", "BPJS JP Employee", "BPJS Kesehatan Employee",
                "BPJS JHT Employer", "BPJS JP Employer", "BPJS JKK",
                "BPJS JKM", "BPJS Kesehatan Employer"
            ]]
        ]
    },
    
    # Salary Structure (loads after components)
    {
        "dt": "Salary Structure",
        "filters": [
            ["name", "=", "Struktur Gaji Tetap G1"]
        ]
    },
    
    # Transaction DocTypes
    "BPJS Payment Summary",
    "BPJS Payment Summary Detail",
    "BPJS Payment Account Detail",
    "PPh TER Table",
    "PPh TER Detail",
    "PPh TER Account Detail",
    
    # Workspace
    {
        "doctype": "Workspace",
        "filters": [
            ["name", "=", "Payroll Indonesia"]
        ]
    },
    
    # Reports
    {
        "dt": "Report",
        "filters": [
            ["name", "in", [
                "PPh 21 Summary", 
                "BPJS Monthly Report",
                "TER vs Progressive Comparison"
            ]]
        ]
    }
]

# Control fixture loading order
fixtures_import_order = [
    "Supplier Group",
    "Supplier",
    "Tax Category",
    "Income Tax Slab", 
    "BPJS Settings",
    "PPh 21 Settings",
    "PPh 21 Tax Bracket",
    "PPh 21 TER Table",
    "PPh 21 PTKP",
    "Golongan",
    "Jabatan",
    "Employee Tax Summary",
    "Payroll Log",
    "BPJS Payment Component",
    "Salary Component",
    "Salary Structure",
    "Custom Field",
    "Property Setter",
    "Client Script",
    "Report",
    "Workspace"
]

# Jinja template methods
jinja = {
    "methods": [
        # BPJS Settings & Functions
        "payroll_indonesia.payroll_indonesia.utils.get_bpjs_settings",
        "payroll_indonesia.payroll_indonesia.utils.calculate_bpjs_contributions",
        
        # PPh 21 Settings & Functions
        "payroll_indonesia.payroll_indonesia.utils.get_ptkp_settings",
        "payroll_indonesia.payroll_indonesia.utils.get_ter_rate",
        "payroll_indonesia.payroll_indonesia.utils.should_use_ter",
        "payroll_indonesia.payroll_indonesia.utils.get_pph21_settings",
        "payroll_indonesia.payroll_indonesia.utils.get_pph21_brackets",
        
        # Tax Reporting Functions
        "payroll_indonesia.payroll_indonesia.utils.get_ytd_tax_info",
        "payroll_indonesia.payroll_indonesia.utils.create_tax_summary_doc",
        
        # Dynamic Salary Calculation Functions
        "payroll_indonesia.payroll_indonesia.utils.get_spt_month"
    ]
}

# Regional Settings
regional_overrides = {
    "Indonesia": {
        "controller_overrides": {
            "Salary Slip": "payroll_indonesia.override.salary_slip",
            "Payroll Entry": "payroll_indonesia.override.payroll_entry"
        }
    }
}

# Module Export Config
export_python_type_annotations = True

# Document title fields for better navigation
get_title = {
    "BPJS Payment Summary": "month_year_title",
    "PPh TER Table": "month_year_title",
    "Employee Tax Summary": "title",
    "Payroll Log": "title"
}

# Module Category - for Desk
module_categories = {
    "Payroll Indonesia": "Human Resources"
}

# Document States
states_in_transaction = {
    "BPJS Payment Summary": ["Draft", "Submitted", "Paid", "Cancelled"],
    "PPh TER Table": ["Draft", "Submitted", "Paid", "Cancelled"]
}

# Scheduled Tasks
scheduler_events = {
    "monthly": [
        "payroll_indonesia.payroll_indonesia.tax.monthly_tasks.update_tax_summaries"
    ],
    "yearly": [
        "payroll_indonesia.payroll_indonesia.tax.yearly_tasks.prepare_tax_report"
    ]
}

# Web Routes
website_route_rules = [
    {"from_route": "/payslip/<path:payslip_name>", "to_route": "payroll_indonesia/templates/pages/payslip"}
]

# Before fixtures hook - untuk menyimpan status dokumen sebelum fixture diproses
before_fixtures = [
    "payroll_indonesia.hooks.before_fixtures.before_fixtures"
]

# After migrate hook - untuk memastikan status submit dan nilai-nilai penting terjaga setelah migrate
after_migrate = [
    "payroll_indonesia.fixtures.after_migrate.process_fixtures"
]

# After fixtures hook - untuk mengembalikan status dokumen setelah fixture diproses
after_fixtures = [
    "payroll_indonesia.fixtures.after_migrate.process_fixtures"
]