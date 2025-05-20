# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-01 11:08:53 by dannyaudian

# Import directly from the controller module
from .controller import (
    IndonesiaPayrollSalarySlip,
    setup_fiscal_year_if_missing,
    process_salary_slips_batch,
    check_fiscal_year_setup,
    clear_caches,
    get_component,
    set_component,
)

# Export for direct imports
__all__ = [
    "IndonesiaPayrollSalarySlip",
    "setup_fiscal_year_if_missing",
    "process_salary_slips_batch",
    "check_fiscal_year_setup",
    "clear_caches",
    "get_component",
    "set_component",
]

# Note: This module is used to initialize the Payroll Indonesia salary slip processing components
