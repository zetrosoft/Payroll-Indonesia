# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

__version__ = "0.0.1"

# Explicitly import and expose key functions from salary_slip module
# This ensures they're accessible through the payroll_indonesia.override package
try:
    from .salary_slip import (
        clear_salary_slip_caches,
        setup_fiscal_year_if_missing,
        check_fiscal_year_setup,
        extend_salary_slip_functionality
    )
    
    __all__ = [
        'clear_salary_slip_caches',
        'setup_fiscal_year_if_missing',
        'check_fiscal_year_setup',
        'extend_salary_slip_functionality'
    ]
except ImportError:
    import frappe
    frappe.log_error("Failed to import functions from salary_slip module in override/__init__.py",
                    "Module Import Error")
