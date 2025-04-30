# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-30 07:38:00 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from .base import update_component_amount
from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import hitung_bpjs

# Define exports for proper importing by other modules
__all__ = [
    'calculate_bpjs_components',
    'debug_log',
    'check_bpjs_enrollment',
    'verify_bpjs_components'
]

# Shared debug function for error tracking
def debug_log(message, module_name="BPJS Calculator", employee=None, trace=False, max_length=2000):
    """
    Log debug message with timestamp and additional info with length limit
    
    Args:
        message: Message to log
        module_name: Module name for the log
        employee: Employee code or name (optional)
        trace: Whether to include traceback (optional)
        max_length: Maximum length of log message (optional)
    """
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    
    # Add employee info if provided
    employee_info = f"[Employee: {employee}] " if employee else ""
    log_message = f"[{timestamp}] {employee_info}{message}"
    
    # Add traceback if requested
    if trace:
        log_message += f"\nTraceback: {frappe.get_traceback()}"
        
    # Truncate message if too long
    if len(log_message) > max_length:
        log_message = log_message[:max_length-50] + f"... (truncated, full length: {len(log_message)})"
        
    frappe.log_error(log_message, module_name)

def check_bpjs_enrollment(employee_doc=None, employee_id=None):
    """
    Check if employee is enrolled in BPJS
    Args:
        employee_doc: Employee document (optional)
        employee_id: Employee ID if document not provided (optional)
    Returns:
        bool: True if enrolled, False otherwise
    """
    # Get employee doc if not provided but ID is
    if not employee_doc and employee_id:
        try:
            employee_doc = frappe.get_doc("Employee", employee_id)
        except Exception as e:
            debug_log(f"Error getting employee doc for {employee_id}: {str(e)}", trace=True)
            return False
            
    # If still no employee doc, can't proceed
    if not employee_doc:
        debug_log("Cannot check BPJS enrollment: No employee document or ID provided")
        return False
            
    # Use fast-path check with direct attribute access
    is_enrolled = getattr(employee_doc, 'is_bpjs_active', True)
    
    # Only check specific types if main flag is False
    if not is_enrolled:
        kesehatan_enrolled = getattr(employee_doc, 'bpjs_kesehatan_active', False)
        jht_enrolled = getattr(employee_doc, 'bpjs_jht_active', False)
        jp_enrolled = getattr(employee_doc, 'bpjs_jp_active', False)
        
        # Employee is enrolled if at least one type is active
        return kesehatan_enrolled or jht_enrolled or jp_enrolled
        
    return True

def verify_bpjs_components(doc, component_names=None):
    """
    Verify BPJS component values and log details
    Args:
        doc: Salary slip document
        component_names: List of BPJS component names to check (optional)
    Returns:
        dict: Dictionary with verification results
    """
    employee_info = f"{doc.employee} ({doc.employee_name})" if hasattr(doc, 'employee_name') else doc.employee
    debug_log(f"Verifying BPJS components for {doc.name}", employee=employee_info)
    
    # Default component names if not specified
    if not component_names:
        component_names = [
            "BPJS JHT Employee", 
            "BPJS JP Employee", 
            "BPJS Kesehatan Employee"
        ]
    
    # Get current values with direct lookup for better performance
    bpjs_components = {name: 0 for name in component_names}
    
    for deduction in doc.deductions:
        if deduction.salary_component in bpjs_components:
            bpjs_components[deduction.salary_component] = flt(deduction.amount)
    
    # Log component values
    debug_log(
        f"BPJS components for {doc.name}: " +
        ", ".join([f"{k.split(' ')[1]}={v}" for k, v in bpjs_components.items()]) +
        f", Total: {sum(bpjs_components.values())}",
        employee=employee_info
    )
    
    # Check if all values are zero but employee should have BPJS
    all_zero = all(value == 0 for value in bpjs_components.values())
    
    return {
        "components": bpjs_components,
        "total": sum(bpjs_components.values()),
        "all_zero": all_zero
    }

def get_cached_bpjs_settings(doc=None):
    """
    Get BPJS settings with caching
    Args:
        doc: Document to store cache in (optional)
    Returns:
        dict: BPJS settings
    """
    # If doc is provided and has cached settings, return those
    if doc and hasattr(doc, '_bpjs_settings'):
        return doc._bpjs_settings
        
    # Otherwise get settings from utility function
    from payroll_indonesia.payroll_indonesia.utils import get_bpjs_settings
    settings = get_bpjs_settings()
    
    # Cache settings in doc if provided
    if doc:
        doc._bpjs_settings = settings
        
    return settings

def add_bpjs_details_to_note(doc, bpjs_values):
    """
    Add BPJS calculation details to the payroll note
    Args:
        doc: Salary slip document
        bpjs_values: BPJS calculation results
    """
    try:
        # Initialize payroll_note if needed
        if not hasattr(doc, 'payroll_note') or doc.payroll_note is None:
            doc.payroll_note = ""
        
        # Get BPJS settings with caching
        settings = get_cached_bpjs_settings(doc)
        
        # Get BPJS percentage rates - handle both structure formats
        # First try the nested dict structure
        kesehatan_percent = settings.get("kesehatan", {}).get("employee_percent", 1.0)
        jht_percent = settings.get("jht", {}).get("employee_percent", 2.0)
        jp_percent = settings.get("jp", {}).get("employee_percent", 1.0)
        
        # If zeros, try the flat structure
        if kesehatan_percent == 0:
            kesehatan_percent = flt(settings.get("kesehatan_employee_percent", 1.0))
        if jht_percent == 0:
            jht_percent = flt(settings.get("jht_employee_percent", 2.0))
        if jp_percent == 0:
            jp_percent = flt(settings.get("jp_employee_percent", 1.0))
    
        # BPJS details section header
        doc.payroll_note += "\n\n=== Perhitungan BPJS ==="
    
        # Add component details
        if bpjs_values.get("kesehatan_employee", 0) > 0:
            doc.payroll_note += f"\nBPJS Kesehatan ({kesehatan_percent}%): Rp {bpjs_values['kesehatan_employee']:,.0f}"
        
        if bpjs_values.get("jht_employee", 0) > 0:
            doc.payroll_note += f"\nBPJS JHT ({jht_percent}%): Rp {bpjs_values['jht_employee']:,.0f}"
        
        if bpjs_values.get("jp_employee", 0) > 0:
            doc.payroll_note += f"\nBPJS JP ({jp_percent}%): Rp {bpjs_values['jp_employee']:,.0f}"
    
        # Total
        total_employee = bpjs_values.get("total_employee", 0)
        doc.payroll_note += f"\nTotal BPJS: Rp {total_employee:,.0f}"
    
    except Exception as e:
        debug_log(f"Error adding BPJS details to note: {str(e)}")
        # Continue even if there's an error adding details to the note

def calculate_bpjs_components(doc, employee, base_salary):
    """
    Calculate and update BPJS components in salary slip
    Delegates actual calculation to hitung_bpjs function
    
    Args:
        doc: Salary slip document
        employee: Employee document
        base_salary: Base salary for BPJS calculation
    """
    employee_info = f"{employee.name} ({employee.employee_name})" if hasattr(employee, 'employee_name') else employee.name
    debug_log(f"Starting calculate_bpjs_components for {doc.name}, employee: {employee_info}")
    
    try:
        # Check if employee is enrolled in BPJS
        is_enrolled = check_bpjs_enrollment(employee_doc=employee)
        if not is_enrolled:
            debug_log(f"Employee {employee_info} not enrolled in BPJS - skipping calculation")
            return
    
        # Calculate BPJS values using hitung_bpjs
        debug_log(f"Calling hitung_bpjs for employee {employee.name}, base_salary: {base_salary}")
        bpjs_values = hitung_bpjs(employee.name, base_salary)
        debug_log(f"BPJS calculation result: {bpjs_values}")
        
        # If no contributions calculated, skip the rest
        if bpjs_values["total_employee"] <= 0:
            debug_log(f"No BPJS contributions for {employee.name}, skipping component update")
            return
    
        # Update components in salary slip - check if doc has set_component_value method
        debug_log(f"Updating BPJS components in salary slip {doc.name}")
        
        # Use appropriate method to update components
        update_component_method = getattr(doc, 'set_component_value', None)
        if update_component_method and callable(update_component_method):
            # Use doc's own method
            if bpjs_values.get("kesehatan_employee", 0) > 0:
                doc.set_component_value("BPJS Kesehatan Employee", bpjs_values["kesehatan_employee"], is_deduction=True)
            
            if bpjs_values.get("jht_employee", 0) > 0:
                doc.set_component_value("BPJS JHT Employee", bpjs_values["jht_employee"], is_deduction=True)
            
            if bpjs_values.get("jp_employee", 0) > 0:
                doc.set_component_value("BPJS JP Employee", bpjs_values["jp_employee"], is_deduction=True)
        else:
            # Use imported update_component_amount function
            if bpjs_values.get("kesehatan_employee", 0) > 0:
                update_component_amount(
                    doc,
                    "BPJS Kesehatan Employee", 
                    bpjs_values["kesehatan_employee"],
                    "deductions"
                )
            
            if bpjs_values.get("jht_employee", 0) > 0:
                update_component_amount(
                    doc,
                    "BPJS JHT Employee", 
                    bpjs_values["jht_employee"],
                    "deductions"
                )
            
            if bpjs_values.get("jp_employee", 0) > 0:
                update_component_amount(
                    doc,
                    "BPJS JP Employee",
                    bpjs_values["jp_employee"],
                    "deductions"
                )
    
        # Calculate total BPJS and set it in doc
        components = verify_bpjs_components(doc)
        if hasattr(doc, 'total_bpjs'):
            doc.total_bpjs = components["total"]
            
        debug_log(f"Total BPJS for {doc.name}: {components['total']}")
            
        # Add BPJS details to payroll note
        add_bpjs_details_to_note(doc, bpjs_values)
            
        debug_log(f"BPJS components calculation completed for {doc.name}")
            
    except Exception as e:
        debug_log(f"Error calculating BPJS for {doc.name}: {str(e)}", employee=employee_info, trace=True)
        frappe.log_error(
            f"Error calculating BPJS for {doc.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Calculation Error"
        )
        frappe.throw(_("Error calculating BPJS: {0}").format(str(e)))
