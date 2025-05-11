# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 08:26:15 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from .base import update_component_amount

# Import functions from bpjs_calculation.py - centralized BPJS logic
from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import (
    hitung_bpjs,
    check_bpjs_enrollment,
    debug_log
)

# Define exports for proper importing by other modules
__all__ = [
    'calculate_bpjs_components',
    'verify_bpjs_components'
]

def calculate_bpjs_components(doc, employee, base_salary):
    """
    Calculate and update BPJS components in salary slip
    This function is a wrapper around the centralized BPJS calculation logic
    
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
        bpjs_config = check_bpjs_enrollment(employee)
        
        if not bpjs_config:
            # Non-critical information - log but continue
            frappe.log_error(
                "Employee {0} not enrolled in any BPJS program - skipping calculation".format(employee_info),
                "BPJS Enrollment Info"
            )
            
            # Initialize total_bpjs to 0 to avoid NoneType errors
            if hasattr(doc, 'total_bpjs'):
                doc.total_bpjs = 0
                
            return
            
        # Calculate BPJS values using the centralized function
        bpjs_values = hitung_bpjs(employee, base_salary)
        
        # If no contributions calculated, initialize fields and return
        if bpjs_values["total_employee"] <= 0:
            # Non-critical information - log but continue
            frappe.log_error(
                "No BPJS contributions calculated for {0}. Check BPJS settings.".format(employee_info),
                "BPJS Calculation Info"
            )
            
            # Initialize total_bpjs to 0 to avoid NoneType errors
            if hasattr(doc, 'total_bpjs'):
                doc.total_bpjs = 0
                
            return
            
        # Update BPJS components in salary slip
        frappe.log_error(
            "Updating BPJS components in salary slip {0}".format(doc.name if hasattr(doc, 'name') else 'New'),
            "BPJS Update Info"
        )
        
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
            frappe.log_error(
                "Set total_bpjs to {0} for {1}".format(
                    doc.total_bpjs, doc.name if hasattr(doc, 'name') else 'New'
                ),
                "BPJS Total Update"
            )
            
        # Add BPJS details to payroll note
        add_bpjs_info_to_note(doc, bpjs_values)
        
        # Verify the components were properly added
        verify_bpjs_components(doc)
        
        frappe.log_error(
            "BPJS components calculation completed for {0}".format(
                doc.name if hasattr(doc, 'name') else 'New'
            ),
            "BPJS Calculation Complete"
        )
        
    except Exception as e:
        # BPJS calculation can continue with default values - log error and show warning
        frappe.log_error(
            "Error calculating BPJS for {0}: {1}".format(employee_info, str(e)),
            "BPJS Calculation Error"
        )
        
        # Initialize total_bpjs to 0 to avoid NoneType errors in tax calculations
        if hasattr(doc, 'total_bpjs'):
            doc.total_bpjs = 0
            
        # Show warning to user but continue processing
        frappe.msgprint(
            _("Warning: Error in BPJS calculation. Using zero values as fallback."),
            indicator="orange"
        )


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
            frappe.log_error(
                "No deductions found in doc {0}".format(doc.name if hasattr(doc, 'name') else 'unknown'),
                "BPJS Verification Info"
            )
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
        # Non-critical verification error - log and return default result
        frappe.log_error(
            "Error verifying BPJS components for {0}: {1}".format(
                doc.name if hasattr(doc, 'name') else 'unknown', str(e)
            ),
            "BPJS Verification Error"
        )
        frappe.msgprint(
            _("Warning: Could not verify BPJS components."),
            indicator="orange"
        )
        # Return default result on error
        return result


def add_bpjs_info_to_note(doc, bpjs_values):
    """
    Add BPJS calculation details to payroll note with duplication check
    
    Args:
        doc: Salary slip document
        bpjs_values: BPJS calculation results
    """
    try:
        # Initialize payroll_note if needed
        if not hasattr(doc, 'payroll_note'):
            doc.payroll_note = ""
        elif doc.payroll_note is None:
            doc.payroll_note = ""
            
        # Check if BPJS calculation section already exists
        if "=== BPJS Calculation ===" in doc.payroll_note:
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
        # Non-critical error - log and continue
        frappe.log_error(
            "Error adding BPJS info to note for {0}: {1}".format(
                doc.name if hasattr(doc, 'name') else 'unknown', str(e)
            ),
            "BPJS Note Error"
        )
        # No msgprint needed as this is a background operation