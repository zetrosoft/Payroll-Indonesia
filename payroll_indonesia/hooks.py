# -*- coding: utf-8 -*-
# Copyright (c) 2025, Danny Audian and contributors
# For license information, please see license.txt

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
    "BPJS Payment Summary": "public/js/bpjs_payment_summary.js"
}

# List view JS 
doctype_list_js = {
    "PPh TER Table": "public/js/pph_ter_table_list.js",
    "BPJS Payment Summary": "public/js/bpjs_payment_summary_list.js"
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
        "validate": "payroll_indonesia.override.salary_slip.validate_salary_slip",
        "on_submit": "payroll_indonesia.override.salary_slip.on_submit_salary_slip"
    }
}

# Fixtures (organized by load order)
fixtures = [
    # Basic Setup
    {
        "dt": "Custom Field",
        "filters": [
            ["dt", "=", "Employee"]
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
    
    # Payroll Indonesia Settings
    "BPJS Settings",
    "PPh 21 Settings",
    "PPh 21 Tax Bracket",
    
    # Master Data - Payroll
    "Golongan",
    "Jabatan",
    
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
    "Golongan",
    "Jabatan",
    "Salary Component",
    "Salary Structure",
    "Custom Field",
    "Property Setter",
    "Client Script",
    "Workspace"
]

# Jinja template methods
jinja = {
    "methods": [
        "payroll_indonesia.payroll_indonesia.utils.get_bpjs_settings",
        "payroll_indonesia.payroll_indonesia.utils.get_ptkp_settings",
        "payroll_indonesia.payroll_indonesia.utils.calculate_bpjs_contributions"
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
    "PPh TER Table": "month_year_title"
}

# Module Category - for Desk
module_categories = {
    "Payroll Indonesia": "Accounting"
}

# Document States
states_in_transaction = {
    "BPJS Payment Summary": ["Draft", "Submitted", "Paid", "Cancelled"],
    "PPh TER Table": ["Draft", "Submitted", "Paid", "Cancelled"]
}

# Last modified timestamp: 2025-04-22 13:53:36
# Updated by: dannyaudian