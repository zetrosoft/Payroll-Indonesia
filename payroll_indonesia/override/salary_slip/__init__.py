# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-30 10:42:45 by dannyaudian

# Import directly from the controller module
from .controller import (
    IndonesiaPayrollSalarySlip,
    setup_fiscal_year_if_missing,
    process_salary_slips_batch,
    check_fiscal_year_setup,
    clear_caches,
    get_component,
    set_component
)

# Import debug_log from bpjs_calculator to prevent circular imports
from payroll_indonesia.override.salary_slip.bpjs_calculator import debug_log

# Export for direct imports
__all__ = [
    'IndonesiaPayrollSalarySlip',
    'setup_fiscal_year_if_missing',
    'process_salary_slips_batch',
    'check_fiscal_year_setup',
    'clear_caches',
    'debug_log',
    'get_component',
    'set_component'
]

# Note: We're importing debug_log directly from bpjs_calculator to prevent circular imports