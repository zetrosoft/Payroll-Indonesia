# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 04:03:35 by dannyaudian

import frappe
from frappe import _

# Import the controller class
from payroll_indonesia.override.salary_slip import IndonesiaPayrollSalarySlip

__all__ = [
    'validate_salary_slip',
    'on_submit_salary_slip',
    'on_cancel_salary_slip',
    'after_insert_salary_slip'
]

def validate_salary_slip(doc, method=None):
    """
    Event hook for validating Salary Slip.
    Delegates to IndonesiaPayrollSalarySlip.validate()
    
    Args:
        doc: The Salary Slip document
        method: Method name (not used)
    """
    try:
        # Check if doc is already an instance of IndonesiaPayrollSalarySlip
        if isinstance(doc, IndonesiaPayrollSalarySlip):
            doc.validate()
        else:
            # For standard SalarySlip instances, create a temp IndonesiaPayrollSalarySlip
            # to handle validation
            temp = IndonesiaPayrollSalarySlip(doc.as_dict())
            temp.validate()
            
            # Copy validated values back to original document
            for field in temp.as_dict():
                if hasattr(doc, field) and field not in ['owner', 'creation', 'modified', 'doctype']:
                    try:
                        setattr(doc, field, getattr(temp, field))
                    except Exception:
                        pass
    except Exception as e:
        frappe.log_error(
            f"Error in validate_salary_slip for {doc.name if hasattr(doc, 'name') else 'New Salary Slip'}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Salary Slip Validation Error"
        )
        frappe.throw(_("Error validating salary slip: {0}").format(str(e)))

def on_submit_salary_slip(doc, method=None):
    """
    Event hook for Salary Slip submission.
    Delegates to IndonesiaPayrollSalarySlip.on_submit()
    
    Args:
        doc: The Salary Slip document
        method: Method name (not used)
    """
    try:
        if isinstance(doc, IndonesiaPayrollSalarySlip):
            # If already the right class, just call on_submit
            doc.on_submit()
        else:
            # Otherwise, create temporary instance and call its method
            temp = IndonesiaPayrollSalarySlip(doc.as_dict())
            temp.on_submit()
            
            # Copy any values that might have been updated
            for field in ['payroll_note']:
                if hasattr(temp, field):
                    setattr(doc, field, getattr(temp, field))
    except Exception as e:
        frappe.log_error(
            f"Error in on_submit_salary_slip for {doc.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Salary Slip Submit Error"
        )
        frappe.throw(_("Error processing salary slip submission: {0}").format(str(e)))

def on_cancel_salary_slip(doc, method=None):
    """
    Event hook for Salary Slip cancellation.
    Delegates to IndonesiaPayrollSalarySlip.on_cancel()
    
    Args:
        doc: The Salary Slip document
        method: Method name (not used)
    """
    try:
        if isinstance(doc, IndonesiaPayrollSalarySlip):
            # If already the right class, just call on_cancel
            doc.on_cancel()
        else:
            # Otherwise, create temporary instance and call its method
            temp = IndonesiaPayrollSalarySlip(doc.as_dict())
            temp.on_cancel()
            
            # Copy any values that might have been updated
            for field in ['payroll_note']:
                if hasattr(temp, field):
                    setattr(doc, field, getattr(temp, field))
                    
    except Exception as e:
        frappe.log_error(
            f"Error in on_cancel_salary_slip for {doc.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
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
        # Initialize custom fields using the controller class
        if isinstance(doc, IndonesiaPayrollSalarySlip):
            # If already using the extended class, just initialize fields
            if hasattr(doc, '_initialize_payroll_fields'):
                doc._initialize_payroll_fields()
        else:
            # For documents not using the extended class, use a temporary instance
            temp = IndonesiaPayrollSalarySlip(doc.as_dict())
            if hasattr(temp, '_initialize_payroll_fields'):
                temp._initialize_payroll_fields()
                
                # Copy initialized fields back to the original doc
                for field in ['is_final_gabung_suami', 'koreksi_pph21', 'payroll_note', 
                            'biaya_jabatan', 'netto', 'total_bpjs', 'is_using_ter', 
                            'ter_rate', 'ter_category']:
                    if hasattr(temp, field):
                        setattr(doc, field, getattr(temp, field))
                        
            # Set doctype-specific values
            if hasattr(doc, 'doctype') and doc.doctype == "Salary Slip":
                # These are set after insert since they can't be set during validation
                if hasattr(doc, 'npwp') and not doc.npwp:
                    # Fetch NPWP from employee if available
                    employee_npwp = frappe.db.get_value("Employee", doc.employee, "npwp")
                    if employee_npwp:
                        doc.db_set('npwp', employee_npwp, update_modified=False)
                        
                if hasattr(doc, 'ktp') and not doc.ktp:
                    # Fetch KTP from employee if available
                    employee_ktp = frappe.db.get_value("Employee", doc.employee, "ktp")
                    if employee_ktp:
                        doc.db_set('ktp', employee_ktp, update_modified=False)
                        
    except Exception as e:
        # Log but don't throw to prevent blocking slip creation
        frappe.log_error(
            f"Error in after_insert_salary_slip for {doc.name if hasattr(doc, 'name') else 'unknown salary slip'}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Salary Slip Hook Error"
        )
        frappe.msgprint(_("Warning: Error in post-creation processing: {0}").format(str(e)))