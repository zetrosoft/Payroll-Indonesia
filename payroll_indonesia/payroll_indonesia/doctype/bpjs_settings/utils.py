

# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-06 18:10:25 by dannyaudian

"""
This module is a compatibility layer that forwards utility functions 
from the central utils module to maintain backward compatibility.
"""

from frappe import _
from payroll_indonesia.payroll_indonesia.utils import (
    get_default_config,
    debug_log,
    find_parent_account,
    create_account,
    create_parent_liability_account,
    create_parent_expense_account,
    retry_bpjs_mapping
)

__all__ = [
    'validate_settings', 
    'setup_accounts',
    'get_default_config',
    'find_parent_account',
    'create_account',
    'create_parent_liability_account',
    'create_parent_expense_account',
    'retry_bpjs_mapping',
    'debug_log'
]

# Validation functions for hooks.py - keep these as they're specific to BPJS Settings
def validate_settings(doc, method=None):
    """Wrapper for BPJSSettings.validate method with protection against recursion"""
    # Skip if already being validated
    if getattr(doc, "_validated", False):
        return
        
    # Mark as being validated to prevent recursion
    doc._validated = True
    
    try:
        # Call the instance methods
        doc.validate_data_types()
        doc.validate_percentages()
        doc.validate_max_salary()
        doc.validate_account_types()
    finally:
        # Always clean up flag
        doc._validated = False
    
def setup_accounts(doc, method=None):
    """Wrapper for BPJSSettings.setup_accounts method with protection against recursion"""
    # Skip if already being processed
    if getattr(doc, "_setup_running", False):
        return
        
    # Mark as being processed to prevent recursion
    doc._setup_running = True
    
    try:
        # Call the instance method
        doc.setup_accounts()
    finally:
        # Always clean up flag
        doc._setup_running = False