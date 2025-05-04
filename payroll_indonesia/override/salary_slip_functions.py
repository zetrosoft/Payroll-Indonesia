# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-04 00:40:01 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate, cint, now_datetime

# Import debug_log directly from bpjs_calculator to avoid circular imports
from payroll_indonesia.override.salary_slip.bpjs_calculator import debug_log

# Import other functions from salary_slip
from payroll_indonesia.override.salary_slip.controller import IndonesiaPayrollSalarySlip
from payroll_indonesia.override.salary_slip import setup_fiscal_year_if_missing

# Constants
MAX_ERROR_MESSAGE_LENGTH = 140

# Validation functions for salary slip
def validate_salary_slip(doc, method=None):
    """Additional validation for salary slip with improved error handling"""
    try:
        # Validate employee is specified
        if not doc.employee:
            frappe.throw(_("Employee is mandatory for Salary Slip"))
        
        # Initialize custom fields - use the function from salary_slip.py
        if isinstance(doc, IndonesiaPayrollSalarySlip):
            doc.initialize_payroll_fields()
        else:
            # If not the extended class, we need to initialize manually
            # by creating a temporary instance and using its method
            temp = IndonesiaPayrollSalarySlip(doc.as_dict())
            temp.initialize_payroll_fields()
            # Copy values back to original doc
            for field in ['is_final_gabung_suami', 'koreksi_pph21', 'payroll_note', 
                          'biaya_jabatan', 'netto', 'total_bpjs', 'is_using_ter', 
                          'ter_rate']:
                if hasattr(temp, field):
                    setattr(doc, field, getattr(temp, field))
        
        # Validate required DocTypes and settings exist
        validate_dependent_doctypes()
        
        # Check if all required components exist in salary slip
        validate_required_components(doc)
        
    except Exception as e:
        log_error(
            f"Salary Slip Validation Error for {doc.name if hasattr(doc, 'name') else 'New Salary Slip'}: {str(e)}",
            "Salary Slip Validation Error"
        )
        frappe.throw(_("Error validating salary slip: {0}").format(str(e)))

def validate_dependent_doctypes():
    """Check if all dependent DocTypes and settings exist"""
    try:
        # Check BPJS Settings
        if not frappe.db.exists("DocType", "BPJS Settings"):
            frappe.throw(_("BPJS Settings DocType not found. Please make sure Payroll Indonesia is properly installed."))
            
        # Check if BPJS Settings document exists
        if not frappe.db.exists("BPJS Settings", "BPJS Settings"):
            frappe.throw(_("BPJS Settings document not configured. Please create BPJS Settings first."))
            
        # Check PPh 21 Settings
        if not frappe.db.exists("DocType", "PPh 21 Settings"):
            frappe.throw(_("PPh 21 Settings DocType not found. Please make sure Payroll Indonesia is properly installed."))
            
        # Check if PPh 21 Settings document exists
        if not frappe.db.exists("PPh 21 Settings", "PPh 21 Settings"):
            frappe.throw(_("PPh 21 Settings document not configured. Please create PPh 21 Settings first."))
            
        # Check required dependent DocTypes
        required_doctypes = [
            "Employee Tax Summary",
            "BPJS Payment Summary"
        ]
        
        for doctype in required_doctypes:
            if not frappe.db.exists("DocType", doctype):
                frappe.throw(_("{0} DocType not found. Please make sure Payroll Indonesia is properly installed.").format(doctype))
                
    except Exception as e:
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
        log_error(
            f"Error validating dependent DocTypes: {str(e)}",
            "Dependent DocType Validation Error"
        )
        frappe.throw(_("Error validating dependent DocTypes: {0}").format(str(e)))

def validate_required_components(doc):
    """Check if all required components exist in the salary slip"""
    try:
        required_components = {
            "earnings": ["Gaji Pokok"],
            "deductions": [
                "BPJS JHT Employee",
                "BPJS JP Employee", 
                "BPJS Kesehatan Employee",
                "PPh 21"
            ]
        }
        
        # First check if all required components exist in the system
        missing_components = []
        for component_type, components in required_components.items():
            for component in components:
                if not frappe.db.exists("Salary Component", component):
                    missing_components.append(component)
                    
        if missing_components:
            frappe.throw(_("Required salary components not found in the system: {0}").format(
                ", ".join(missing_components)
            ))
        
        # Then check if all required components are in the salary slip
        for component_type, components in required_components.items():
            if not hasattr(doc, component_type) or not getattr(doc, component_type):
                frappe.throw(_("Salary slip doesn't have {0}").format(component_type))
                
            components_in_slip = [d.salary_component for d in getattr(doc, component_type)]
            for component in components:
                if component not in components_in_slip:
                    # Add the missing component
                    try:
                        # Get abbr from component
                        component_doc = frappe.get_doc("Salary Component", component)
                        
                        # Create a new row
                        doc.append(component_type, {
                            "salary_component": component,
                            "abbr": component_doc.salary_component_abbr,
                            "amount": 0
                        })
                        
                        frappe.msgprint(_("Added missing component: {0}").format(component))
                    except Exception as e:
                        log_error(
                            f"Error adding component {component}: {str(e)}",
                            "Component Addition Error"
                        )
                        frappe.throw(_("Error adding component {0}: {1}").format(component, str(e)))
                        
    except Exception as e:
        log_error(
            f"Error validating required components: {str(e)}",
            "Component Validation Error"
        )
        frappe.throw(_("Error validating required salary components: {0}").format(str(e)))

def on_submit_salary_slip(doc, method=None):
    """Actions after salary slip is submitted"""
    try:
        # Updates will be handled in salary_slip.py IndonesiaPayrollSalarySlip.on_submit
        # Just log the event
        debug_log(f"on_submit_salary_slip hook triggered for {doc.name}", employee=getattr(doc, 'employee', 'unknown'))
        
        # Add note to the doc's payroll_note field if it exists
        if hasattr(doc, 'payroll_note'):
            timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
            doc.payroll_note += f"\n[{timestamp}] Salary slip submitted via hook."
            doc.db_set('payroll_note', doc.payroll_note, update_modified=False)
            
    except Exception as e:
        log_error(
            f"Error in on_submit_salary_slip for {doc.name}: {str(e)}",
            "Salary Slip Submit Error"
        )
        frappe.throw(_("Error processing salary slip submission: {0}").format(str(e)))

def on_cancel_salary_slip(doc, method=None):
    """Actions to take when a salary slip is cancelled"""
    try:
        # Log event that salary slip was cancelled
        debug_log(f"Salary Slip {doc.name} cancelled for employee {getattr(doc, 'employee', 'unknown')}")
        
        # Use queue_document_updates_on_cancel from IndonesiaPayrollSalarySlip if possible
        if isinstance(doc, IndonesiaPayrollSalarySlip):
            doc.queue_document_updates_on_cancel()
        else:
            # Otherwise create a temporary instance to use the method
            temp = IndonesiaPayrollSalarySlip(doc.as_dict())
            temp.queue_document_updates_on_cancel()
        
        # Add notification to payroll_note if the field exists
        if hasattr(doc, 'payroll_note'):
            timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
            doc.payroll_note += f"\n[{timestamp}] Salary slip cancelled."
            doc.db_update()
            
        frappe.msgprint(_("Salary Slip cancelled. Related documents will be updated."))
    except Exception as e:
        log_error(
            f"Error in on_cancel_salary_slip for {doc.name}: {str(e)}",
            "Salary Slip Cancel Error"
        )
        frappe.throw(_("Error processing salary slip cancellation: {0}").format(str(e)))

def after_insert_salary_slip(doc, method=None):
    """
    Hook that runs after Salary Slip is created with better validation
    
    Args:
        doc: Object of the newly created Salary Slip
        method: Method that called the hook (not used)
    """
    try:
        # Validate required fields
        if not doc.name:
            frappe.msgprint(_("Salary Slip name is missing."))
            return
            
        if not doc.employee:
            frappe.msgprint(_("Employee is missing in Salary Slip."))
            return
            
        # Initialize custom fields using shared logic
        if isinstance(doc, IndonesiaPayrollSalarySlip):
            doc.initialize_payroll_fields()
        else:
            # For documents not using the extended class
            temp = IndonesiaPayrollSalarySlip(doc.as_dict())
            temp.initialize_payroll_fields()
            # Copy values back
            for field in ['is_final_gabung_suami', 'koreksi_pph21', 'payroll_note', 
                          'biaya_jabatan', 'netto', 'total_bpjs', 'is_using_ter', 
                          'ter_rate']:
                if hasattr(temp, field):
                    setattr(doc, field, getattr(temp, field))
        
        # Log salary slip creation with more information
        try:
            debug_log(
                f"Salary Slip {doc.name} created for employee {doc.employee} ({getattr(doc, 'employee_name', 'unnamed')})"
            )
        except Exception:
            # If logger fails, continue anyway
            pass
        
        # Add to payroll notifications if feature is available
        add_to_payroll_notifications(doc)
        
    except Exception as e:
        log_error(
            f"Error in after_insert_salary_slip for {doc.name if hasattr(doc, 'name') else 'unknown salary slip'}: {str(e)}",
            "Salary Slip Hook Error"
        )
        # Don't throw here to prevent blocking salary slip creation
        frappe.msgprint(_("Warning: Error in post-creation processing: {0}").format(str(e)))

# Wrapper functions for compatibility with hooks - updated to align with modified files
def wrapper_create_from_salary_slip(doc, method=None):
    """Wrapper to call create_from_salary_slip from bpjs_payment_api"""
    try:
        from payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api import create_from_salary_slip
        # Call the original function with only doc.name parameter
        create_from_salary_slip(doc.name)
    except ImportError:
        log_error(
            f"Could not import create_from_salary_slip from bpjs_payment_api for {doc.name}",
            "Import Error"
        )
        frappe.msgprint(_("Warning: Could not create BPJS Payment Summary."))
    except Exception as e:
        log_error(
            f"Error in wrapper_create_from_salary_slip for {doc.name}: {str(e)}",
            "Wrapper Function Error"
        )
        frappe.msgprint(_("Warning: Error creating BPJS Payment Summary: {0}").format(str(e)))

def wrapper_create_from_employee_tax_summary(doc, method=None):
    """Wrapper to call create_from_salary_slip from employee_tax_summary"""
    try:
        from payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary import create_from_salary_slip
        # Call the original function with only doc.name parameter
        create_from_salary_slip(doc.name)
    except ImportError:
        log_error(
            f"Could not import create_from_salary_slip from employee_tax_summary for {doc.name}",
            "Import Error"
        )
        frappe.msgprint(_("Warning: Could not create Employee Tax Summary."))
    except Exception as e:
        log_error(
            f"Error in wrapper_create_from_employee_tax_summary for {doc.name}: {str(e)}",
            "Wrapper Function Error"
        )
        frappe.msgprint(_("Warning: Error creating Employee Tax Summary: {0}").format(str(e)))

def wrapper_update_on_salary_slip_cancel(doc, method=None):
    """Wrapper to call update_on_salary_slip_cancel from bpjs_payment_api"""
    try:
        from payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api import update_on_salary_slip_cancel
        
        if not hasattr(doc, 'end_date') or not doc.end_date:
            frappe.msgprint(_("Salary slip end date missing, cannot update BPJS Payment Summary on cancel"))
            return
            
        # Extract month and year from doc
        month = getdate(doc.end_date).month
        year = getdate(doc.end_date).year
        
        # Call the original function with the correct parameters
        update_on_salary_slip_cancel(doc.name, month, year)
    except ImportError:
        log_error(
            f"Could not import update_on_salary_slip_cancel from bpjs_payment_api for {doc.name}",
            "Import Error"
        )
    except Exception as e:
        log_error(
            f"Error in wrapper_update_on_salary_slip_cancel for {doc.name}: {str(e)}",
            "Wrapper Function Error"
        )

def wrapper_update_on_salary_slip_cancel_employee_tax_summary(doc, method=None):
    """Wrapper to call update_on_salary_slip_cancel from employee_tax_summary"""
    try:
        from payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary import update_on_salary_slip_cancel
        
        if not hasattr(doc, 'end_date') or not doc.end_date:
            frappe.msgprint(_("Salary slip end date missing, cannot update Employee Tax Summary on cancel"))
            return
            
        # Extract year from doc
        year = getdate(doc.end_date).year
        
        # Call the original function with the correct parameters - only needs year
        update_on_salary_slip_cancel(doc.name, year)
    except ImportError:
        log_error(
            f"Could not import update_on_salary_slip_cancel from employee_tax_summary for {doc.name}",
            "Import Error"
        )
    except Exception as e:
        log_error(
            f"Error in wrapper_update_on_salary_slip_cancel_employee_tax_summary for {doc.name}: {str(e)}",
            "Wrapper Function Error"
        )

# Utility functions for error handling
def log_error(message, title):
    """
    Log error to system log
    Args:
        message: Error message
        title: Error title
    """
    full_traceback = f"{message}\n\nTraceback: {frappe.get_traceback()}"
    frappe.log_error(full_traceback, title)

def log_and_raise_error(message, log_title, user_message):
    """
    Log error and raise user-friendly message
    Args:
        message: Full error message for log
        log_title: Error log title
        user_message: User-friendly message to display
    Raises:
        ValidationError: With user-friendly message
    """
    log_error(message, log_title)
    frappe.throw(_(user_message) + f": {truncate_message(str(message), MAX_ERROR_MESSAGE_LENGTH)}")

def truncate_message(message, max_length=140):
    """
    Truncate message to prevent CharacterLengthExceededError
    Args:
        message: Message to truncate
        max_length: Maximum length
    Returns:
        str: Truncated message
    """
    if not message:
        return ""
        
    if len(message) <= max_length:
        return message
        
    return message[:max_length - 3] + "..."

def check_ter_method_enabled():
    """
    Check if TER method is enabled in PPh 21 Settings
    
    Returns:
        bool: True if TER method is enabled, False otherwise
    """
    try:
        if not frappe.db.exists("PPh 21 Settings", "PPh 21 Settings"):
            return False
            
        # Get settings
        settings = frappe.get_cached_value(
            "PPh 21 Settings",
            "PPh 21 Settings",
            ["calculation_method", "use_ter"],
            as_dict=True
        )
        
        # Check if TER is enabled
        if settings.get("calculation_method") == "TER" and settings.get("use_ter"):
            return True
            
        return False
    except Exception:
        # If there's any error, return False as a safe default
        return False

def add_to_payroll_notifications(doc):
    """Add entry to payroll notifications if available with error handling"""
    try:
        # Check if doctype Payroll Notification exists
        if not frappe.db.exists('DocType', 'Payroll Notification'):
            # No need to log or notify, just return
            return
            
        # Validate required fields
        if not doc.employee or not doc.name:
            frappe.msgprint(_("Employee or salary slip name is missing. Skipping notification."))
            return
            
        # Create notification
        notification = frappe.new_doc("Payroll Notification")
        
        # Set required fields
        notification.employee = doc.employee
        notification.employee_name = getattr(doc, 'employee_name', doc.employee)
        notification.salary_slip = doc.name
        notification.posting_date = getattr(doc, 'posting_date', frappe.utils.today())
        notification.amount = getattr(doc, 'net_pay', 0)
        notification.status = "Draft"
        
        # Add TER information if applicable
        if hasattr(doc, 'is_using_ter') and doc.is_using_ter:
            notification.is_using_ter = 1
            notification.ter_rate = getattr(doc, 'ter_rate', 0)
        
        # Insert notification
        notification.insert(ignore_permissions=True)
        
    except Exception as e:
        log_error(
            f"Failed to create payroll notification for {doc.name if hasattr(doc, 'name') else 'unknown salary slip'}: {str(e)}",
            "Payroll Notification Error"
        )
        # Don't throw here to prevent blocking salary slip creation
        frappe.msgprint(_("Warning: Could not create payroll notification: {0}").format(str(e)))