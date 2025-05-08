# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-06 19:25:00 by dannyaudian

from __future__ import unicode_literals

# Basic app configuration
app_name = "payroll_indonesia"
app_title = "Payroll Indonesia"
app_publisher = "PT. Innovasi Terbaik Bangsa"
app_description = "Payroll module for Indonesian companies with local regulatory features"
app_email = "danny.a.pratama@cao-group.co.id"
app_license = "GPL-3"
app_version = "0.1.0"
required_apps = ["erpnext", "hrms"]

# Setup functions - delegated to setup_module.py
before_install = "payroll_indonesia.fixtures.setup.before_install"
after_install = "payroll_indonesia.fixtures.setup.after_install"

# JS files for doctypes
doctype_js = {
    "Employee": "payroll_indonesia/public/js/employee.js",
    "Salary Slip": "payroll_indonesia/public/js/salary_slip.js",
    "Payroll Entry": "payroll_indonesia/public/js/payroll_entry.js",
    "PPh 21 Settings": "payroll_indonesia/public/js/pph_21_settings.js",
    "BPJS Settings": "payroll_indonesia/payroll_indonesia/doctype/bpjs_settings/bpjs_settings.js",
    "BPJS Account Mapping": "payroll_indonesia/payroll_indonesia/doctype/bpjs_account_mapping/bpjs_account_mapping.js",
    "BPJS Payment Summary": "payroll_indonesia/payroll_indonesia/doctype/bpjs_payment_summary/bpjs_payment_summary.js"
}

# List view JS
doctype_list_js = {
    "BPJS Payment Summary": "payroll_indonesia/payroll_indonesia/doctype/bpjs_payment_summary/bpjs_payment_summary_list.js",
    "Employee Tax Summary": "payroll_indonesia/public/js/employee_tax_summary_list.js",
    "BPJS Account Mapping": "payroll_indonesia/payroll_indonesia/doctype/bpjs_account_mapping/bpjs_account_mapping_list.js"
}

# DocType Class Override
override_doctype_class = {
    "Salary Slip": "payroll_indonesia.override.salary_slip.controller.IndonesiaPayrollSalarySlip",
    "Payroll Entry": "payroll_indonesia.override.payroll_entry.CustomPayrollEntry",
    "Salary Structure": "payroll_indonesia.override.salary_structure.CustomSalaryStructure"
}

# Document Events
doc_events = {
    "Employee": {
        "validate": "payroll_indonesia.override.employee.validate",
        "on_update": "payroll_indonesia.override.employee.on_update"
    },
    "PPh 21 Settings": {
        "on_update": "payroll_indonesia.payroll_indonesia.tax.pph21_settings.on_update"
    },
    "BPJS Settings": {
        "validate": "payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.utils.validate_settings",
        "on_update": [
            "payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.bpjs_settings.on_update",
            "payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.utils.setup_accounts"
        ]
    },
    "Payroll Entry": {
        "before_validate": "payroll_indonesia.override.payroll_entry_functions.before_validate",
        "validate": "payroll_indonesia.override.payroll_entry_functions.validate_payroll_entry",
        "on_submit": "payroll_indonesia.override.payroll_entry_functions.on_submit"
    },
    "Salary Slip": {
        "before_insert": "payroll_indonesia.override.salary_slip.gl_entry_override.override_salary_slip_gl_entries",
        "validate": "payroll_indonesia.override.salary_slip_functions.validate_salary_slip",
        "on_submit": [
            "payroll_indonesia.override.salary_slip_functions.on_submit_salary_slip",
            "payroll_indonesia.override.salary_slip_functions.wrapper_create_from_employee_tax_summary",
            "payroll_indonesia.override.salary_slip.gl_entry_override.override_salary_slip_gl_entries"
        ],
        "on_cancel": [
            "payroll_indonesia.override.salary_slip_functions.on_cancel_salary_slip",
            "payroll_indonesia.override.salary_slip_functions.wrapper_update_on_salary_slip_cancel_employee_tax_summary"
        ],
        "after_insert": "payroll_indonesia.override.salary_slip_functions.after_insert_salary_slip"
    },
    "BPJS Account Mapping": {
        "validate": "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping.validate",
        "on_update": "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping.on_update_mapping"
    },
    "BPJS Payment Component": {
        "validate": "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_component.bpjs_payment_component.validate",
        "on_submit": "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_component.bpjs_payment_component.create_journal_entries"
    },
    "Payment Entry": {
        "on_submit": "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.payment_hooks.payment_entry_on_submit",
        "on_cancel": "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.payment_hooks.payment_entry_on_cancel"
    },
    "BPJS Payment Summary": {
        "validate": "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_summary.validate",
        "on_submit": "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_summary.on_submit",
        "on_cancel": "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_summary.on_cancel"
    },
    "Account": {
        "on_update": "payroll_indonesia.payroll_indonesia.account_hooks.account_on_update"
    }
}

# Fixtures - with appropriate filters
fixtures = [
    {
        "doctype": "Custom Field",
        "filters": [["module", "=", "Payroll Indonesia"]]
    },
    {
        "doctype": "Property Setter",
        "filters": [["module", "=", "Payroll Indonesia"]]
    },
    {
        "doctype": "Client Script",
        "filters": [["module", "=", "Payroll Indonesia"]]
    },
    {
        "doctype": "Workspace",
        "filters": [["module", "=", "Payroll Indonesia"]]
    },
    {
        "doctype": "Report",
        "filters": [["module", "=", "Payroll Indonesia"]]
    },
    {
        "doctype": "Print Format",
        "filters": [["name", "in", ["BPJS Payment Summary Report"]]]
    },
    # Master Data
    {
        "doctype": "Supplier Group",
        "filters": [["name", "in", ["BPJS Provider", "Tax Authority"]]]
    },
    {
        "doctype": "Supplier",
        "filters": [["supplier_group", "in", ["BPJS Provider", "Tax Authority"]]]
    },
    {
        "doctype": "Tax Category",
        "filters": [["name", "like", "PPh 21%"]]
    },
    # Payroll Indonesia Settings
    {
        "doctype": "BPJS Settings", 
        "filters": [["name", "=", "BPJS Settings"]]
    },
    {
        "doctype": "PPh 21 Settings",
        "filters": [["name", "=", "PPh 21 Settings"]]
    },
    {
        "doctype": "PPh 21 Tax Bracket",
        "filters": [["parent", "=", "PPh 21 Settings"]]
    },
    {
        "doctype": "PPh 21 PTKP",
        "filters": [["parent", "=", "PPh 21 Settings"]]
    },
    {
        "doctype": "BPJS Account Mapping",
        "filters": [["company", "like", "%"]]
    },
    # Salary Components
    {
        "doctype": "Salary Component",
        "filters": [
            ["name", "in", [
                "BPJS Kesehatan Employee", "BPJS Kesehatan Employer", 
                "BPJS JHT Employee", "BPJS JHT Employer",
                "BPJS JP Employee", "BPJS JP Employer",
                "BPJS JKK", "BPJS JKM",
                "PPh 21"
            ]]
        ]
    },
    # Master Data - Payroll
    {
        "doctype": "Golongan",
        "filters": [["name", "like", "%"]]
    },
    {
        "doctype": "Jabatan",
        "filters": [["name", "like", "%"]]
    }
]

# Scheduler tasks
scheduler_events = {
    "daily": [
        "payroll_indonesia.utilities.tax_slab.create_income_tax_slab", 
        "payroll_indonesia.override.salary_structure.update_salary_structures",
        "payroll_indonesia.payroll_indonesia.bpjs.daily_tasks.check_bpjs_settings"
    ],
    "monthly": [
        "payroll_indonesia.payroll_indonesia.tax.monthly_tasks.update_tax_summaries"
    ],
    "yearly": [
        "payroll_indonesia.payroll_indonesia.tax.yearly_tasks.prepare_tax_report"
    ]
}

# Jinja template methods - only expose read-only and safe functions
jinja = {
    "methods": [
        # BPJS Settings & Functions
        "payroll_indonesia.payroll_indonesia.utils.get_bpjs_settings",
        "payroll_indonesia.payroll_indonesia.utils.calculate_bpjs_contributions",
        "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping.get_mapping_for_company",
        "payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation.hitung_bpjs",
        
        # PPh 21 Settings & Functions
        "payroll_indonesia.payroll_indonesia.utils.get_ptkp_settings",
        "payroll_indonesia.payroll_indonesia.utils.get_ter_rate",
        "payroll_indonesia.payroll_indonesia.utils.should_use_ter",
        "payroll_indonesia.payroll_indonesia.utils.get_pph21_settings",
        "payroll_indonesia.payroll_indonesia.utils.get_pph21_brackets",
        
        # Tax Reporting Functions
        "payroll_indonesia.payroll_indonesia.utils.get_ytd_tax_info",
        "payroll_indonesia.payroll_indonesia.utils.get_spt_month",
        
        # Utility Functions
        "payroll_indonesia.override.salary_slip.base.get_formatted_currency",
        "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_utils.get_formatted_currency"
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

# Document titles for better navigation
get_title = {
    "BPJS Payment Summary": "month_year_title",
    "Employee Tax Summary": "title",
    "Payroll Log": "title",
    "BPJS Account Mapping": "mapping_name"
}

# Module Category - for Desk
module_categories = {
    "Payroll Indonesia": "Human Resources"
}

# Web Routes
website_route_rules = [
    {"from_route": "/payslip/<path:payslip_name>", "to_route": "payroll_indonesia/templates/pages/payslip"}
]

# Hook after migration
after_migrate = [
    "payroll_indonesia.payroll_indonesia.setup.setup_module.after_sync"
]

# Override whitelisted methods
override_whitelisted_methods = {
    "hrms.payroll.doctype.salary_slip.salary_slip.make_salary_slip_from_timesheet": 
    "payroll_indonesia.override.salary_slip.make_salary_slip_from_timesheet"
}

# Whitelist for client-side API calls
whitelist_methods = [
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api.create_payment_entry",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api.get_employee_bpjs_details",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api.get_summary_for_period",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api.get_bpjs_suppliers",
    "payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.get_ytd_data_until_month",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping.get_mapping_for_company",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping.create_default_mapping",
    "payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation.update_all_bpjs_components",
    "payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation.hitung_bpjs"
]