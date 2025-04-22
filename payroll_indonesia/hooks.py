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
    }
}

# DocTypes to be created by the app
doctype_list = [
    # Settings
    "BPJS Settings",
    "PPh 21 Settings",
    
    # Master DocTypes
    "Golongan",
    "Jabatan",
    
    # Transaction DocTypes
    "BPJS Payment Summary",
    "PPh TER Table",
    
    # Child Tables
    "BPJS Payment Summary Detail",
    "BPJS Payment Account Detail",
    "PPh TER Detail",
    "PPh TER Account Detail",
    "PPh 21 Tax Bracket"
]

# Fixtures (simplified and grouped)
fixtures = [
    # Custom UI Elements
    {
        "dt": "Custom Field",
        "filters": [
            ["dt", "=", "Employee"],
            ["module", "=", "Payroll Indonesia"]
        ]
    },
    "Client Script",
    {
        "dt": "Property Setter",
        "filters": [
            ["doc_type", "=", "Employee"]
        ]
    },
    
    # Master Data
    {
        "dt": "Supplier Group",
        "filters": [
            ["supplier_group_name", "=", "Government"]
        ]
    },
    {
        "dt": "Tax Category",
        "filters": [
            ["name", "=", "Government"]
        ]
    },
    
    # Salary Components and Structure
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
    {
        "dt": "Salary Structure",
        "filters": [
            ["name", "=", "Struktur Gaji Tetap G1"]
        ]
    },
    
    # Workspace
    {
        "dt": "Workspace",
        "filters": [
            ["name", "=", "Payroll Indonesia"]
        ]
    }
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