# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last updated: 2025-05-04 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, cint, now_datetime
from payroll_indonesia.payroll_indonesia.utils import get_bpjs_settings


def debug_log(message, module_name="BPJS Calculation", max_length=500):
    """Log debug message with timestamp and limited length"""
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"[{timestamp}] {message}"
    
    # Truncate if message is too long to avoid memory issues
    if len(log_message) > max_length:
        log_message = log_message[:max_length] + "... (truncated)"
        
    frappe.log_error(log_message, module_name)


def check_bpjs_enrollment(employee_doc):
    """
    Check if employee is enrolled in BPJS programs
    
    Args:
        employee_doc: Employee document or dictionary
        
    Returns:
        dict: Configuration dictionary based on enrollment status
    """
    # Get BPJS settings
    settings = get_bpjs_settings()
    config = {}
    
    # Access the employee fields safely with get() if it's a dict or getattr() if it's a document
    is_dict = isinstance(employee_doc, dict)
    
    # Check BPJS Kesehatan enrollment
    # Default to 1 (enrolled) if field is missing
    if is_dict:
        kesehatan_enrolled = cint(employee_doc.get("ikut_bpjs_kesehatan", 1))
        ketenagakerjaan_enrolled = cint(employee_doc.get("ikut_bpjs_ketenagakerjaan", 1))
    else:
        kesehatan_enrolled = cint(getattr(employee_doc, "ikut_bpjs_kesehatan", 1))
        ketenagakerjaan_enrolled = cint(getattr(employee_doc, "ikut_bpjs_ketenagakerjaan", 1))
    
    # Configure BPJS Kesehatan if enrolled
    if kesehatan_enrolled:
        config["kesehatan"] = {
            "employee_percent": settings.get("kesehatan_employee_percent", 1.0),
            "employer_percent": settings.get("kesehatan_employer_percent", 4.0),
            "max_salary": settings.get("kesehatan_max_salary", 12000000),
        }

    # Configure BPJS Ketenagakerjaan components if enrolled
    if ketenagakerjaan_enrolled:
        config["jht"] = {
            "employee_percent": settings.get("jht_employee_percent", 2.0),
            "employer_percent": settings.get("jht_employer_percent", 3.7),
        }

        config["jp"] = {
            "employee_percent": settings.get("jp_employee_percent", 1.0),
            "employer_percent": settings.get("jp_employer_percent", 2.0),
            "max_salary": settings.get("jp_max_salary", 9077600),
        }

        config["jkk"] = {"percent": settings.get("jkk_percent", 0.24)}
        config["jkm"] = {"percent": settings.get("jkm_percent", 0.3)}

    return config


def hitung_bpjs(employee, base_salary=0, settings=None):
    """
    Calculate BPJS contributions for given employee and salary
    
    Args:
        employee: Employee ID or document
        base_salary (float): Base salary amount
        settings (obj, optional): BPJS Settings doc
        
    Returns:
        dict: Dictionary with calculated amounts
    """
    # Initialize result with zeros to avoid None values
    result = {
        "kesehatan_employee": 0,
        "kesehatan_employer": 0,
        "jht_employee": 0,
        "jht_employer": 0,
        "jp_employee": 0,
        "jp_employer": 0,
        "jkk_employer": 0,
        "jkm_employer": 0,
        "total_employee": 0,
        "total_employer": 0
    }
    
    try:
        # Validate inputs
        if isinstance(employee, str) and not base_salary:
            # If employee is an ID and no base_salary provided, get employee document
            emp_doc = frappe.get_doc("Employee", employee)
            if not emp_doc:
                debug_log(f"Employee {employee} not found")
                return result
        elif isinstance(employee, dict) or hasattr(employee, 'name'):
            # If employee is already a document or dict, use it
            emp_doc = employee
        else:
            debug_log(f"Invalid employee parameter: {type(employee)}")
            return result
            
        # Basic validation
        if not base_salary or base_salary <= 0:
            debug_log(f"Invalid base salary: {base_salary} for employee {getattr(emp_doc, 'name', employee)}")
            return result
            
        # Get BPJS settings if not provided
        if not settings:
            settings = frappe.get_cached_doc("BPJS Settings", "BPJS Settings")
            
        if not settings:
            debug_log("BPJS Settings not found")
            return result
            
        # Get configuration based on enrollment status
        config = check_bpjs_enrollment(emp_doc)
        
        # If no config (not enrolled in any program), return zeros
        if not config:
            debug_log(f"Employee {getattr(emp_doc, 'name', employee)} not participating in any BPJS program")
            return result

        # Calculate BPJS Kesehatan if enrolled
        if "kesehatan" in config:
            # Apply salary cap
            max_kesehatan = flt(config["kesehatan"].get("max_salary", base_salary))
            kesehatan_salary = min(base_salary, max_kesehatan)
            
            # Calculate contributions
            result["kesehatan_employee"] = flt(kesehatan_salary * config["kesehatan"]["employee_percent"] / 100)
            result["kesehatan_employer"] = flt(kesehatan_salary * config["kesehatan"]["employer_percent"] / 100)

        # Calculate BPJS JHT if enrolled
        if "jht" in config:
            result["jht_employee"] = flt(base_salary * config["jht"]["employee_percent"] / 100)
            result["jht_employer"] = flt(base_salary * config["jht"]["employer_percent"] / 100)

        # Calculate BPJS JP if enrolled with salary cap
        if "jp" in config:
            max_jp = flt(config["jp"].get("max_salary", base_salary))
            jp_salary = min(base_salary, max_jp)
            
            result["jp_employee"] = flt(jp_salary * config["jp"]["employee_percent"] / 100)
            result["jp_employer"] = flt(jp_salary * config["jp"]["employer_percent"] / 100)

        # Calculate BPJS JKK if enrolled
        if "jkk" in config:
            result["jkk_employer"] = flt(base_salary * config["jkk"]["percent"] / 100)

        # Calculate BPJS JKM if enrolled
        if "jkm" in config:
            result["jkm_employer"] = flt(base_salary * config["jkm"]["percent"] / 100)

        # Calculate totals with explicit conversion to float
        result["total_employee"] = flt(
            result["kesehatan_employee"] + result["jht_employee"] + result["jp_employee"]
        )
        result["total_employer"] = flt(
            result["kesehatan_employer"] + result["jht_employer"] +
            result["jp_employer"] + result["jkk_employer"] + result["jkm_employer"]
        )

        # Log result safely
        emp_name = getattr(emp_doc, 'name', employee) if hasattr(emp_doc, 'name') else employee
        debug_log(f"BPJS result for {emp_name}: total_employee={result['total_employee']}, total_employer={result['total_employer']}")
        return result
        
    except Exception as e:
        # Log error but don't raise exception
        debug_log(f"Error calculating BPJS: {str(e)[:100]}")
        frappe.log_error(f"Error calculating BPJS: {str(e)}", "BPJS Calculation Error")
        return result


@frappe.whitelist()
def update_all_bpjs_components():
    """Update all BPJS components for active salary structures"""
    try:
        # Get BPJS Settings
        bpjs_settings = frappe.get_doc("BPJS Settings", "BPJS Settings")
        if not bpjs_settings:
            frappe.msgprint(_("Please configure BPJS Settings first"))
            return
            
        # Update salary structures
        bpjs_settings.update_salary_structures()
        
        frappe.msgprint(_("BPJS components updated successfully"))
        
    except Exception as e:
        frappe.log_error(f"Error updating BPJS components: {str(e)[:100]}", "BPJS Update Error")
        frappe.throw(_("Failed to update BPJS components. Please check error log."))