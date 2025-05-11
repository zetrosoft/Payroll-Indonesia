# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 08:16:21 by dannyaudian

import frappe
from frappe import _

# Import centralized tax calculation function
from payroll_indonesia.override.salary_slip.tax_calculator import calculate_tax_components

# Import standardized error logging and cache utilities
from payroll_indonesia.utilities.cache_utils import clear_all_caches, schedule_cache_clearing
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
        
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # Critical validation error - log and throw
        frappe.log_error(
            "Error validating salary slip {0}: {1}".format(
                doc.name if hasattr(doc, 'name') else 'New', str(e)
            ),
            "Salary Slip Validation Error"
        )
        frappe.throw(_("Could not validate salary slip: {0}").format(str(e)))

def on_submit_salary_slip(doc, method=None):
    """
    Event hook for Salary Slip submission.
    Updates related tax and benefit documents.
    
    Args:
        doc: The Salary Slip document
        method: Method name (not used)
    """
    try:
        # Verify settings for TER if using TER method
        if getattr(doc, "is_using_ter", 0):
            # Verify TER category is set - warning only
            if not getattr(doc, "ter_category", ""):
                frappe.log_error(
                    "Using TER but no category set for {0}".format(doc.name),
                    "TER Warning"
                )
                frappe.msgprint(
                    _("Warning: Using TER but no category set"),
                    indicator="orange"
                )
                
            # Verify TER rate is set - warning only
            if not getattr(doc, "ter_rate", 0):
                frappe.log_error(
                    "Using TER but no rate set for {0}".format(doc.name),
                    "TER Warning"
                )
                frappe.msgprint(
                    _("Warning: Using TER but no rate set"),
                    indicator="orange"
                )
        
        # Update tax summary document if needed
        # This functionality can be expanded as needed
        
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # Critical submission error - log and throw
        frappe.log_error(
            "Error processing salary slip submission for {0}: {1}".format(doc.name, str(e)),
            "Salary Slip Submit Error"
        )
        frappe.throw(_("Error processing salary slip submission: {0}").format(str(e)))

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
        
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # Critical cancellation error - log and throw
        frappe.log_error(
            "Error processing salary slip cancellation for {0}: {1}".format(doc.name, str(e)),
            "Salary Slip Cancel Error"
        )
        frappe.throw(_("Error processing salary slip cancellation: {0}").format(str(e)))

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
            
    except Exception as e:
        # Non-critical post-creation error - log and continue
        frappe.log_error(
            "Error in post-creation processing for {0}: {1}".format(
                doc.name if hasattr(doc, 'name') else 'New', str(e)
            ),
            "Salary Slip Post-Creation Error"
        )
        frappe.msgprint(
            _("Warning: Error during post-creation processing: {0}").format(str(e)),
            indicator="orange"
        )

def _initialize_payroll_fields(doc):
    """
    Initialize additional payroll fields with default values.
    Ensures all required fields exist with proper default values.
    
    Args:
        doc: The Salary Slip document
    """
    try:
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
        }
        
        # Set defaults for fields that don't exist or are None
        for field, default in defaults.items():
            if not hasattr(doc, field) or getattr(doc, field) is None:
                setattr(doc, field, default)
                
    except Exception as e:
        # Non-critical error during initialization - log and continue
        frappe.log_error(
            "Error initializing payroll fields for {0}: {1}".format(
                doc.name if hasattr(doc, 'name') else 'New', str(e)
            ),
            "Field Initialization Error"
        )
        frappe.msgprint(
            _("Warning: Error initializing payroll fields: {0}").format(str(e)),
            indicator="orange"
        )

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
    if not hasattr(doc, 'employee') or not doc.employee:
        # Critical validation error - employee is required
        frappe.throw(
            _("Salary Slip must have an employee assigned"),
            title=_("Missing Employee")
        )
        
    try:
        return frappe.get_doc("Employee", doc.employee)
    except Exception as e:
        # Critical validation error - employee must exist
        frappe.log_error(
            "Error retrieving Employee {0} for salary slip {1}: {2}".format(
                doc.employee, doc.name if hasattr(doc, 'name') else 'New', str(e)
            ),
            "Employee Retrieval Error"
        )
        frappe.throw(
            _("Could not retrieve Employee {0}: {1}").format(doc.employee, str(e)),
            title=_("Employee Not Found")
        )

def set_tax_ids_from_employee(doc):
    """
    Set tax ID fields (NPWP, KTP) from employee record
    
    Args:
        doc: The Salary Slip document
    """
    try:
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
                
    except Exception as e:
        # Non-critical error - log and continue
        frappe.log_error(
            "Error setting tax IDs from employee for {0}: {1}".format(
                doc.name if hasattr(doc, 'name') else 'New', str(e)
            ),
            "Tax ID Setting Error"
        )
        frappe.msgprint(
            _("Warning: Could not set tax IDs from employee record: {0}").format(str(e)),
            indicator="orange"
        )

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
        
        # Use standard log_error for consistency
        frappe.log_error(
            "Salary slip caches cleared successfully",
            "Cache Clearing Success"
        )
        return {"status": "success", "message": "All caches cleared successfully"}
        
    except Exception as e:
        # Non-critical error during cache clearing - log and return error
        frappe.log_error(
            "Error clearing caches: {0}".format(str(e)),
            "Cache Clearing Error"
        )
        return {"status": "error", "message": "Error clearing caches: {0}".format(str(e))}