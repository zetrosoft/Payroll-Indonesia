# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-06 02:45:10 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, cint, now_datetime
import gc  # For manual garbage collection

from .base import update_component_amount
# Import fungsi dari bpjs_calculation.py untuk menghindari duplikasi dan inkonsistensi
from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import (
    hitung_bpjs,
    check_bpjs_enrollment as bpjs_calculation_check_enrollment,
    debug_log as bpjs_calculation_debug_log
)

# Define exports for proper importing by other modules
__all__ = [
    'calculate_bpjs_components',
    'verify_bpjs_components',
    'check_bpjs_enrollment',
    'debug_log'
]

def debug_log(message, module_name="BPJS Calculator", employee=None, trace=False, max_length=250):
    """
    Log debug message with timestamp and limited length
    
    Args:
        message: Message to log
        module_name: Module name for error log
        employee: Optional employee identifier for context
        trace: Whether to include stack trace (default: False)
        max_length: Maximum message length to avoid memory issues
    """
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    
    # Add employee info if provided
    employee_info = f"[Employee: {employee}] " if employee else ""
    log_message = f"[{timestamp}] {employee_info}{message}"
    
    # Truncate message if too long to avoid memory issues
    if len(log_message) > max_length:
        log_message = log_message[:max_length] + "... (truncated)"
    
    # Include stack trace if requested
    if trace:
        log_message += f"\n\nTraceback: {frappe.get_traceback()}"
        
    frappe.log_error(log_message, module_name)


def check_bpjs_enrollment(employee_doc):
    """
    Checks if employee is enrolled in BPJS programs
    Uses the configuration from bpjs_calculation.py and converts
    the result to boolean for backward compatibility
    
    Args:
        employee_doc: Employee document
        
    Returns:
        bool: True if enrolled in any BPJS program, False otherwise
    """
    # Use the implementation from bpjs_calculation.py
    config = bpjs_calculation_check_enrollment(employee_doc)
    
    # Convert the result to boolean - if any config is returned, employee is enrolled
    is_enrolled = bool(config and len(config) > 0)
    
    # Log the enrollment status for debugging
    employee_name = getattr(employee_doc, 'name', str(employee_doc))
    debug_log(f"Employee {employee_name} BPJS enrollment status: {is_enrolled}, config: {len(config) if config else 0} programs")
    
    return is_enrolled


def calculate_bpjs_components(doc, employee, base_salary):
    """
    Calculate and update BPJS components in salary slip
    With improved validation and error handling
    
    Args:
        doc: Salary slip document
        employee: Employee document
        base_salary: Base salary amount for BPJS calculation
    """
    # Get employee info for logging
    employee_info = f"{employee.name}"
    if hasattr(employee, 'employee_name') and employee.employee_name:
        employee_info += f" ({employee.employee_name})"
        
    try:
        # Validate base_salary first
        if not base_salary or base_salary <= 0:
            debug_log(f"Warning: Invalid base salary ({base_salary}) for {employee_info}, using gross pay or minimum wage", trace=True)
            
            # Try to use gross_pay as fallback
            if hasattr(doc, 'gross_pay') and doc.gross_pay > 0:
                base_salary = flt(doc.gross_pay)
                debug_log(f"Using gross pay as base salary: {base_salary} for {employee_info}")
            else:
                # Use minimum default (UMR Jakarta as safe default)
                base_salary = 4900000  # Default to Jakarta UMR as safe minimum if no valid amount
                debug_log(f"Using default minimum wage as base salary: {base_salary} for {employee_info}")
        
        # Check if employee is enrolled in any BPJS program
        # Using the config directly to avoid duplication
        debug_log(f"Checking BPJS enrollment for {employee_info}")
        bpjs_config = bpjs_calculation_check_enrollment(employee)
        
        if not bpjs_config:
            debug_log(f"Employee {employee_info} not enrolled in any BPJS program - skipping calculation")
            
            # Initialize total_bpjs to 0 to avoid NoneType errors
            if hasattr(doc, 'total_bpjs'):
                doc.total_bpjs = 0
                
            return
            
        # Calculate BPJS values
        debug_log(f"Calculating BPJS for {employee_info}, base_salary: {base_salary}")
        bpjs_values = hitung_bpjs(employee, base_salary)
        
        # If no contributions calculated, initialize fields and return
        if bpjs_values["total_employee"] <= 0:
            debug_log(f"No BPJS contributions calculated for {employee_info}. Check BPJS settings.")
            
            # Initialize total_bpjs to 0 to avoid NoneType errors
            if hasattr(doc, 'total_bpjs'):
                doc.total_bpjs = 0
                
            return
            
        # Update BPJS components in salary slip
        debug_log(f"Updating BPJS components in salary slip {doc.name}")
        
        # BPJS Kesehatan Employee
        if bpjs_values["kesehatan_employee"] > 0:
            debug_log(f"Setting BPJS Kesehatan Employee: {bpjs_values['kesehatan_employee']}")
            update_component_amount(
                doc,
                "BPJS Kesehatan Employee", 
                bpjs_values["kesehatan_employee"],
                "deductions"
            )
        
        # BPJS JHT Employee
        if bpjs_values["jht_employee"] > 0:
            debug_log(f"Setting BPJS JHT Employee: {bpjs_values['jht_employee']}")
            update_component_amount(
                doc,
                "BPJS JHT Employee", 
                bpjs_values["jht_employee"],
                "deductions"
            )
        
        # BPJS JP Employee
        if bpjs_values["jp_employee"] > 0:
            debug_log(f"Setting BPJS JP Employee: {bpjs_values['jp_employee']}")
            update_component_amount(
                doc,
                "BPJS JP Employee",
                bpjs_values["jp_employee"],
                "deductions"
            )
        
        # Set total_bpjs in doc
        if hasattr(doc, 'total_bpjs'):
            doc.total_bpjs = flt(bpjs_values["total_employee"])
            debug_log(f"Set total_bpjs to {doc.total_bpjs}")
            
        # Add BPJS details to payroll note
        add_bpjs_info_to_note(doc, bpjs_values)
        
        # Verify the components were properly added
        verification = verify_bpjs_components(doc)
        if verification["all_zero"]:
            debug_log(f"Warning: All BPJS components are zero after calculation for {employee_info}", trace=True)
        
        # Run garbage collection to free memory
        gc.collect()
        
        debug_log(f"BPJS components calculation completed for {doc.name}")
        
    except Exception as e:
        # Log error with limited size
        debug_log(f"Error in BPJS calculation: {str(e)[:100]}", employee=employee_info, trace=True)
        
        # Initialize total_bpjs to 0 to avoid NoneType errors in tax calculations
        if hasattr(doc, 'total_bpjs'):
            doc.total_bpjs = 0
            
        # Don't raise exception to prevent process termination
        frappe.msgprint(_("Warning: Error in BPJS calculation. See error log for details."))


def verify_bpjs_components(doc):
    """
    Verify that BPJS components in the salary slip are correct
    
    Args:
        doc: Salary slip document
        
    Returns:
        dict: Verification results
    """
    # Initialize result
    result = {
        "all_zero": True,
        "kesehatan_found": False,
        "jht_found": False,
        "jp_found": False,
        "total": 0
    }
    
    try:
        # Check for BPJS components in deductions
        if not hasattr(doc, 'deductions') or not doc.deductions:
            debug_log(f"No deductions found in doc {doc.name}")
            return result
            
        for deduction in doc.deductions:
            if deduction.salary_component == "BPJS Kesehatan Employee":
                result["kesehatan_found"] = True
                if flt(deduction.amount) > 0:
                    result["all_zero"] = False
                result["total"] += flt(deduction.amount)
                
            elif deduction.salary_component == "BPJS JHT Employee":
                result["jht_found"] = True
                if flt(deduction.amount) > 0:
                    result["all_zero"] = False
                result["total"] += flt(deduction.amount)
                
            elif deduction.salary_component == "BPJS JP Employee":
                result["jp_found"] = True
                if flt(deduction.amount) > 0:
                    result["all_zero"] = False
                result["total"] += flt(deduction.amount)
        
        # Update doc.total_bpjs if it exists
        if hasattr(doc, 'total_bpjs'):
            doc.total_bpjs = result["total"]
            
        return result
        
    except Exception as e:
        debug_log(f"Error verifying BPJS components: {str(e)[:100]}", trace=True)
        # Return default result on error
        return result


def add_bpjs_info_to_note(doc, bpjs_values):
    """
    Add BPJS calculation details to payroll note with duplication check
    """
    try:
        # Initialize payroll_note if needed
        if not hasattr(doc, 'payroll_note'):
            doc.payroll_note = ""
        elif doc.payroll_note is None:
            doc.payroll_note = ""
            
        # Check if BPJS calculation section already exists
        if "=== BPJS Calculation ===" in doc.payroll_note:
            debug_log(f"BPJS calculation info already exists in payroll_note, skipping")
            return
            
        # Add BPJS calculation details with section markers
        doc.payroll_note += "\n\n<!-- BPJS_CALCULATION_START -->\n"
        doc.payroll_note += "=== BPJS Calculation ===\n"
        
        # Only add components with values
        if bpjs_values["kesehatan_employee"] > 0:
            doc.payroll_note += f"BPJS Kesehatan: Rp {flt(bpjs_values['kesehatan_employee']):,.0f}\n"
            
        if bpjs_values["jht_employee"] > 0:
            doc.payroll_note += f"BPJS JHT: Rp {flt(bpjs_values['jht_employee']):,.0f}\n"
            
        if bpjs_values["jp_employee"] > 0:
            doc.payroll_note += f"BPJS JP: Rp {flt(bpjs_values['jp_employee']):,.0f}\n"
            
        # Add total
        doc.payroll_note += f"Total BPJS: Rp {flt(bpjs_values['total_employee']):,.0f}\n"
        doc.payroll_note += "<!-- BPJS_CALCULATION_END -->\n"
        
    except Exception as e:
        # Log error but continue
        debug_log(f"Error adding BPJS info to note: {str(e)[:100]}", trace=True)
