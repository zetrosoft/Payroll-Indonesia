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

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/payroll_indonesia/css/payroll_indonesia.css"
# app_include_js = "/assets/payroll_indonesia/js/payroll_indonesia.js"

# include js, css files in header of web template
# web_include_css = "/assets/payroll_indonesia/css/payroll_indonesia.css"
# web_include_js = "/assets/payroll_indonesia/js/payroll_indonesia.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "payroll_indonesia/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
    "Employee": "public/js/employee.js",
    "Salary Slip": "public/js/salary_slip.js"
}

# doctype_list_js = {"doctype": "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype": "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype": "public/js/doctype_calendar.js"}

# Home Pages
# ----------
# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#   "Role": "home_page"
# }

# Website user home page (by function)
# get_website_user_home_page = "payroll_indonesia.utils.get_home_page"

# Generators
# ----------
# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------
# before_install = "payroll_indonesia.fixtures.setup.before_install"
after_install = "payroll_indonesia.fixtures.setup.after_install"

# Boot
# ----
# boot_session = "payroll_indonesia.boot.boot_session"

# DocType Class
# ---------------
override_doctype_class = {
    "Salary Slip": "payroll_indonesia.override.salary_slip.CustomSalarySlip"
}

# Document Events
# --------------
doc_events = {
    "Employee": {
        "validate": "payroll_indonesia.override.employee.validate",
        "on_update": "payroll_indonesia.override.employee.on_update"
    }
}

# Scheduled Tasks
# ---------------
# scheduler_events = {
#   "all": [
#       "payroll_indonesia.tasks.all"
#   ],
#   "daily": [
#       "payroll_indonesia.tasks.daily"
#   ],
#   "hourly": [
#       "payroll_indonesia.tasks.hourly"
#   ],
#   "weekly": [
#       "payroll_indonesia.tasks.weekly"
#   ],
#   "monthly": [
#       "payroll_indonesia.tasks.monthly"
#   ]
# }

# Testing
# -------
# before_tests = "payroll_indonesia.install.before_tests"

# Overriding Methods
# ------------------------------
# override_whitelisted_methods = {
#   "frappe.desk.doctype.event.event.get_events": "payroll_indonesia.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
#   "Task": "payroll_indonesia.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Fixtures
# --------
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
                "Employee-npwp",
                "Employee-npwp_suami",
                "Employee-npwp_gabung_suami",
                "Employee-bpjs_col",
                "Employee-ikut_bpjs_kesehatan",
                "Employee-ikut_bpjs_ketenagakerjaan",
                "Employee-tipe_karyawan",
                "Employee-penghasilan_final"
            ]]
        ]
    },
    {
        "dt": "Salary Component",
        "filters": [
            ["name", "in", [
                "Gaji Pokok",
                "Tunjangan Makan",
                "Tunjangan Transport",
                "Insentif",
                "BPJS Kesehatan",
                "BPJS TK",
                "PPh 21",
                "PPh 21 Correction",
                "Biaya Jabatan"
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
                "Beban Gaji Pokok - %",
                "Beban Tunjangan Makan - %",
                "Beban Tunjangan Transport - %",
                "Beban Insentif - %",
                "Hutang BPJS Kesehatan - %",
                "Hutang BPJS TK - %",
                "Hutang PPh 21 - %"
            ]]
        ]
    }
]

# Default configuration values
# ---------------------------
default_mail_footer = """
<div style="padding: 7px; text-align: center;">
    <p>Powered by <a href="https://erpnext.com" target="_blank">ERPNext</a> & Payroll Indonesia</p>
</div>
"""

# Additional jinja environment globals
# -----------------------------------
jinja = {
    "methods": [
        "payroll_indonesia.payroll_indonesia.utils.get_bpjs_settings",
        "payroll_indonesia.payroll_indonesia.utils.get_ptkp_settings"
    ]
}

# Regional Settings
# ----------------
regional_overrides = {
    "Indonesia": {
        "controller_overrides": {
            "Salary Slip": "payroll_indonesia.override.salary_slip"
        }
    }
}