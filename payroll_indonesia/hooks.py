# -*- coding: utf-8 -*-
# Copyright (c) 2025, Danny Audian and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe

app_name = "payroll_indonesia"
app_title = "Payroll Indonesia"
app_publisher = "Danny Audian"
app_description = "Payroll module for Indonesian companies with local regulatory features"
app_email = "dannyaudian@example.com"
app_license = "GPL-3"
app_version = "0.0.1"
required_apps = ["erpnext"]

# include js in doctype views
doctype_js = {
    "Employee": "public/js/employee.js",
    "Salary Slip": "public/js/salary_slip.js",
    "PPh TER Table": "public/js/pph_ter_table.js",
    "BPJS Payment Summary": "public/js/bpjs_payment_summary.js"
}

# List view customizations
doctype_list_js = {
    "PPh TER Table": "public/js/pph_ter_table_list.js",
    "BPJS Payment Summary": "public/js/bpjs_payment_summary_list.js"
}

# Installation
after_install = "payroll_indonesia.fixtures.setup.after_install"

# DocType Class
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

# Fixtures
fixtures = [
    "Custom Field",
    "Client Script",
    {
        "dt": "Property Setter",
        "filters": [
            ["doc_type", "=", "Employee"]
        ]
    },
    # Core DocTypes
    "PPh TER Table",
    "BPJS Payment Summary",
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
    }
]

# Default configuration values
default_mail_footer = """
<div style="padding: 7px; text-align: center;">
    <p>Powered by <a href="https://erpnext.com" target="_blank">ERPNext</a> & Payroll Indonesia</p>
</div>
"""

# Additional jinja environment globals
jinja = {
    "methods": [
        "payroll_indonesia.payroll_indonesia.utils.get_bpjs_settings",
        "payroll_indonesia.payroll_indonesia.utils.get_ptkp_settings"
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
