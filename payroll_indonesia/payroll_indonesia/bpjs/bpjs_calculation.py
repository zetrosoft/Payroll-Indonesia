# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-28 03:02:00 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, now_datetime
from payroll_indonesia.payroll_indonesia.utils import get_bpjs_settings

# Debug function for error tracking
def debug_log(message, module_name="BPJS Calculation"):
    """Log debug message with timestamp and additional info"""
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    frappe.log_error(f"[{timestamp}] {message}", module_name)

def hitung_bpjs(employee, gaji_pokok):
    """
    Calculate BPJS contributions based on basic salary
    
    Args:
        employee (str): Employee ID
        gaji_pokok (float): Basic salary
        
    Returns:
        dict: BPJS calculation results
    """
    debug_log(f"Starting hitung_bpjs for employee={employee}, gaji_pokok={gaji_pokok}")
    
    try:
        # Initialize default result structure
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
        
        # Validate employee
        if not employee:
            debug_log("Employee ID not provided")
            return result
            
        # Validate gaji_pokok
        if not gaji_pokok or gaji_pokok <= 0:
            debug_log(f"Invalid gaji_pokok: {gaji_pokok}")
            return result
            
        # Get employee document with error handling
        try:
            emp = frappe.get_doc("Employee", employee)
            if not emp:
                debug_log(f"Employee document not found: {employee}")
                return result
        except Exception as e:
            debug_log(f"Error fetching employee {employee}: {str(e)}")
            return result
        
        # Get BPJS settings with error handling
        try:
            settings = get_bpjs_settings()
            if not settings:
                debug_log("BPJS settings not found")
                return result
            debug_log(f"BPJS settings: {settings}")
        except Exception as e:
            debug_log(f"Error fetching BPJS settings: {str(e)}")
            # Use default settings
            settings = {
                "kesehatan_employee": 1.0,
                "kesehatan_employer": 4.0,
                "jht_employee": 2.0,
                "jht_employer": 3.7,
                "jp_employee": 1.0,
                "jp_employer": 2.0,
                "jkk_employer": 0.24,
                "jkm_employer": 0.3,
                "max_salary": 12000000,
                "jp_max_salary": 9077600
            }
        
        # Check BPJS participation safely
        ikut_bpjs_kesehatan = emp.get("ikut_bpjs_kesehatan", 1)
        ikut_bpjs_ketenagakerjaan = emp.get("ikut_bpjs_ketenagakerjaan", 1)
        
        debug_log(f"BPJS participation for {employee}: Kesehatan={ikut_bpjs_kesehatan}, Ketenagakerjaan={ikut_bpjs_ketenagakerjaan}")
        
        # Skip if employee doesn't participate in any BPJS programs
        if not ikut_bpjs_kesehatan and not ikut_bpjs_ketenagakerjaan:
            debug_log(f"Employee {employee} does not participate in any BPJS programs")
            return result
        
        # Get maximum salary values
        kesehatan_max_salary = flt(settings.get("kesehatan", {}).get("max_salary", settings.get("max_salary", 12000000)))
        jp_max_salary = flt(settings.get("jp", {}).get("max_salary", settings.get("jp_max_salary", 9077600)))
        
        # Apply maximum salary cap for BPJS calculations
        kesehatan_salary = min(flt(gaji_pokok), kesehatan_max_salary)
        jp_salary = min(flt(gaji_pokok), jp_max_salary)
        
        # BPJS Kesehatan (Health Insurance)
        if ikut_bpjs_kesehatan:
            # Get rates from nested structure or flat structure
            kesehatan_employee_percent = flt(
                settings.get("kesehatan", {}).get("employee_percent", 
                settings.get("kesehatan_employee", 1.0))
            )
            
            kesehatan_employer_percent = flt(
                settings.get("kesehatan", {}).get("employer_percent", 
                settings.get("kesehatan_employer", 4.0))
            )
            
            # Calculate contributions
            result["kesehatan_employee"] = kesehatan_salary * kesehatan_employee_percent / 100
            result["kesehatan_employer"] = kesehatan_salary * kesehatan_employer_percent / 100
            
            debug_log(f"BPJS Kesehatan calculated: employee={result['kesehatan_employee']}, employer={result['kesehatan_employer']}")
        
        # BPJS Ketenagakerjaan (Employment Insurance)
        if ikut_bpjs_ketenagakerjaan:
            # Get rates from nested structure or flat structure
            
            # JHT (Jaminan Hari Tua - Old Age Security)
            jht_employee_percent = flt(
                settings.get("jht", {}).get("employee_percent", 
                settings.get("jht_employee", 2.0))
            )
            
            jht_employer_percent = flt(
                settings.get("jht", {}).get("employer_percent", 
                settings.get("jht_employer", 3.7))
            )
            
            result["jht_employee"] = flt(gaji_pokok) * jht_employee_percent / 100
            result["jht_employer"] = flt(gaji_pokok) * jht_employer_percent / 100
            
            # JP (Jaminan Pensiun - Pension Security)
            jp_employee_percent = flt(
                settings.get("jp", {}).get("employee_percent", 
                settings.get("jp_employee", 1.0))
            )
            
            jp_employer_percent = flt(
                settings.get("jp", {}).get("employer_percent", 
                settings.get("jp_employer", 2.0))
            )
            
            result["jp_employee"] = jp_salary * jp_employee_percent / 100
            result["jp_employer"] = jp_salary * jp_employer_percent / 100
            
            # JKK (Jaminan Kecelakaan Kerja - Work Accident Security)
            jkk_percent = flt(
                settings.get("jkk", {}).get("percent", 
                settings.get("jkk_employer", 0.24))
            )
            
            result["jkk_employer"] = flt(gaji_pokok) * jkk_percent / 100
            
            # JKM (Jaminan Kematian - Death Security)
            jkm_percent = flt(
                settings.get("jkm", {}).get("percent", 
                settings.get("jkm_employer", 0.3))
            )
            
            result["jkm_employer"] = flt(gaji_pokok) * jkm_percent / 100
            
            debug_log(f"BPJS Ketenagakerjaan calculated: JHT={result['jht_employee']}/{result['jht_employer']}, " +
                     f"JP={result['jp_employee']}/{result['jp_employer']}, " +
                     f"JKK={result['jkk_employer']}, JKM={result['jkm_employer']}")
        
        # Calculate totals
        result["total_employee"] = (
            result["kesehatan_employee"] +
            result["jht_employee"] +
            result["jp_employee"]
        )
        
        result["total_employer"] = (
            result["kesehatan_employer"] +
            result["jht_employer"] +
            result["jp_employer"] +
            result["jkk_employer"] +
            result["jkm_employer"]
        )
        
        debug_log(f"Total BPJS calculated: employee={result['total_employee']}, employer={result['total_employer']}")
        
        return result
        
    except Exception as e:
        debug_log(f"Error in hitung_bpjs: {str(e)}\n{frappe.get_traceback()}")
        frappe.log_error(
            f"Error calculating BPJS for employee {employee}: {str(e)}\nTraceback: {frappe.get_traceback()}",
            "BPJS Calculation Error"
        )
        
        # Return empty result structure to avoid breaking code that relies on it
        return {
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
