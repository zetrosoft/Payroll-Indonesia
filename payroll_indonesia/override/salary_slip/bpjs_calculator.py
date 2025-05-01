# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-01 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, now_datetime
import gc  # For manual garbage collection

from .base import update_component_amount
from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import hitung_bpjs

# Define exports for proper importing by other modules
__all__ = [
    'calculate_bpjs_components',
    'debug_log'
]

def debug_log(message, module_name="BPJS Calculator", employee=None, max_length=250):
    """
    Log debug message with timestamp and limited length
    """
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    
    # Add employee info if provided
    employee_info = f"[Employee: {employee}] " if employee else ""
    log_message = f"[{timestamp}] {employee_info}{message}"
    
    # Truncate message if too long to avoid memory issues
    if len(log_message) > max_length:
        log_message = log_message[:max_length] + "... (truncated)"
        
    frappe.log_error(log_message, module_name)


def check_bpjs_enrollment(employee_doc):
    """
    Check if employee is enrolled in BPJS programs
    
    Args:
        employee_doc: Employee document
        
    Returns:
        bool: True if enrolled in any BPJS program, False otherwise
    """
    # Check using the correct fields, defaulting to True (1) if missing
    kesehatan_enrolled = cint(getattr(employee_doc, "ikut_bpjs_kesehatan", 1))
    ketenagakerjaan_enrolled = cint(getattr(employee_doc, "ikut_bpjs_ketenagakerjaan", 1))
    
    # Return True if enrolled in any BPJS program
    return kesehatan_enrolled or ketenagakerjaan_enrolled


def calculate_bpjs_components(doc, employee, base_salary):
    """
    Calculate and update BPJS components in salary slip
    
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
        # Check if employee is enrolled in any BPJS program
        if not check_bpjs_enrollment(employee):
            debug_log(f"Employee {employee_info} not enrolled in any BPJS program - skipping calculation")
            
            # Initialize total_bpjs to 0 to avoid NoneType errors
            if hasattr(doc, 'total_bpjs'):
                doc.total_bpjs = 0
                
            return
            
        # Calculate BPJS values
        debug_log(f"Calculating BPJS for {employee_info}, base_salary: {base_salary}")
        bpjs_values = hitung_bpjs(employee.name, base_salary)
        
        # If no contributions calculated, initialize fields and return
        if bpjs_values["total_employee"] <= 0:
            debug_log(f"No BPJS contributions calculated for {employee_info}")
            
            # Initialize total_bpjs to 0 to avoid NoneType errors
            if hasattr(doc, 'total_bpjs'):
                doc.total_bpjs = 0
                
            return
            
        # Update BPJS components in salary slip
        debug_log(f"Updating BPJS components in salary slip {doc.name}")
        
        # BPJS Kesehatan Employee
        if bpjs_values["kesehatan_employee"] > 0:
            update_component_amount(
                doc,
                "BPJS Kesehatan Employee", 
                bpjs_values["kesehatan_employee"],
                "deductions"
            )
        
        # BPJS JHT Employee
        if bpjs_values["jht_employee"] > 0:
            update_component_amount(
                doc,
                "BPJS JHT Employee", 
                bpjs_values["jht_employee"],
                "deductions"
            )
        
        # BPJS JP Employee
        if bpjs_values["jp_employee"] > 0:
            update_component_amount(
                doc,
                "BPJS JP Employee",
                bpjs_values["jp_employee"],
                "deductions"
            )
        
        # Set total_bpjs in doc
        if hasattr(doc, 'total_bpjs'):
            doc.total_bpjs = flt(bpjs_values["total_employee"])
            
        # Add BPJS details to payroll note
        add_bpjs_info_to_note(doc, bpjs_values)
        
        # Run garbage collection to free memory
        gc.collect()
        
        debug_log(f"BPJS components calculation completed for {doc.name}")
        
    except Exception as e:
        # Log error with limited size
        debug_log(f"Error in BPJS calculation: {str(e)[:100]}", employee=employee_info)
        
        # Initialize total_bpjs to 0 to avoid NoneType errors in tax calculations
        if hasattr(doc, 'total_bpjs'):
            doc.total_bpjs = 0
            
        # Don't raise exception to prevent process termination
        frappe.msgprint(_("Warning: Error in BPJS calculation. See error log for details."))


def add_bpjs_info_to_note(doc, bpjs_values):
    """Add BPJS calculation details to payroll note"""
    try:
        # Initialize payroll_note if needed
        if not hasattr(doc, 'payroll_note'):
            doc.payroll_note = ""
        elif doc.payroll_note is None:
            doc.payroll_note = ""
            
        # Add BPJS calculation details
        doc.payroll_note += "\n\n=== BPJS Calculation ===\n"
        
        # Only add components with values
        if bpjs_values["kesehatan_employee"] > 0:
            doc.payroll_note += f"BPJS Kesehatan: Rp {flt(bpjs_values['kesehatan_employee']):,.0f}\n"
            
        if bpjs_values["jht_employee"] > 0:
            doc.payroll_note += f"BPJS JHT: Rp {flt(bpjs_values['jht_employee']):,.0f}\n"
            
        if bpjs_values["jp_employee"] > 0:
            doc.payroll_note += f"BPJS JP: Rp {flt(bpjs_values['jp_employee']):,.0f}\n"
            
        # Add total
        doc.payroll_note += f"Total BPJS: Rp {flt(bpjs_values['total_employee']):,.0f}\n"
        
    except Exception as e:
        # Log error but continue
        debug_log(f"Error adding BPJS info to note: {str(e)[:100]}")