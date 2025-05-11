# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 09:39:53 by dannyaudian

"""
Constants for Payroll Indonesia module.
This file centralizes magic numbers and other constants used throughout the codebase.
"""

# Time constants (in seconds)
THIRTY_MIN = 1800
ONE_HOUR = 3600
ONE_DAY = 86400

# Calendar constants
MONTHS_PER_YEAR = 12
DAYS_PER_MONTH = 30  # Standard calculation month
MAX_WORKING_DAYS = 22
DEFAULT_WORKING_HOURS = 8
DECEMBER_MONTH = 12

# Currency rounding
CURRENCY_PRECISION = 2
PERCENTAGE_PRECISION = 2

# Thresholds
TAX_DETECTION_THRESHOLD = 100000000  # 100 million rupiah
ANNUAL_DETECTION_FACTOR = 3  # If gross pay > 3x total earnings, likely annual
SALARY_BASIC_FACTOR = 10  # If gross pay > 10x basic salary, likely annual
MAX_DATE_DIFF = 31  # Maximum acceptable difference (in days) between dates

# Default values
DEFAULT_UMR = 4900000  # Jakarta UMR as default
DEFAULT_MEAL_ALLOWANCE = 750000
DEFAULT_TRANSPORT_ALLOWANCE = 900000
DEFAULT_POSITION_ALLOWANCE_PERCENT = 7.5
DEFAULT_BASIC_SALARY_PERCENT = 75

# BPJS default rates
BPJS_KESEHATAN_EMPLOYEE_PERCENT = 1.0
BPJS_KESEHATAN_EMPLOYER_PERCENT = 4.0
BPJS_KESEHATAN_MAX_SALARY = 12000000
BPJS_JHT_EMPLOYEE_PERCENT = 2.0
BPJS_JHT_EMPLOYER_PERCENT = 3.7
BPJS_JP_EMPLOYEE_PERCENT = 1.0
BPJS_JP_EMPLOYER_PERCENT = 2.0
BPJS_JP_MAX_SALARY = 9077600
BPJS_JKK_PERCENT = 0.24
BPJS_JKM_PERCENT = 0.3

# Tax constants
BIAYA_JABATAN_PERCENT = 5.0
BIAYA_JABATAN_MAX = 500000
TER_MAX_RATE = 34.0  # Highest TER rate is 34% for all categories per PMK 168/2023

# Cache lifetimes (in seconds)
CACHE_BRIEF = 300       # 5 minutes
CACHE_SHORT = 1800      # 30 minutes
CACHE_MEDIUM = 3600     # 1 hour
CACHE_LONG = 86400      # 1 day
CACHE_EXTENDED = 604800 # 1 week

# Log sizes
MAX_LOG_LENGTH = 500

# Valid tax status codes
VALID_TAX_STATUS = ["TK0", "TK1", "TK2", "TK3", "K0", "K1", "K2", "K3", "HB0", "HB1", "HB2", "HB3"]

# TER Categories
TER_CATEGORY_A = "TER A"
TER_CATEGORY_B = "TER B" 
TER_CATEGORY_C = "TER C"
TER_CATEGORIES = [TER_CATEGORY_A, TER_CATEGORY_B, TER_CATEGORY_C]

# Default BPJS rates as dictionary (for backwards compatibility)
DEFAULT_BPJS_RATES = {
    "kesehatan_employee_percent": BPJS_KESEHATAN_EMPLOYEE_PERCENT,
    "kesehatan_employer_percent": BPJS_KESEHATAN_EMPLOYER_PERCENT,
    "kesehatan_max_salary": BPJS_KESEHATAN_MAX_SALARY,
    "jht_employee_percent": BPJS_JHT_EMPLOYEE_PERCENT,
    "jht_employer_percent": BPJS_JHT_EMPLOYER_PERCENT,
    "jp_employee_percent": BPJS_JP_EMPLOYEE_PERCENT,
    "jp_employer_percent": BPJS_JP_EMPLOYER_PERCENT,
    "jp_max_salary": BPJS_JP_MAX_SALARY,
    "jkk_percent": BPJS_JKK_PERCENT,
    "jkm_percent": BPJS_JKM_PERCENT
}