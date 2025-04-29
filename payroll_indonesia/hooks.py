# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-29 12:48:43 by dannyaudian

from __future__ import unicode_literals

# Konfigurasi app dasar
app_name = "payroll_indonesia"
app_title = "Payroll Indonesia"
app_publisher = "PT. Innovasi Terbaik Bangsa"
app_description = "Payroll module for Indonesian companies with local regulatory features"
app_email = "danny.a.pratama@cao-group.co.id"
app_license = "GPL-3"
app_version = "0.0.1"
required_apps = ["erpnext", "hrms"]

# JS files untuk doctypes
doctype_js = {
    "Employee": "payroll_indonesia/public/js/employee.js",
    "Salary Slip": "payroll_indonesia/public/js/salary_slip.js",
    "Payroll Entry": "payroll_indonesia/public/js/payroll_entry.js",
    "PPh TER Table": "payroll_indonesia/payroll_indonesia/doctype/pph_ter_table/pph_ter_table.js",
    "BPJS Payment Summary": "payroll_indonesia/payroll_indonesia/doctype/bpjs_payment_summary/bpjs_payment_summary.js",
    "PPh 21 Settings": "payroll_indonesia/public/js/pph_21_settings.js",
    "BPJS Settings": "payroll_indonesia/payroll_indonesia/doctype/bpjs_settings/bpjs_settings.js",
    "BPJS Account Mapping": "payroll_indonesia/payroll_indonesia/doctype/bpjs_account_mapping/bpjs_account_mapping.js"
}

# List view JS
doctype_list_js = {
    "PPh TER Table": "payroll_indonesia/payroll_indonesia/doctype/pph_ter_table/pph_ter_table_list.js",
    "BPJS Payment Summary": "payroll_indonesia/payroll_indonesia/doctype/bpjs_payment_summary/bpjs_payment_summary_list.js",
    "Employee Tax Summary": "payroll_indonesia/public/js/employee_tax_summary_list.js"
}

# Installation
before_install = "payroll_indonesia.fixtures.setup.before_install"
after_install = "payroll_indonesia.fixtures.setup.after_install"

# DocType Class Override
override_doctype_class = {
    # FIXED: Path to IndonesiaPayrollSalarySlip updated to correct location
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
        "on_update": "payroll_indonesia.payroll_indonesia.bpjs.bpjs_settings.on_update"
    },  
    "Payroll Entry": {
        "before_validate": "payroll_indonesia.override.payroll_entry_functions.before_validate",
        "validate": "payroll_indonesia.override.payroll_entry_functions.validate_payroll_entry",
        "on_submit": "payroll_indonesia.override.payroll_entry_functions.on_submit"
    },
    "Salary Slip": {
        "before_insert": "payroll_indonesia.override.salary_slip.gl_entry_override.override_salary_slip_gl_entries",
        "validate": "payroll_indonesia.override.salary_slip_functions.validate_salary_slip",
        "on_submit": "payroll_indonesia.override.salary_slip_functions.on_submit_salary_slip",
        "on_cancel": "payroll_indonesia.override.salary_slip_functions.on_cancel_salary_slip",
        "after_insert": "payroll_indonesia.override.salary_slip_functions.after_insert_salary_slip"
    },
    
    "BPJS Account Mapping": {
        "validate": "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping.validate"
    },
    "BPJS Payment Component": {
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
    }
}

# Fixtures
fixtures = [
    # Basic Setup
    "Custom Field",
    "Client Script",
    "Property Setter",
    
    # Master Data
    "Supplier Group",
    "Supplier",
    "Tax Category",
    
    # Payroll Indonesia Settings
    "BPJS Settings",
    "PPh 21 Settings",
    "PPh 21 Tax Bracket",
    "PPh 21 TER Table",
    "PPh 21 PTKP",
    "BPJS Account Mapping",
    
    # Master Data - Payroll
    "Golongan",
    "Jabatan",
    
    # Tracking & Component DocTypes
    "Employee Tax Summary",
    "Employee Monthly Tax Detail",
    "Payroll Log",
    "BPJS Payment Component",
    
    # Salary Components
    "Salary Component",
    
    # Transaction DocTypes
    "BPJS Payment Summary",
    "BPJS Payment Summary Detail",
    "BPJS Payment Account Detail",
    "PPh TER Table",
    "PPh TER Detail",
    "PPh TER Account Detail",
    
    # Workspace
    "Workspace",
    
    # Reports
    "Report",
    
    # Print Format
    {
        "doctype": "Print Format",
        "filters": [
            [
                "name",
                "in",
                ["BPJS Payment Summary Report"]
            ]
        ]
    }
]

# Scheduler tasks
scheduler_events = {
    "daily": [
        "payroll_indonesia.utilities.tax_slab.create_income_tax_slab", 
        "payroll_indonesia.override.salary_structure.update_salary_structures"
    ],
    "monthly": [
        "payroll_indonesia.payroll_indonesia.tax.monthly_tasks.update_tax_summaries"
    ],
    "yearly": [
        "payroll_indonesia.payroll_indonesia.tax.yearly_tasks.prepare_tax_report"
    ]
}

# Jinja template methods
jinja = {
    "methods": [
        # BPJS Settings & Functions
        "payroll_indonesia.payroll_indonesia.utils.get_bpjs_settings",
        "payroll_indonesia.payroll_indonesia.utils.calculate_bpjs_contributions",
        "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping.get_mapping_for_company",
        "payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation.hitung_bpjs",
        "payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation.debug_log",
        
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
        "payroll_indonesia.payroll_indonesia.utils.get_spt_month",
        
        # Modular Calculator Functions
        "payroll_indonesia.override.salary_slip.base.get_formatted_currency",
        "payroll_indonesia.override.salary_slip.ter_calculator.get_ter_rate",
        "payroll_indonesia.override.salary_slip.ter_calculator.should_use_ter_method",
        
        # PPh TER Table & Employee Tax Summary Functions
        "payroll_indonesia.payroll_indonesia.doctype.pph_ter_table.pph_ter_table.create_from_salary_slip",
        "payroll_indonesia.payroll_indonesia.doctype.pph_ter_table.pph_ter_table.update_on_salary_slip_cancel",
        "payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.create_from_salary_slip",
        "payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.update_on_salary_slip_cancel",
        
        # BPJS Payment Summary Functions - Updated paths to match new structure
        "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api.get_summary_for_period",
        "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api.get_employee_bpjs_details",
        "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api.create_payment_entry",
        # Fungsi utilitas dari bpjs_payment_utils.py
        "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_utils.get_formatted_currency",
        "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_utils.debug_log"
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

# Document title fields untuk navigasi yang lebih baik
get_title = {
    "BPJS Payment Summary": "month_year_title",
    "PPh TER Table": "month_year_title",
    "Employee Tax Summary": "title",
    "Payroll Log": "title",
    "BPJS Account Mapping": "mapping_name"
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

# Web Routes
website_route_rules = [
    {"from_route": "/payslip/<path:payslip_name>", "to_route": "payroll_indonesia/templates/pages/payslip"}
]

# Hook setelah migrasi
after_migrate = [
    "payroll_indonesia.fixtures.setup.check_system_readiness",
    "payroll_indonesia.utilities.tax_slab.create_income_tax_slab",
    "payroll_indonesia.override.salary_structure.create_default_salary_structure",
    "payroll_indonesia.utilities.fix_doctype_structure.fix_all_doctypes"
]

override_whitelisted_methods = {
    "hrms.payroll.doctype.salary_slip.salary_slip.make_salary_slip_from_timesheet": 
    "payroll_indonesia.override.salary_slip.make_salary_slip_from_timesheet"
}

on_session_creation = [
    "payroll_indonesia.override.auth_hooks.on_session_creation"
]

rest_export = {
    "Employee": {
        "get": "payroll_indonesia.api.get_employee"
    },
    "Salary Slip": {
        "get": "payroll_indonesia.api.get_salary_slip",
        "list": "payroll_indonesia.api.get_recent_salary_slips",
        "employee": "payroll_indonesia.api.get_salary_slips_by_employee"
    },
    "BPJS Payment Summary": {
        "get": "payroll_indonesia.api.get_bpjs_summary",
        "list": "payroll_indonesia.api.get_bpjs_summaries"
    }
}

# Add diagnostic tools
debug_tools = [
    "payroll_indonesia.override.salary_slip.diagnose_salary_slip_submission",
    "payroll_indonesia.override.salary_slip.manually_create_related_documents",
    # Mengarahkan ke fungsi debug di bpjs_payment_utils.py
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_utils.debug_log"
]

# Daftar modul yang baru dibuat untuk memudahkan debugging
module_info = {
    "payroll_indonesia.override.salary_slip": "Main Salary Slip Override",
    "payroll_indonesia.override.salary_slip.base": "Salary Slip Base Utilities",
    "payroll_indonesia.override.salary_slip.tax_calculator": "PPh 21 Calculator",
    "payroll_indonesia.override.salary_slip.bpjs_calculator": "BPJS Calculator",
    "payroll_indonesia.override.salary_slip.ter_calculator": "TER Method Calculator",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping": "BPJS Account Mapping Controller",
    "payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation": "BPJS Calculation Module",
    "payroll_indonesia.payroll_indonesia.doctype.pph_ter_table.pph_ter_table": "PPh TER Table Controller",
    "payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary": "Employee Tax Summary Controller",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_summary": "BPJS Payment Summary Controller",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api": "BPJS Payment API",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_integration": "BPJS Payment Integration",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_utils": "BPJS Payment Utilities",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.payment_hooks": "BPJS Payment Hooks"
}

# Whitelist for Client-side API Calls
whitelist_methods = [
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api.create_payment_entry",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api.get_employee_bpjs_details",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api.get_summary_for_period",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api.get_bpjs_suppliers",
    "payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.get_ytd_data_until_month"
]