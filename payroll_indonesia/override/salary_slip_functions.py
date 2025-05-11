# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 04:14:53 by dannyaudian

import frappe
from frappe import _
import traceback

# Import the controller class
from payroll_indonesia.override.salary_slip import IndonesiaPayrollSalarySlip

__all__ = [
    'validate_salary_slip',
    'on_submit_salary_slip',
    'on_cancel_salary_slip',
    'after_insert_salary_slip',
    'log_error',
    'raise_user_error'
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
    Delegates to validate() method of the document
    
    Args:
        doc: The Salary Slip document
        method: Method name (not used)
    """
    try:
        # Call validate method
        doc.validate()
    except Exception as e:
        # Log technical error details
        log_error(
            f"Salary Slip Validation Error: {doc.name if hasattr(doc, 'name') else 'New'}",
            e
        )
        # Raise user-friendly message
        raise_user_error(f"Could not validate salary slip: {str(e)}")

def on_submit_salary_slip(doc, method=None):
    """
    Event hook for Salary Slip submission.
    Delegates to on_submit() method of the document
    
    Args:
        doc: The Salary Slip document
        method: Method name (not used)
    """
    try:
        # Check if method exists
        if hasattr(doc, 'on_submit'):
            doc.on_submit()
    except Exception as e:
        # Log technical error details
        log_error(
            f"Salary Slip Submit Error: {doc.name}",
            e
        )
        # Raise user-friendly message
        raise_user_error(f"Error processing salary slip submission: {str(e)}")

def on_cancel_salary_slip(doc, method=None):
    """
    Event hook for Salary Slip cancellation.
    Delegates to on_cancel() method of the document
    
    Args:
        doc: The Salary Slip document
        method: Method name (not used)
    """
    try:
        # Check if method exists
        if hasattr(doc, 'on_cancel'):
            doc.on_cancel()
    except Exception as e:
        # Log technical error details
        log_error(
            f"Salary Slip Cancel Error: {doc.name}",
            e
        )
        # Raise user-friendly message
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
        if not hasattr(doc, 'doctype') or doc.doctype != "Salary Slip":
            return
        
        # Initialize custom fields for Indonesian payroll
        initialize_indonesian_payroll_fields(doc)
        
        # Set tax ID fields from employee
        set_tax_ids_from_employee(doc)
            
    except Exception as e:
        # Log technical error details but don't block slip creation
        log_error(
            f"Salary Slip Post-Creation Error: {doc.name if hasattr(doc, 'name') else 'New'}",
            e
        )
        # Show warning instead of blocking error
        frappe.msgprint(_("Warning: Error in post-creation processing: {0}").format(str(e)))

def initialize_indonesian_payroll_fields(doc):
    """
    Initialize custom Indonesian payroll fields on the document
    
    Args:
        doc: The Salary Slip document
    """
    # Define default fields
    default_fields = {
        'is_final_gabung_suami': 0,
        'koreksi_pph21': 0,
        'payroll_note': "",
        'biaya_jabatan': 0,
        'netto': 0,
        'total_bpjs': 0,
        'is_using_ter': 0,
        'ter_rate': 0,
        'ter_category': ""
    }
    
    # Set default values for fields if they don't exist
    for field, default_value in default_fields.items():
        if not hasattr(doc, field) or getattr(doc, field) is None:
            setattr(doc, field, default_value)
            # Update the database
            try:
                doc.db_set(field, default_value, update_modified=False)
            except Exception:
                # Some fields might not be in the database schema, ignore those errors
                pass

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