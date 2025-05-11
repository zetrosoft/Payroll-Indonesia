# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 03:56:22 by dannyaudian

import frappe
from frappe import _

def before_validate(doc, method=None):
    """
    Event hook that runs before validating a Payroll Entry document.
    This hook delegates to the CustomPayrollEntry class methods.
    
    Args:
        doc: The Payroll Entry document instance
        method: The method being called (not used)
    """
    # Delegate to the CustomPayrollEntry's before_validate method
    # CustomPayrollEntry handles all validation logic internally
    if hasattr(doc, 'before_validate') and callable(doc.before_validate):
        doc.before_validate()