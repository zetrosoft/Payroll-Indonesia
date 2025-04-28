# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-28 02:45:00 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from .base import update_component_amount
from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import hitung_bpjs

# Debug function for error tracking
def debug_log(message, module_name="BPJS Calculator"):
    """Log debug message with timestamp and additional info"""
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
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
    
    # Check BPJS participation directly from employee fields
    ikut_bpjs_kesehatan = employee.get('ikut_bpjs_kesehatan', 1)
    ikut_bpjs_ketenagakerjaan = employee.get('ikut_bpjs_ketenagakerjaan', 1)
    
    debug_log(f"BPJS participation for {employee.name}: Kesehatan={ikut_bpjs_kesehatan}, Ketenagakerjaan={ikut_bpjs_ketenagakerjaan}")
    
    # Skip if employee doesn't participate in any BPJS programs
    if not ikut_bpjs_kesehatan and not ikut_bpjs_ketenagakerjaan:
        debug_log(f"Employee {employee.name} does not participate in any BPJS programs, skipping")
        return
    
    try:
        # Use hitung_bpjs function for calculation - all BPJS settings validation is handled there
        debug_log(f"Calling hitung_bpjs for employee {employee.name}, gaji_pokok: {gaji_pokok}")
        bpjs_result = hitung_bpjs(employee.name, gaji_pokok)
        debug_log(f"BPJS calculation result: {bpjs_result}")
        
        # Update components in salary slip based on participation and calculation results
        debug_log(f"Updating BPJS components in salary slip {doc.name}")
        
        # Kesehatan - only if employee participates
        if ikut_bpjs_kesehatan and bpjs_result["kesehatan_employee"] > 0:
            update_component_amount(
                doc,
                "BPJS Kesehatan Employee", 
                bpjs_result["kesehatan_employee"],
                "deductions"
            )
        
        # JHT and JP - only if employee participates in Ketenagakerjaan
        if ikut_bpjs_ketenagakerjaan:
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
            from payroll_indonesia.payroll_indonesia.utils import get_bpjs_settings
            settings = get_bpjs_settings()
            
            doc.payroll_note += "\n\n=== Perhitungan BPJS ==="
            
            if ikut_bpjs_kesehatan and total_bpjs_kesehatan > 0:
                kesehatan_percent = flt(settings.get("kesehatan_employee", 1.0))
                doc.payroll_note += f"\nBPJS Kesehatan ({kesehatan_percent}%): Rp {total_bpjs_kesehatan:,.0f}"
            
            if ikut_bpjs_ketenagakerjaan:
                jht_percent = flt(settings.get("jht_employee", 2.0))
                jp_percent = flt(settings.get("jp_employee", 1.0))
                
                if total_bpjs_jht > 0:
                    doc.payroll_note += f"\nBPJS JHT ({jht_percent}%): Rp {total_bpjs_jht:,.0f}"
                
                if total_bpjs_jp > 0:
                    doc.payroll_note += f"\nBPJS JP ({jp_percent}%): Rp {total_bpjs_jp:,.0f}"
            
            doc.payroll_note += f"\nTotal BPJS: Rp {doc.total_bpjs:,.0f}"
            
        except Exception as e:
            debug_log(f"Error updating payroll note: {str(e)}")
            # Continue even if payroll note update fails
            
        debug_log(f"BPJS components calculation completed for {doc.name}")
            
    except Exception as e:
        debug_log(f"BPJS Calculation Error for Employee {employee.name}: {str(e)}\n{frappe.get_traceback()}")
        frappe.log_error(
            f"BPJS Calculation Error for Employee {employee.name}: {str(e)}",
            "BPJS Calculation Error"
        )
        # Convert to user-friendly error
        frappe.throw(_("Error calculating BPJS components: {0}").format(str(e)))
