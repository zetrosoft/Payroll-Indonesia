# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-28 03:01:00 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from .base import update_component_amount
from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import hitung_bpjs

# Debug function for error tracking
# Replace in bpjs_calculator.py
def debug_log(message, module_name="BPJS Calculator", max_length=2000):
    """Log debug message with timestamp and additional info with length limit"""
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    
    # Truncate message if too long
    if len(message) > max_length:
        message = message[:max_length-50] + f"... (truncated, full length: {len(message)})"
        
    frappe.log_error(f"[{timestamp}] {message}", module_name)

def calculate_bpjs_components(doc, employee, gaji_pokok):
    """
    Calculate and update BPJS components in salary slip
    Delegates actual calculation to hitung_bpjs function
    """
    debug_log(f"Starting calculate_bpjs_components for {doc.name}, employee: {employee.name}")
    
    # Ensure payroll_note is initialized as empty string
    if not hasattr(doc, 'payroll_note') or doc.payroll_note is None:
        doc.payroll_note = ""
    
    try:
        # Use hitung_bpjs function for calculation
        debug_log(f"Calling hitung_bpjs for employee {employee.name}, gaji_pokok: {gaji_pokok}")
        bpjs_result = hitung_bpjs(employee.name, gaji_pokok)
        debug_log(f"BPJS calculation result: {bpjs_result}")
        
        # If no contributions calculated, skip the rest
        if bpjs_result["total_employee"] <= 0:
            debug_log(f"No BPJS contributions for {employee.name}, skipping component update")
            return
        
        # Update components in salary slip
        debug_log(f"Updating BPJS components in salary slip {doc.name}")
        
        # Kesehatan
        if bpjs_result["kesehatan_employee"] > 0:
            update_component_amount(
                doc,
                "BPJS Kesehatan Employee", 
                bpjs_result["kesehatan_employee"],
                "deductions"
            )
        
        # JHT
        if bpjs_result["jht_employee"] > 0:
            update_component_amount(
                doc,
                "BPJS JHT Employee", 
                bpjs_result["jht_employee"],
                "deductions"
            )
        
        # JP
        if bpjs_result["jp_employee"] > 0:
            update_component_amount(
                doc,
                "BPJS JP Employee",
                bpjs_result["jp_employee"],
                "deductions"
            )
        
        # Calculate total BPJS for tax purposes (use actual values from salary slip)
        total_bpjs_kesehatan = 0
        total_bpjs_jht = 0
        total_bpjs_jp = 0
        
        for d in doc.deductions:
            if d.salary_component == "BPJS Kesehatan Employee":
                total_bpjs_kesehatan = flt(d.amount)
            elif d.salary_component == "BPJS JHT Employee":
                total_bpjs_jht = flt(d.amount)
            elif d.salary_component == "BPJS JP Employee":
                total_bpjs_jp = flt(d.amount)
        
        doc.total_bpjs = total_bpjs_kesehatan + total_bpjs_jht + total_bpjs_jp
        debug_log(f"Total BPJS for {doc.name}: {doc.total_bpjs}")
        
        # Update payroll note with BPJS details
        try:
            # Get BPJS settings
            from payroll_indonesia.payroll_indonesia.utils import get_bpjs_settings
            settings = get_bpjs_settings()
            
            doc.payroll_note += "\n\n=== Perhitungan BPJS ==="
            
            # Show Kesehatan if applicable
            if total_bpjs_kesehatan > 0:
                kesehatan_percent = settings.get("kesehatan", {}).get("employee_percent", 1.0)
                doc.payroll_note += f"\nBPJS Kesehatan ({kesehatan_percent}%): Rp {total_bpjs_kesehatan:,.0f}"
            
            # Show JHT and JP if applicable
            if total_bpjs_jht > 0:
                jht_percent = settings.get("jht", {}).get("employee_percent", 2.0)
                doc.payroll_note += f"\nBPJS JHT ({jht_percent}%): Rp {total_bpjs_jht:,.0f}"
            
            if total_bpjs_jp > 0:
                jp_percent = settings.get("jp", {}).get("employee_percent", 1.0)
                doc.payroll_note += f"\nBPJS JP ({jp_percent}%): Rp {total_bpjs_jp:,.0f}"
            
            doc.payroll_note += f"\nTotal BPJS: Rp {doc.total_bpjs:,.0f}"
            
        except Exception as e:
            debug_log(f"Error updating payroll note: {str(e)}")
            # Continue even if payroll note update fails
            
        debug_log(f"BPJS components calculation completed for {doc.name}")
            
    except Exception as e:
        # Truncate log message manually to avoid size limit issues (140 chars)
        error_msg = f'BPJS Calculation Error for {doc.name}: {str(e)}'
        if len(error_msg) > 130:  # Leaving some margin from 140 limit
            error_msg = error_msg[:127] + '...'
        frappe.log_error(error_msg, "BPJS Calculation Error")
        
        # Re-raise or handle based on your error handling strategy
        frappe.msgprint(_("Error in BPJS calculation. See error log for details."))

        # Convert to user-friendly error
        frappe.throw(_("Error calculating BPJS components: {0}").format(str(e)))


