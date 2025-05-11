# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 08:11:32 by dannyaudian

import frappe
from frappe import _

def before_validate(doc, method=None):
    """
    Event hook that runs before validating a Payroll Entry document.
    This file is retained only for backward-compatible hook registration.
    
    Since all validation logic has been centralized in CustomPayrollEntry class,
    this simply calls doc.validate() to ensure proper validation flow.
    
    This file can be safely removed in future versions once all hooks
    are updated to use CustomPayrollEntry directly.
    
    Args:
        doc: The Payroll Entry document instance
        method: The method being called (not used)
    """
    try:
        # Call validate() which contains all centralized validation logic
        if hasattr(doc, 'validate') and callable(doc.validate):
            doc.validate()
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # Log unexpected errors
        frappe.log_error(
            "Error in before_validate hook for Payroll Entry {0}: {1}".format(
                doc.name if hasattr(doc, 'name') else 'New', str(e)
            ),
            "Payroll Entry Hook Error"
        )
        # This is not a user-initiated action, so throw to prevent silent failures
        frappe.throw(_("Error in payroll entry validation hook: {0}").format(str(e)))