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
    "PPh TER Table": "public/js/pph_ter_table.js"  # Added for PPh TER Table
}

# List view customizations
doctype_list_js = {
    "PPh TER Table": "public/js/pph_ter_table_list.js"  # Added for PPh TER Table list view
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
    {
        "dt": "Custom Field",
        "filters": [
            ["name", "in", [
                "Employee-payroll_indonesia_section",
                "Employee-golongan",
                "Employee-jabatan",
                "Employee-status_pajak",
                "Employee-jumlah_tanggungan",
                "Employee-npwp_section",
                "Employee-npwp",
                "Employee-npwp_suami",
                "Employee-npwp_gabung_suami",
                "Employee-bpjs_section",
                "Employee-ikut_bpjs_kesehatan",
                "Employee-ikut_bpjs_ketenagakerjaan",
                "Employee-employment_details_section",
                "Employee-tipe_karyawan",
                "Employee-penghasilan_final"
            ]]
        ]
    },
    {
        "dt": "Client Script",
        "filters": [
            ["dt", "=", "Employee"]
        ]
    },
    {
        "dt": "Property Setter",
        "filters": [
            ["doc_type", "=", "Employee"]
        ]
    },
    {
        "dt": "Salary Component",
        "filters": [
            ["name", "in", [
                # Earnings
                "Gaji Pokok",
                "Tunjangan Makan",
                "Tunjangan Transport",
                "Insentif",
                "Bonus",
                # Deductions
                "PPh 21",
                "BPJS JHT Employee",
                "BPJS JP Employee",
                "BPJS Kesehatan Employee",
                # Statistical (Employer Share)
                "BPJS JHT Employer",
                "BPJS JP Employer",
                "BPJS JKK",
                "BPJS JKM",
                "BPJS Kesehatan Employer"
            ]]
        ]
    },
    {
        "dt": "Salary Structure",
        "filters": [
            ["name", "in", [
                "Struktur Gaji Tetap G1",
                "Struktur Freelance"
            ]]
        ]
    },
    {
        "dt": "Account",
        "filters": [
            ["name", "in", [
                # Expense Accounts
                "Beban Gaji Pokok - %",
                "Beban Tunjangan Makan - %",
                "Beban Tunjangan Transport - %",
                "Beban Insentif - %",
                "Beban Bonus - %",
                "Beban BPJS JHT - %",
                "Beban BPJS JP - %",
                "Beban BPJS JKK - %",
                "Beban BPJS JKM - %",
                "Beban BPJS Kesehatan - %",
                # Liability Accounts
                "Hutang PPh 21 - %",
                "Hutang BPJS JHT - %",
                "Hutang BPJS JP - %",
                "Hutang BPJS Kesehatan - %"
            ]]
        ]
    },
    {
        "dt": "PPh TER Table",  # Added PPh TER Table fixture
        "filters": [
            ["modified", ">", "2025-04-22 03:39:27"],  # Current timestamp
            ["owner", "=", "dannyaudian"]  # Current user
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
