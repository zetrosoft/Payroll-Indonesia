# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last updated: 2025-05-01 by dannyaudian

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


def get_bpjs_config(emp, settings):
    """Get BPJS configuration based on employee enrollment status"""
    config = {}

    # Only include BPJS Kesehatan if employee is enrolled
    # Default to 1 (enrolled) if field is missing
    if cint(emp.get("ikut_bpjs_kesehatan", 1)):
        config["kesehatan"] = {
            "employee_percent": settings.get("kesehatan_employee_percent", 1.0),
            "employer_percent": settings.get("kesehatan_employer_percent", 4.0),
            "max_salary": settings.get("kesehatan_max_salary", 12000000),
        }

    # Only include BPJS Ketenagakerjaan components if employee is enrolled
    # Default to 1 (enrolled) if field is missing
    if cint(emp.get("ikut_bpjs_ketenagakerjaan", 1)):
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


def hitung_bpjs(employee, gaji_pokok):
    """
    Calculate BPJS amounts for an employee
    
    Args:
        employee: Employee ID
        gaji_pokok: Base salary amount
        
    Returns:
        dict: Dictionary with BPJS calculation results
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

    # Basic validation
    if not employee or not gaji_pokok or gaji_pokok <= 0:
        debug_log(f"Invalid input: employee={employee}, gaji_pokok={gaji_pokok}")
        return result

    try:
        # Get employee document
        emp = frappe.get_doc("Employee", employee)
        
        # Get BPJS settings
        settings = get_bpjs_settings()
        
        # Get configuration based on enrollment status
        config = get_bpjs_config(emp, settings)
        
        # If no config (not enrolled in any program), return zeros
        if not config:
            debug_log(f"Employee {employee} not participating in any BPJS program")
            return result

        # Calculate BPJS Kesehatan if enrolled
        if "kesehatan" in config:
            # Apply salary cap
            kesehatan_salary = min(gaji_pokok, config["kesehatan"].get("max_salary", gaji_pokok))
            
            # Calculate contributions
            result["kesehatan_employee"] = flt(kesehatan_salary * config["kesehatan"]["employee_percent"] / 100)
            result["kesehatan_employer"] = flt(kesehatan_salary * config["kesehatan"]["employer_percent"] / 100)

        # Calculate BPJS JHT if enrolled
        if "jht" in config:
            result["jht_employee"] = flt(gaji_pokok * config["jht"]["employee_percent"] / 100)
            result["jht_employer"] = flt(gaji_pokok * config["jht"]["employer_percent"] / 100)

        # Calculate BPJS JP if enrolled with salary cap
        if "jp" in config:
            jp_salary = min(gaji_pokok, config["jp"].get("max_salary", gaji_pokok))
            result["jp_employee"] = flt(jp_salary * config["jp"]["employee_percent"] / 100)
            result["jp_employer"] = flt(jp_salary * config["jp"]["employer_percent"] / 100)

        # Calculate BPJS JKK if enrolled
        if "jkk" in config:
            result["jkk_employer"] = flt(gaji_pokok * config["jkk"]["percent"] / 100)

        # Calculate BPJS JKM if enrolled
        if "jkm" in config:
            result["jkm_employer"] = flt(gaji_pokok * config["jkm"]["percent"] / 100)

        # Calculate totals with explicit conversion to float
        result["total_employee"] = flt(
            result["kesehatan_employee"] + result["jht_employee"] + result["jp_employee"]
        )
        result["total_employer"] = flt(
            result["kesehatan_employer"] + result["jht_employer"] +
            result["jp_employer"] + result["jkk_employer"] + result["jkm_employer"]
        )

        # Log result safely
        debug_log(f"BPJS result for {employee}: total_employee={result['total_employee']}, total_employer={result['total_employer']}")
        return result
        
    except Exception as e:
        # Log error but don't raise exception
        debug_log(f"Error calculating BPJS for {employee}: {str(e)}")
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

def hitung_bpjs(base_salary, settings=None):
    """
    Calculate BPJS contributions for given salary
    
    Args:
        base_salary (float): Base salary amount
        settings (obj, optional): BPJS Settings doc
        
    Returns:
        dict: Dictionary with calculated amounts
    """
    try:
        if not settings:
            settings = frappe.get_cached_doc("BPJS Settings", "BPJS Settings")
            
        if not settings:
            frappe.throw(_("BPJS Settings not found"))
            
        # Calculate each component
        results = {
            "kesehatan": {
                "employee": 0,
                "employer": 0
            },
            "jht": {
                "employee": 0,
                "employer": 0
            },
            "jp": {
                "employee": 0,
                "employer": 0  
            },
            "jkk": {
                "employer": 0
            },
            "jkm": {
                "employer": 0
            }
        }
        
        # BPJS Kesehatan
        max_kesehatan = flt(settings.kesehatan_max_salary)
        salary_for_kesehatan = min(base_salary, max_kesehatan)
        
        results["kesehatan"]["employee"] = flt(salary_for_kesehatan * settings.kesehatan_employee_percent / 100)
        results["kesehatan"]["employer"] = flt(salary_for_kesehatan * settings.kesehatan_employer_percent / 100)
        
        # BPJS JHT
        results["jht"]["employee"] = flt(base_salary * settings.jht_employee_percent / 100)
        results["jht"]["employer"] = flt(base_salary * settings.jht_employer_percent / 100)
        
        # BPJS JP
        max_jp = flt(settings.jp_max_salary)
        salary_for_jp = min(base_salary, max_jp)
        
        results["jp"]["employee"] = flt(salary_for_jp * settings.jp_employee_percent / 100)
        results["jp"]["employer"] = flt(salary_for_jp * settings.jp_employer_percent / 100)
        
        # BPJS JKK
        results["jkk"]["employer"] = flt(base_salary * settings.jkk_percent / 100)
        
        # BPJS JKM
        results["jkm"]["employer"] = flt(base_salary * settings.jkm_percent / 100)
        
        return results
        
    except Exception as e:
        frappe.log_error(f"Error calculating BPJS: {str(e)[:100]}", "BPJS Calculation Error")
        frappe.throw(_("Error calculating BPJS contributions"))