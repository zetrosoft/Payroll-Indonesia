# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-06 03:01:01 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate, cint, now_datetime

# Import debug_log directly from bpjs_calculator to avoid circular imports
from payroll_indonesia.override.salary_slip.bpjs_calculator import debug_log

# Import other functions from salary_slip
from payroll_indonesia.override.salary_slip.controller import IndonesiaPayrollSalarySlip
from payroll_indonesia.override.salary_slip import setup_fiscal_year_if_missing

# Import BPJS functions
from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import hitung_bpjs, check_bpjs_enrollment

__all__ = [
    'validate_salary_slip',
    'validate_dependent_doctypes',
    'validate_required_components',
    'ensure_bpjs_components',
    'on_submit_salary_slip',
    'on_cancel_salary_slip',
    'after_insert_salary_slip',
    'wrapper_create_from_employee_tax_summary',
    'wrapper_update_on_salary_slip_cancel_employee_tax_summary',
    'log_error',
    'log_and_raise_error',
    'truncate_message',
    'check_ter_method_enabled',
    'add_to_payroll_notifications'
]

# Constants
MAX_ERROR_MESSAGE_LENGTH = 140
# Required components that must exist in every salary slip
REQUIRED_COMPONENTS = {
    "earnings": ["Gaji Pokok"],
    "deductions": [
        "BPJS JHT Employee",
        "BPJS JP Employee", 
        "BPJS Kesehatan Employee",
        "PPh 21"
    ]
}
# Default UMR Jakarta as safe fallback
DEFAULT_UMR = 4900000

# Validation functions for salary slip
def validate_salary_slip(doc, method=None):
    """
    Additional validation for salary slip with improved error handling
    
    Args:
        doc (obj): Salary Slip document
        method (str, optional): Method that called this function
    """
    try:
        # Get employee info for logging
        employee_info = f"{doc.employee} ({doc.employee_name})" if hasattr(doc, 'employee_name') else doc.employee
        debug_log(f"Starting validate_salary_slip for {doc.name if hasattr(doc, 'name') else 'New Salary Slip'}", 
                 employee=employee_info)
        
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
        
        # Check if all required components exist in salary slip - added detailed logging
        debug_log(f"Validating required components for {doc.name if hasattr(doc, 'name') else 'New Salary Slip'}", 
                 employee=employee_info)
        validate_required_components(doc)
        
        # Ensure BPJS components are properly set - NEW FUNCTION
        debug_log(f"Ensuring BPJS components for {doc.name if hasattr(doc, 'name') else 'New Salary Slip'}", 
                 employee=employee_info)
        ensure_bpjs_components(doc)
        
        debug_log(f"Validation completed for {doc.name if hasattr(doc, 'name') else 'New Salary Slip'}", 
                 employee=employee_info)
        
    except Exception as e:
        log_error(
            f"Salary Slip Validation Error for {doc.name if hasattr(doc, 'name') else 'New Salary Slip'}: {str(e)}",
            "Salary Slip Validation Error"
        )
        frappe.throw(_("Error validating salary slip: {0}").format(str(e)))

def validate_dependent_doctypes():
    """
    Check if all dependent DocTypes and settings exist
    
    Raises:
        ValidationError: If any required DocType is missing
    """
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
            
        # Check required dependent DocTypes - Employee Tax Summary only
        required_doctypes = [
            "Employee Tax Summary"
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
    """
    Check if all required components exist in the salary slip and add them if missing
    
    Args:
        doc (obj): Salary Slip document
        
    Raises:
        ValidationError: If required components are missing and can't be added
    """
    try:
        # First check if all required components exist in the system
        missing_components = []
        for component_type, components in REQUIRED_COMPONENTS.items():
            for component in components:
                if not frappe.db.exists("Salary Component", component):
                    missing_components.append(component)
                    
        if missing_components:
            frappe.throw(_("Required salary components not found in the system: {0}").format(
                ", ".join(missing_components)
            ))
        
        # Then check if all required components are in the salary slip
        for component_type, components in REQUIRED_COMPONENTS.items():
            # Verify the component type exists in the doc
            if not hasattr(doc, component_type) or not getattr(doc, component_type):
                frappe.throw(_("Salary slip doesn't have {0} table").format(component_type))
                
            # Get list of existing components in this type
            components_in_slip = [d.salary_component for d in getattr(doc, component_type)]
            
            # Check for missing components and add them
            for component in components:
                if component not in components_in_slip:
                    debug_log(f"Adding missing component {component} to {doc.name if hasattr(doc, 'name') else 'New Salary Slip'}")
                    # Add the missing component with improved error handling
                    try:
                        # Get component details
                        component_doc = frappe.get_cached_doc("Salary Component", component)
                        if not component_doc:
                            debug_log(f"Component {component} exists but couldn't be fetched", trace=True)
                            component_doc = frappe.get_doc("Salary Component", component)
                        
                        # Get abbr, default to first 3 chars if not found
                        abbr = component_doc.salary_component_abbr if hasattr(component_doc, "salary_component_abbr") else component[:3].upper()
                        
                        # Create a new row
                        row = frappe.new_doc("Salary Detail")
                        row.salary_component = component
                        row.abbr = abbr
                        row.amount = 0  # Initialize with zero
                        row.parentfield = component_type
                        row.parenttype = "Salary Slip"
                        row.parent = doc.name if hasattr(doc, 'name') else ""
                        
                        # Append to the component list in doc
                        getattr(doc, component_type).append(row)
                        
                        debug_log(f"Added missing component: {component}")
                        frappe.msgprint(_("Added missing component: {0}").format(component))
                        
                    except Exception as e:
                        log_error(
                            f"Error adding component {component}: {str(e)}\nTraceback: {frappe.get_traceback()}",
                            "Component Addition Error"
                        )
                        frappe.throw(_("Error adding component {0}: {1}").format(component, str(e)))
                        
    except Exception as e:
        log_error(
            f"Error validating required components: {str(e)}\nTraceback: {frappe.get_traceback()}",
            "Component Validation Error"
        )
        frappe.throw(_("Error validating required salary components: {0}").format(str(e)))

def ensure_bpjs_components(doc):
    """
    Ensure BPJS components are properly calculated and set
    """
    try:
        # Skip if employee is not set
        if not hasattr(doc, 'employee') or not doc.employee:
            debug_log(f"Cannot ensure BPJS components - employee not set")
            return
            
        # Get employee doc
        try:
            employee = frappe.get_doc("Employee", doc.employee)
        except Exception as e:
            debug_log(f"Error getting employee doc for {doc.employee}: {str(e)}", trace=True)
            return
            
        # Get base salary for BPJS from earnings
        base_salary = get_base_salary_for_bpjs(doc)
        if base_salary <= 0:
            debug_log(f"Base salary for BPJS is invalid: {base_salary}. Using gross_pay or default UMR.", employee=doc.employee)
            # Try to use gross_pay
            if hasattr(doc, 'gross_pay') and doc.gross_pay > 0:
                base_salary = doc.gross_pay
            else:
                # Use default UMR as fallback
                base_salary = DEFAULT_UMR
                
        debug_log(f"Using base salary {base_salary} for BPJS calculations", employee=doc.employee)
        
        # Check if employee is enrolled in BPJS
        try:
            # Get BPJS config for employee
            bpjs_config = check_bpjs_enrollment(employee)
            
            # If employee is not enrolled, set zeros in components and return
            if not bpjs_config:
                debug_log(f"Employee {doc.employee} is not enrolled in BPJS. Setting zeros.")
                set_component_values(doc, {
                    "BPJS Kesehatan Employee": 0,
                    "BPJS JHT Employee": 0,
                    "BPJS JP Employee": 0
                }, "deductions")
                
                # Set total_bpjs to 0
                if hasattr(doc, 'total_bpjs'):
                    doc.total_bpjs = 0
                    
                return
                
            # Employee is enrolled, calculate BPJS values
            debug_log(f"Calculating BPJS values for {doc.employee} with base salary {base_salary}")
            bpjs_values = hitung_bpjs(employee, base_salary)
            
            # Check if calculation succeeded
            if not bpjs_values or bpjs_values["total_employee"] <= 0:
                debug_log(f"BPJS calculation returned no values or zero total. Check BPJS settings.", employee=doc.employee)
                # Don't return, will set zeros below
            
            # Set component values in the salary slip with explicit keys
            set_component_values(doc, {
                "BPJS Kesehatan Employee": bpjs_values.get("kesehatan_employee", 0),
                "BPJS JHT Employee": bpjs_values.get("jht_employee", 0),
                "BPJS JP Employee": bpjs_values.get("jp_employee", 0)
            }, "deductions")
            
            # Set total_bpjs field
            if hasattr(doc, 'total_bpjs'):
                doc.total_bpjs = flt(bpjs_values.get("total_employee", 0))
                debug_log(f"Set total_bpjs to {doc.total_bpjs}", employee=doc.employee)
                
            
        except Exception as e:
            debug_log(f"Error calculating BPJS for {doc.employee}: {str(e)}", trace=True, employee=doc.employee)
            frappe.msgprint(_("Warning: Error calculating BPJS values. Check log for details."))
            
    except Exception as e:
        debug_log(f"Error in ensure_bpjs_components: {str(e)}", trace=True)
        log_error(
            f"Error ensuring BPJS components: {str(e)}\nTraceback: {frappe.get_traceback()}",
            "BPJS Component Error"
        )
        frappe.msgprint(_("Warning: Error ensuring BPJS components. Check log for details."))

def get_base_salary_for_bpjs(doc):
    """
    Get base salary for BPJS calculation with enhanced validation
    
    Args:
        doc (obj): Salary Slip document
        
    Returns:
        float: Base salary amount for BPJS calculation
    """
    base_salary = 0
    
    # Check if earnings exist
    if not hasattr(doc, 'earnings') or not doc.earnings:
        debug_log(f"No earnings found in salary slip {getattr(doc, 'name', 'unknown')}")
        # No earnings, use gross_pay if available
        if hasattr(doc, 'gross_pay') and doc.gross_pay > 0:
            debug_log(f"Using gross_pay as base salary: {doc.gross_pay}")
            return flt(doc.gross_pay)
        return 0
        
    # Try to find Gaji Pokok first
    gaji_pokok_found = False
    for earning in doc.earnings:
        if earning.salary_component == "Gaji Pokok":
            base_salary = flt(earning.amount)
            gaji_pokok_found = True
            debug_log(f"Found Gaji Pokok component: {base_salary}")
            break
    
    # If not found, try Basic
    if not gaji_pokok_found:
        debug_log("Gaji Pokok not found, looking for Basic component")
        basic_found = False
        for earning in doc.earnings:
            if earning.salary_component == "Basic":
                base_salary = flt(earning.amount)
                basic_found = True
                debug_log(f"Found Basic component: {base_salary}")
                break
        
        # If still not found, use first component
        if not basic_found and doc.earnings:
            base_salary = flt(doc.earnings[0].amount)
            debug_log(f"Using first component as base salary: {base_salary} ({doc.earnings[0].salary_component})")
    
    # If still zero, use gross_pay as fallback
    if base_salary <= 0 and hasattr(doc, 'gross_pay') and doc.gross_pay > 0:
        base_salary = flt(doc.gross_pay)
        debug_log(f"No valid component found, using gross_pay as base salary: {base_salary}")
        
    debug_log(f"Final base salary for BPJS calculation: {base_salary}")
    return base_salary

def set_component_values(doc, component_values, component_type):
    """
    Set values for components in the salary slip
    
    Args:
        doc (obj): Salary Slip document
        component_values (dict): Dictionary of component names and values
        component_type (str): Type of component (earnings/deductions)
    """
    components = getattr(doc, component_type, [])
    if not components:
        debug_log(f"No {component_type} found in doc {getattr(doc, 'name', 'unknown')}")
        return
        
    # Track which components were found and updated
    updated_components = set()
    
    # Update existing components
    for component in components:
        if component.salary_component in component_values:
            old_value = flt(component.amount)
            new_value = flt(component_values[component.salary_component])
            component.amount = new_value
            updated_components.add(component.salary_component)
            debug_log(f"Updated {component.salary_component}: {old_value} -> {new_value}")
            
    # Add missing components if not found
    for component_name, value in component_values.items():
        if component_name not in updated_components:
            try:
                # Get component details
                component_doc = frappe.get_cached_doc("Salary Component", component_name)
                if not component_doc:
                    component_doc = frappe.get_doc("Salary Component", component_name)
                
                # Get abbreviation
                abbr = component_doc.salary_component_abbr if hasattr(component_doc, "salary_component_abbr") else component_name[:3].upper()
                
                # Create new row
                row = frappe.new_doc("Salary Detail")
                row.salary_component = component_name
                row.abbr = abbr
                row.amount = flt(value)
                row.parentfield = component_type
                row.parenttype = "Salary Slip"
                row.parent = doc.name if hasattr(doc, 'name') else ""
                
                # Add to components
                components.append(row)
                debug_log(f"Added new component {component_name} with value {value}")
                
            except Exception as e:
                debug_log(f"Error adding component {component_name}: {str(e)}", trace=True)

def add_bpjs_note(doc, bpjs_values):
    """
    Add BPJS calculation details to payroll note
    
    Args:
        doc (obj): Salary Slip document
        bpjs_values (dict): BPJS calculation values
    """
    try:
        # Initialize payroll_note if needed
        if not hasattr(doc, 'payroll_note'):
            doc.payroll_note = ""
        elif doc.payroll_note is None:
            doc.payroll_note = ""
            
        # Add BPJS calculation details
        doc.payroll_note += "\n\n=== BPJS Calculation ===\n"
        
        # Only add components with values
        if bpjs_values.get("kesehatan_employee", 0) > 0:
            doc.payroll_note += f"BPJS Kesehatan: Rp {flt(bpjs_values['kesehatan_employee']):,.0f}\n"
            
        if bpjs_values.get("jht_employee", 0) > 0:
            doc.payroll_note += f"BPJS JHT: Rp {flt(bpjs_values['jht_employee']):,.0f}\n"
            
        if bpjs_values.get("jp_employee", 0) > 0:
            doc.payroll_note += f"BPJS JP: Rp {flt(bpjs_values['jp_employee']):,.0f}\n"
            
        # Add total
        doc.payroll_note += f"Total BPJS: Rp {flt(bpjs_values.get('total_employee', 0)):,.0f}\n"
        
    except Exception as e:
        # Log error but continue
        debug_log(f"Error adding BPJS info to note: {str(e)}", trace=True)

def on_submit_salary_slip(doc, method=None):
    """
    Actions after salary slip is submitted
    
    Args:
        doc (obj): Salary Slip document
        method (str, optional): Method that called this function
    """
    try:
        # Updates will be handled in salary_slip.py IndonesiaPayrollSalarySlip.on_submit
        # Just log the event
        debug_log(f"on_submit_salary_slip hook triggered for {doc.name}", "Salary Slip Submit")
        
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
    """
    Actions to take when a salary slip is cancelled
    
    Args:
        doc (obj): Salary Slip document
        method (str, optional): Method that called this function
    """
    try:
        # Log event that salary slip was cancelled
        debug_log(f"Salary Slip {doc.name} cancelled for employee {getattr(doc, 'employee', 'unknown')}", "Salary Slip Cancel")
        
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
        doc (obj): Object of the newly created Salary Slip
        method (str, optional): Method that called the hook (not used)
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
        debug_log(
            f"Salary Slip {doc.name} created for employee {doc.employee} ({getattr(doc, 'employee_name', 'unnamed')})",
            "Salary Slip Created"
        )
        
        # Add to payroll notifications if feature is available
        add_to_payroll_notifications(doc)
        
    except Exception as e:
        log_error(
            f"Error in after_insert_salary_slip for {doc.name if hasattr(doc, 'name') else 'unknown salary slip'}: {str(e)}",
            "Salary Slip Hook Error"
        )
        # Don't throw here to prevent blocking salary slip creation
        frappe.msgprint(_("Warning: Error in post-creation processing: {0}").format(str(e)))

def wrapper_create_from_employee_tax_summary(doc, method=None):
    """
    Wrapper to call create_from_salary_slip from employee_tax_summary
    
    Args:
        doc (obj): Salary Slip document
        method (str, optional): Method that called this function (not used)
    """
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

def wrapper_update_on_salary_slip_cancel_employee_tax_summary(doc, method=None):
    """
    Wrapper to call update_on_salary_slip_cancel from employee_tax_summary
    
    Args:
        doc (obj): Salary Slip document
        method (str, optional): Method that called this function (not used)
    """
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
        message (str): Error message
        title (str): Error title
    """
    full_traceback = f"{message}\n\nTraceback: {frappe.get_traceback()}"
    frappe.log_error(full_traceback, title)

def log_and_raise_error(message, log_title, user_message):
    """
    Log error and raise user-friendly message
    
    Args:
        message (str): Full error message for log
        log_title (str): Error log title
        user_message (str): User-friendly message to display
        
    Raises:
        ValidationError: With user-friendly message
    """
    log_error(message, log_title)
    frappe.throw(_(user_message) + f": {truncate_message(str(message), MAX_ERROR_MESSAGE_LENGTH)}")

def truncate_message(message, max_length=140):
    """
    Truncate message to prevent CharacterLengthExceededError
    
    Args:
        message (str): Message to truncate
        max_length (int, optional): Maximum length. Defaults to 140.
        
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
    """
    Add entry to payroll notifications if available with error handling
    
    Args:
        doc (obj): Salary Slip document
    """
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
        
        # Add note about BPJS Payment Summary
        if hasattr(doc, 'payroll_note'):
            timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
            doc.payroll_note += f"\n[{timestamp}] Note: BPJS Payment Summary needs to be created manually."
            doc.db_set('payroll_note', doc.payroll_note, update_modified=False)
        
    except Exception as e:
        log_error(
            f"Failed to create payroll notification for {doc.name if hasattr(doc, 'name') else 'unknown salary slip'}: {str(e)}",
            "Payroll Notification Error"
        )
        # Don't throw here to prevent blocking salary slip creation
        frappe.msgprint(_("Warning: Could not create payroll notification: {0}").format(str(e)))
