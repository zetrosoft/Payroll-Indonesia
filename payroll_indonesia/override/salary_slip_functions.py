# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 07:59:27 by dannyaudian

import frappe
from frappe import _

# Import centralized tax calculation function
from payroll_indonesia.override.salary_slip.tax_calculator import calculate_tax_components

# Import standardized error logging and cache utilities
from payroll_indonesia.utilities.cache_utils import clear_all_caches
from payroll_indonesia.utils import log_error

__all__ = [
    'validate_salary_slip',
    'on_submit_salary_slip',
    'on_cancel_salary_slip',
    'after_insert_salary_slip',
    'clear_caches'
]

def validate_salary_slip(doc, method=None):
    """
    Event hook for validating Salary Slip.
    Handles tax and BPJS calculations with appropriate error handling.
    
    Args:
        doc: The Salary Slip document
        method: Method name (not used)
    """
    try:
        # Initialize default fields if needed
        _initialize_payroll_fields(doc)
        
        # Get employee document
        employee = _get_employee_doc(doc)
        
        # Calculate tax components using centralized function
        calculate_tax_components(doc, employee)
    
    except frappe.ValidationError:
        # Re-raise Frappe Validation Errors to prevent masking
        raise
    
    except Exception as e:
        error_message = _("Could not validate salary slip: {0}").format(str(e))
        log_error(
            "Salary Slip Validation Error",
            error_message,
            doc.name if hasattr(doc, 'name') else 'New',
            with_traceback=True
        )
        frappe.throw(error_message)

def on_submit_salary_slip(doc, method=None):
    """
    Event hook for Salary Slip submission.
    Updates related tax and benefit documents.
    
    Args:
        doc: The Salary Slip document
        method: Method name (not used)
    """
    # Konsistensi: gunakan string literal untuk nama komponen
    BPJS_COMPONENTS = ["BPJS JHT Employee", "BPJS JP Employee", "BPJS Kesehatan Employee"]
    
    try:
        # Verify settings for TER if using TER method
        if doc.is_using_ter:  # Gunakan akses properti langsung
            if not doc.ter_category: # Gunakan akses properti langsung
                frappe.msgprint(_("Warning: Using TER but no category set"), indicator="yellow")
            if not doc.ter_rate: # Gunakan akses properti langsung
                frappe.msgprint(_("Warning: Using TER but no rate set"), indicator="yellow")
        
        # Update tax summary document if needed
        # This functionality can be expanded as needed
    
    except frappe.ValidationError:
        # Biarkan validasi error dari Frappe naik
        raise
    
    except Exception as e:
        error_message = _("Error processing salary slip submission: {0}").format(str(e))
        log_error(
            "Salary Slip Submit Error",
            error_message,
            doc.name,
            with_traceback=True
        )
        frappe.throw(error_message)

def on_cancel_salary_slip(doc, method=None):
    """
    Event hook for Salary Slip cancellation.
    Reverts related document changes.
    
    Args:
        doc: The Salary Slip document
        method: Method name (not used)
    """
    try:
        # Revert changes to tax summary if needed
        # This functionality can be expanded as needed
        pass
    
    except frappe.ValidationError:
        # Biarkan validasi error dari Frappe naik
        raise
    
    except Exception as e:
        error_message = _("Error processing salary slip cancellation: {0}").format(str(e))
        log_error(
            "Salary Slip Cancel Error",
            error_message,
            doc.name,
            with_traceback=True
        )
        frappe.throw(error_message)

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
        
        # Initialize tax ID fields
        set_tax_ids_from_employee(doc)
    
    except frappe.ValidationError:
        # Biarkan validasi error dari Frappe naik
        raise
    
    except Exception as e:
        error_message = _("Error in post-creation processing: {0}").format(str(e))
        log_error(
            "Salary Slip Post-Creation Error",
            error_message,
            doc.name if hasattr(doc, 'name') else 'New',
            with_traceback=True
        )
        frappe.msgprint(_("Warning: {0}").format(error_message))

def _initialize_payroll_fields(doc):
    """
    Initialize additional payroll fields with default values.
    Ensures all required fields exist with proper default values.
    
    Args:
        doc: The Salary Slip document
    """
    defaults = {
        'biaya_jabatan': 0,
        'netto': 0,
        'total_bpjs': 0,
        'is_using_ter': 0,
        'ter_rate': 0,
        'ter_category': "",
        'koreksi_pph21': 0,
        'payroll_note': "",
        'npwp': "",
        'ktp': "",
        'is_final_gabung_suami': 0,
        'monthly_gross_for_ter': 0,
        'annual_taxable_amount': 0
    }
    
    # Set defaults for fields that don't exist or are None
    for field, default in defaults.items():
        if not hasattr(doc, field) or getattr(doc, field) is None:
            doc.set(field, default)

def _get_employee_doc(doc):
    """
    Retrieves the complete Employee document for the current salary slip.
    
    Args:
        doc: The Salary Slip document
        
    Returns:
        frappe.Document: The employee document
        
    Raises:
        frappe.ValidationError: If employee cannot be found or retrieved
    """
    if not doc.employee:  # Simplified condition
        frappe.throw(_("Salary Slip must have an employee assigned"))
        
    try:
        return frappe.get_doc("Employee", doc.employee)
    except frappe.DoesNotExistError:
        frappe.throw(_("Employee {0} not found").format(doc.employee))
    except Exception as e:
        frappe.throw(_("Could not retrieve Employee {0}: {1}").format(doc.employee, str(e)))

def set_tax_ids_from_employee(doc):
    """
    Set tax ID fields (NPWP, KTP) from employee record
    
    Args:
        doc: The Salary Slip document
    """
    if not doc.employee:  # Simplified condition
        return
        
    employee = frappe.get_doc("Employee", doc.employee) # Load employee doc
    
    # Set NPWP and KTP from employee if they're not already set
    if hasattr(doc, 'npwp') and not doc.npwp:
        doc.npwp = employee.npwp if hasattr(employee, "npwp") else ""
        
    if hasattr(doc, 'ktp') and not doc.ktp:
        doc.ktp = employee.ktp if hasattr(employee, "ktp") else ""

def clear_caches():
    """
    Clear all caches related to salary slip and tax calculations.
    This function is used by scheduler events and can be called manually.
    """
    try:
        # Use the centralized cache clearing function
        clear_all_caches()
        frappe.logger().info("Salary slip caches cleared successfully")
        return {"status": "success", "message": "All caches cleared successfully"}
    except Exception as e:
        frappe.logger().error(f"Error clearing caches: {str(e)}")
        return {"status": "error", "message": f"Error clearing caches: {str(e)}"}