# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last updated: 2025-05-11 10:08:25 by dannyaudianlanjutkan

import frappe
from frappe import _
from frappe.utils import flt, cint, now_datetime
from payroll_indonesia.payroll_indonesia.utils import get_bpjs_settings

# Import constants
from payroll_indonesia.constants import (
    DEFAULT_UMR, DEFAULT_BPJS_RATES, MAX_LOG_LENGTH,
    BPJS_KESEHATAN_EMPLOYEE_PERCENT, BPJS_KESEHATAN_EMPLOYER_PERCENT,
    BPJS_KESEHATAN_MAX_SALARY, BPJS_JHT_EMPLOYEE_PERCENT,
    BPJS_JHT_EMPLOYER_PERCENT, BPJS_JP_EMPLOYEE_PERCENT,
    BPJS_JP_EMPLOYER_PERCENT, BPJS_JP_MAX_SALARY,
    BPJS_JKK_PERCENT, BPJS_JKM_PERCENT
)


def debug_log(message, module_name="BPJS Calculation", employee=None, trace=False, max_length=MAX_LOG_LENGTH):
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
    
    # Truncate if message is too long to avoid memory issues
    if len(log_message) > max_length:
        log_message = log_message[:max_length] + "... (truncated)"
        
    # Add traceback if requested
    if trace:
        log_message += f"\n\nTraceback: {frappe.get_traceback()}"
        
    frappe.log_error(log_message, module_name)


def check_bpjs_enrollment(employee_doc):
    """
    Check if employee is enrolled in BPJS programs
    
    Args:
        employee_doc: Employee document or dictionary
        
    Returns:
        dict: Configuration dictionary based on enrollment status
        
    Note:
        This is the authoritative implementation of check_bpjs_enrollment.
        Other files should use this function directly to ensure consistency.
    """
    # Get BPJS settings with safe defaults
    settings = get_bpjs_settings() or DEFAULT_BPJS_RATES
    config = {}
    
    try:
        # Handle different input types safely
        is_dict = isinstance(employee_doc, dict)
        
        # If employee_doc is a string (employee ID), convert to document
        if isinstance(employee_doc, str):
            try:
                employee_doc = frappe.get_doc("Employee", employee_doc)
                is_dict = False
            except Exception as e:
                debug_log(f"Error getting employee document for ID {employee_doc}: {str(e)}", trace=True)
                # Continue with empty employee_doc, will use defaults
        
        # Get enrollment status with safe defaults (default to enrolled if fields missing)
        if is_dict:
            kesehatan_enrolled = cint(employee_doc.get("ikut_bpjs_kesehatan", 1))
            ketenagakerjaan_enrolled = cint(employee_doc.get("ikut_bpjs_ketenagakerjaan", 1))
        else:
            kesehatan_enrolled = cint(getattr(employee_doc, "ikut_bpjs_kesehatan", 1))
            ketenagakerjaan_enrolled = cint(getattr(employee_doc, "ikut_bpjs_ketenagakerjaan", 1))
        
        # Log enrollment status for debugging
        employee_name = getattr(employee_doc, 'name', str(employee_doc)) if not is_dict else str(employee_doc.get('name', 'unknown'))
        debug_log(f"BPJS enrollment status for {employee_name}: Kesehatan={kesehatan_enrolled}, Ketenagakerjaan={ketenagakerjaan_enrolled}")
        
        # Configure BPJS Kesehatan if enrolled
        if kesehatan_enrolled:
            config["kesehatan"] = {
                "employee_percent": settings.get("kesehatan_employee_percent", BPJS_KESEHATAN_EMPLOYEE_PERCENT),
                "employer_percent": settings.get("kesehatan_employer_percent", BPJS_KESEHATAN_EMPLOYER_PERCENT),
                "max_salary": settings.get("kesehatan_max_salary", BPJS_KESEHATAN_MAX_SALARY),
            }
            debug_log(f"Added BPJS Kesehatan config for {employee_name}")

        # Configure BPJS Ketenagakerjaan components if enrolled
        if ketenagakerjaan_enrolled:
            config["jht"] = {
                "employee_percent": settings.get("jht_employee_percent", BPJS_JHT_EMPLOYEE_PERCENT),
                "employer_percent": settings.get("jht_employer_percent", BPJS_JHT_EMPLOYER_PERCENT),
            }
            debug_log(f"Added BPJS JHT config for {employee_name}")

            config["jp"] = {
                "employee_percent": settings.get("jp_employee_percent", BPJS_JP_EMPLOYEE_PERCENT),
                "employer_percent": settings.get("jp_employer_percent", BPJS_JP_EMPLOYER_PERCENT),
                "max_salary": settings.get("jp_max_salary", BPJS_JP_MAX_SALARY),
            }
            debug_log(f"Added BPJS JP config for {employee_name}")

            config["jkk"] = {"percent": settings.get("jkk_percent", BPJS_JKK_PERCENT)}
            config["jkm"] = {"percent": settings.get("jkm_percent", BPJS_JKM_PERCENT)}
            debug_log(f"Added BPJS JKK and JKM config for {employee_name}")
            
        # Log final enrollment status
        is_enrolled = bool(config)
        debug_log(f"Final enrollment status for {employee_name}: {is_enrolled} with {len(config)} programs")
        
    except Exception as e:
        debug_log(f"Error checking BPJS enrollment: {str(e)}", trace=True)
        # In case of error, return empty config which means not enrolled

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
        # Extract employee info for logging
        employee_info = ""
        if isinstance(employee, str):
            employee_info = employee
        elif isinstance(employee, dict) and 'name' in employee:
            employee_info = employee['name']
        elif hasattr(employee, 'name'):
            employee_info = employee.name
        
        # Validate inputs with enhanced flexibility
        if isinstance(employee, str):
            try:
                # If employee is an ID, get employee document
                emp_doc = frappe.get_doc("Employee", employee)
                if not emp_doc:
                    debug_log(f"Employee {employee} not found", employee=employee)
                    return result
            except Exception as e:
                debug_log(f"Error getting employee {employee}: {str(e)}", employee=employee, trace=True)
                return result
        elif isinstance(employee, dict) or hasattr(employee, 'name'):
            # If employee is already a document or dict, use it
            emp_doc = employee
        else:
            debug_log(f"Invalid employee parameter type: {type(employee)}", trace=True)
            return result
            
        # IMPROVED: Basic salary validation with a fallback mechanism
        if not base_salary or base_salary <= 0:
            debug_log(f"Invalid base salary: {base_salary} for employee {employee_info}. Attempting to use gross_pay or default UMR.",
                      employee=employee_info)
                    
            # Try to get salary from employee document if available
            if hasattr(emp_doc, 'gross_salary') and emp_doc.gross_salary > 0:
                base_salary = flt(emp_doc.gross_salary)
                debug_log(f"Using employee gross salary as base: {base_salary}", employee=employee_info)
            else:
                # Use default UMR (Jakarta minimum wage as safe default)
                base_salary = DEFAULT_UMR
                debug_log(f"Using default UMR as base salary: {base_salary}", employee=employee_info)
            
        debug_log(f"Using final base salary: {base_salary}", employee=employee_info)
            
        # Get BPJS settings if not provided, with exception handling
        if not settings:
            try:
                settings = frappe.get_cached_doc("BPJS Settings", "BPJS Settings")
                if not settings:
                    debug_log("BPJS Settings not found, using defaults", employee=employee_info)
                    settings = DEFAULT_BPJS_RATES
            except Exception as e:
                debug_log(f"Error getting BPJS Settings: {str(e)}. Using defaults.", employee=employee_info, trace=True)
                settings = DEFAULT_BPJS_RATES
            
        # Get configuration based on enrollment status
        config = check_bpjs_enrollment(emp_doc)
        
        # If no config (not enrolled in any program), return zeros
        if not config:
            debug_log(f"Employee {employee_info} not participating in any BPJS program")
            return result

        # Calculate BPJS Kesehatan if enrolled
        if "kesehatan" in config:
            # Apply salary cap
            max_kesehatan = flt(config["kesehatan"].get("max_salary", base_salary))
            kesehatan_salary = min(base_salary, max_kesehatan)
            
            # Calculate contributions
            result["kesehatan_employee"] = flt(kesehatan_salary * config["kesehatan"]["employee_percent"] / 100)
            result["kesehatan_employer"] = flt(kesehatan_salary * config["kesehatan"]["employer_percent"] / 100)
            
            debug_log(f"Calculated BPJS Kesehatan: Employee={result['kesehatan_employee']}, Employer={result['kesehatan_employer']}",
                      employee=employee_info)

        # Calculate BPJS JHT if enrolled
        if "jht" in config:
            result["jht_employee"] = flt(base_salary * config["jht"]["employee_percent"] / 100)
            result["jht_employer"] = flt(base_salary * config["jht"]["employer_percent"] / 100)
            
            debug_log(f"Calculated BPJS JHT: Employee={result['jht_employee']}, Employer={result['jht_employer']}",
                     employee=employee_info)

        # Calculate BPJS JP if enrolled with salary cap
        if "jp" in config:
            max_jp = flt(config["jp"].get("max_salary", base_salary))
            jp_salary = min(base_salary, max_jp)
            
            result["jp_employee"] = flt(jp_salary * config["jp"]["employee_percent"] / 100)
            result["jp_employer"] = flt(jp_salary * config["jp"]["employer_percent"] / 100)
            
            debug_log(f"Calculated BPJS JP: Employee={result['jp_employee']}, Employer={result['jp_employer']}",
                     employee=employee_info)

        # Calculate BPJS JKK if enrolled
        if "jkk" in config:
            result["jkk_employer"] = flt(base_salary * config["jkk"]["percent"] / 100)
            debug_log(f"Calculated BPJS JKK: Employer={result['jkk_employer']}", employee=employee_info)

        # Calculate BPJS JKM if enrolled
        if "jkm" in config:
            result["jkm_employer"] = flt(base_salary * config["jkm"]["percent"] / 100)
            debug_log(f"Calculated BPJS JKM: Employer={result['jkm_employer']}", employee=employee_info)

        # Calculate totals with explicit conversion to float
        result["total_employee"] = flt(
            result["kesehatan_employee"] + result["jht_employee"] + result["jp_employee"]
        )
        result["total_employer"] = flt(
            result["kesehatan_employer"] + result["jht_employer"] +
            result["jp_employer"] + result["jkk_employer"] + result["jkm_employer"]
        )

        # Log result safely
        debug_log(f"BPJS calculation successful. Total employee={result['total_employee']}, total employer={result['total_employer']}",
                 employee=employee_info)
                 
        # Apply rounding to all result values for consistent calculation
        for key in result:
            result[key] = round(flt(result[key]), CURRENCY_PRECISION)
            
        return result
        
    except Exception as e:
        # Log error but don't raise exception
        debug_log(f"Error calculating BPJS: {str(e)}", trace=True)
        frappe.log_error(f"Error calculating BPJS: {str(e)}\nTraceback: {frappe.get_traceback()}", "BPJS Calculation Error")
        return result


def get_bpjs_enrollment_status(employee):
    """
    Get simple boolean enrollment status for an employee
    
    Args:
        employee: Employee document, dict or ID
        
    Returns:
        bool: True if enrolled in any BPJS program, False otherwise
    """
    config = check_bpjs_enrollment(employee)
    is_enrolled = bool(config and len(config) > 0)
    
    # Get employee name for logging
    if isinstance(employee, str):
        employee_name = employee
    elif isinstance(employee, dict) and 'name' in employee:
        employee_name = employee['name']
    elif hasattr(employee, 'name'):
        employee_name = employee.name
    else:
        employee_name = "unknown"
    
    debug_log(f"Employee {employee_name} BPJS enrollment status: {is_enrolled}, enrolled in {len(config) if config else 0} programs")
    
    return is_enrolled


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
        debug_log(f"Error updating BPJS components: {str(e)}", trace=True)
        frappe.log_error(f"Error updating BPJS components: {str(e)}\nTraceback: {frappe.get_traceback()}",
                        "BPJS Update Error")
        frappe.throw(_("Failed to update BPJS components. Please check error log."))


@frappe.whitelist()
def debug_bpjs_for_employee(employee=None, salary=None):
    """
    Debug function to test BPJS calculation for a specific employee
    
    Args:
        employee: Employee ID
        salary: Base salary to use for calculation
        
    Returns:
        dict: BPJS calculation results
    """
    if not employee:
        frappe.throw(_("Employee ID is required"))
        
    try:
        # Convert salary to float if provided
        if salary:
            salary = flt(salary)
        else:
            # Try to get salary from employee document
            emp_doc = frappe.get_doc("Employee", employee)
            if hasattr(emp_doc, "gross_salary") and emp_doc.gross_salary:
                salary = flt(emp_doc.gross_salary)
            else:
                # Use default UMR
                salary = DEFAULT_UMR
                
        # Log debug information
        debug_log(f"Debug BPJS calculation for employee {employee} with salary {salary}")
        
        # Calculate BPJS
        result = hitung_bpjs(employee, salary)
        
        # Add enrollment status
        result["is_enrolled"] = get_bpjs_enrollment_status(employee)
        
        # Add base salary used
        result["base_salary_used"] = salary
        
        # Return result
        return result
        
    except Exception as e:
        debug_log(f"Error in debug_bpjs_for_employee: {str(e)}", trace=True)
        frappe.throw(_("Error debugging BPJS: {0}").format(str(e)))