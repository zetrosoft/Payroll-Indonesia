# -*- coding: utf-8 -*-
# Copyright (c) 2025, Danny Audian and contributors
# For license information, please see license.txt
# Last modified: 2025-04-23 13:11:33 by dannyaudian

from __future__ import unicode_literals

app_name = "payroll_indonesia"
app_title = "Payroll Indonesia"
app_publisher = "Danny Audian"
app_description = "Payroll module for Indonesian companies with local regulatory features"
app_email = "dannyaudian@example.com"
app_license = "GPL-3"
app_version = "0.0.1"
required_apps = ["erpnext", "hrms"]

# JS files for doctypes
doctype_js = {
    "Employee": "public/js/employee.js",
    "Salary Slip": "public/js/salary_slip.js",
    "PPh TER Table": "public/js/pph_ter_table.js",
    "BPJS Payment Summary": "public/js/bpjs_payment_summary.js",
    "PPh 21 Settings": "public/js/pph_21_settings.js",
    "BPJS Settings": "public/js/bpjs_settings.js"
}

# List view JS 
doctype_list_js = {
    "PPh TER Table": "public/js/pph_ter_table_list.js",
    "BPJS Payment Summary": "public/js/bpjs_payment_summary_list.js",
    "Employee Tax Summary": "public/js/employee_tax_summary_list.js"
}

# Installation
after_install = "payroll_indonesia.fixtures.setup.after_install"

# DocType Class Override
override_doctype_class = {
    "Salary Slip": "payroll_indonesia.override.salary_slip.CustomSalarySlip"
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
    }
}

# Fixtures (organized by load order)
fixtures = [
    # Basic Setup
    {
        "dt": "Custom Field",
        "filters": [
            ["dt", "in", ["Employee", "Salary Slip"]]
        ]
    },
    "Client Script",
    {
        "dt": "Property Setter",
        "filters": [
            ["doc_type", "=", "Employee"]
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
    
    # Workspace & Reports
    {
        "dt": "Workspace",
        "filters": [
            ["name", "=", "Payroll Indonesia"]
        ]
    },
    
    "payroll_indonesia/payroll_indonesia/workspace/payroll_indonesia/payroll_indonesia.json",
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
        "payroll_indonesia.payroll_indonesia.utils.get_bpjs_settings",
        "payroll_indonesia.payroll_indonesia.utils.get_ptkp_settings",
        "payroll_indonesia.payroll_indonesia.utils.calculate_bpjs_contributions",
        "payroll_indonesia.payroll_indonesia.utils.get_ter_rate",
        "payroll_indonesia.payroll_indonesia.utils.should_use_ter",
        "payroll_indonesia.payroll_indonesia.utils.get_pph21_settings"
    ]
}

# Regional Settings
regional_overrides = {
    "Indonesia": {
        "controller_overrides": {
            "Salary Slip": "payroll_indonesia.override.salary_slip"
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

# Boot Info
boot_session = "payroll_indonesia.startup.boot.boot_session"

# Web Routes
website_route_rules = [
    {"from_route": "/payslip/<path:payslip_name>", "to_route": "payroll_indonesia/templates/pages/payslip"}
]