# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 05:51:22 by dannyaudian

import frappe
from frappe import _
import traceback

# Import the controller class
from payroll_indonesia.override.salary_slip import IndonesiaPayrollSalarySlip

# Import centralized cache utilities
from payroll_indonesia.utilities.cache_utils import clear_all_caches, schedule_cache_clearing

__all__ = [
    'validate_salary_slip',
    'on_submit_salary_slip',
    'on_cancel_salary_slip',
    'after_insert_salary_slip',
    'log_error',
    'raise_user_error',
    'clear_caches'
]

# Utility functions for standardized error handling
def log_error(title, error):
    """
    Log detailed error information for developers
    
    Args:
        title (str): Title for the error log
        error (Exception): The exception object
    """
    error_message = f"{str(error)}\n\nTraceback: {traceback.format_exc()}"
    frappe.log_error(error_message, title)

def raise_user_error(message):
    """
    Raise a user-friendly validation error
    
    Args:
        message (str): Clear message for the end user
        
    Raises:
        frappe.ValidationError: With the provided message
    """
    frappe.throw(_(message))

def validate_salary_slip(doc, method=None):
    """
    Event hook for validating Salary Slip.
    Since we're using monkey-patching, this function is a lightweight wrapper
    that delegates to the SalarySlip's validate method which has been enhanced.
    
    Args:
        doc: The Salary Slip document
        method: Method name (not used)
    """
    try:
        # The validate method itself has been monkey-patched, so just call it
        # The monkey-patching in extend_salary_slip_functionality will handle the rest
        if hasattr(doc, 'validate'):
            doc.validate()
    except Exception as e:
        log_error(f"Salary Slip Validation Error: {doc.name if hasattr(doc, 'name') else 'New'}", e)
        raise_user_error(f"Could not validate salary slip: {str(e)}")

def on_submit_salary_slip(doc, method=None):
    """
    Event hook for Salary Slip submission.
    Since we're using monkey-patching, this is a lightweight wrapper.
    
    Args:
        doc: The Salary Slip document
        method: Method name (not used)
    """
    try:
        # The on_submit method has been monkey-patched, so just call it
        # The monkey-patching in extend_salary_slip_functionality will handle the rest
        if hasattr(doc, 'on_submit'):
            doc.on_submit()
    except Exception as e:
        log_error(f"Salary Slip Submit Error: {doc.name}", e)
        raise_user_error(f"Error processing salary slip submission: {str(e)}")

def on_cancel_salary_slip(doc, method=None):
    """
    Event hook for Salary Slip cancellation.
    Since we're using monkey-patching, this is a lightweight wrapper.
    
    Args:
        doc: The Salary Slip document
        method: Method name (not used)
    """
    try:
        # The on_cancel method has been monkey-patched, so just call it
        # The monkey-patching in extend_salary_slip_functionality will handle the rest
        if hasattr(doc, 'on_cancel'):
            doc.on_cancel()
    except Exception as e:
        log_error(f"Salary Slip Cancel Error: {doc.name}", e)
        raise_user_error(f"Error processing salary slip cancellation: {str(e)}")

def after_insert_salary_slip(doc, method=None):
    """
    Event hook that runs after a Salary Slip is created.
    Initializes custom fields required for Indonesian payroll.
    
    Args:
        doc: The Salary Slip document
        method: Method name (not used)
    """
    try:
        # Handle initialization only for Salary Slip documents
        if doc.doctype != "Salary Slip":
            return
        
        # Initialize tax ID fields - minimal initialization since monkey patching handles the rest
        set_tax_ids_from_employee(doc)
            
    except Exception as e:
        log_error(f"Salary Slip Post-Creation Error: {doc.name if hasattr(doc, 'name') else 'New'}", e)
        frappe.msgprint(_("Warning: Error in post-creation processing: {0}").format(str(e)))

def set_tax_ids_from_employee(doc):
    """
    Set tax ID fields (NPWP, KTP) from employee record
    
    Args:
        doc: The Salary Slip document
    """
    if not hasattr(doc, 'employee') or not doc.employee:
        return
        
    # Get NPWP and KTP from employee if they're not already set
    if hasattr(doc, 'npwp') and not doc.npwp:
        employee_npwp = frappe.db.get_value("Employee", doc.employee, "npwp")
        if employee_npwp:
            doc.db_set('npwp', employee_npwp, update_modified=False)
            
    if hasattr(doc, 'ktp') and not doc.ktp:
        employee_ktp = frappe.db.get_value("Employee", doc.employee, "ktp")
        if employee_ktp:
            doc.db_set('ktp', employee_ktp, update_modified=False)

def clear_caches():
    """
    Clear all caches related to salary slip and tax calculations.
    This function is used by scheduler events and can be called manually.
    """
    try:
        # Use the centralized cache clearing function
        clear_all_caches()
        
        # Schedule next cache clear in 30 minutes
        schedule_cache_clearing(minutes=30)
        
        frappe.logger().info("Salary slip caches cleared successfully")
        return {"status": "success", "message": "All caches cleared successfully"}
    except Exception as e:
        frappe.logger().error(f"Error clearing caches: {str(e)}")
        return {"status": "error", "message": f"Error clearing caches: {str(e)}"}