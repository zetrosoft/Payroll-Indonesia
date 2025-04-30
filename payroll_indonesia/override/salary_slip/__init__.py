# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-30 08:05:35 by dannyaudiandesk

# Import directly from the controller module
from .controller import IndonesiaPayrollSalarySlip
from .controller import (
    setup_fiscal_year_if_missing,
    process_salary_slips_batch,
    check_fiscal_year_setup,
    clear_caches
)

# Import the debug_log function from the bpjs_calculator module
# to solve the circular import issue
from payroll_indonesia.calculations.bpjs_calculator import debug_log

# Export for direct imports
__all__ = [
    'IndonesiaPayrollSalarySlip',
    'setup_fiscal_year_if_missing',
    'process_salary_slips_batch',
    'check_fiscal_year_setup',
    'clear_caches',
    'debug_log'
]

# Note: We're importing debug_log directly from bpjs_calculator
# to prevent circular import issues between salary_slip and salary_slip_functions
