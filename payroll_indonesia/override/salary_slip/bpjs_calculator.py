# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 07:35:26 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt

from .base import update_component_amount

def calculate_bpjs_components(doc, employee, gaji_pokok):
    """Calculate and update BPJS components based on settings"""
    # Ensure payroll_note is initialized as empty string
    if not hasattr(doc, 'payroll_note') or doc.payroll_note is None:
        doc.payroll_note = ""
        
    # Initialize BPJS participation fields if not exist
    if not hasattr(employee, 'ikut_bpjs_ketenagakerjaan'):
        employee.ikut_bpjs_ketenagakerjaan = 0
        frappe.msgprint(_("BPJS Ketenagakerjaan participation not set for employee {0}, using default (No)").format(employee.name))
        
    if not hasattr(employee, 'ikut_bpjs_kesehatan'):
        employee.ikut_bpjs_kesehatan = 0
        frappe.msgprint(_("BPJS Kesehatan participation not set for employee {0}, using default (No)").format(employee.name))
        
    # Skip if employee doesn't participate in any BPJS programs
    if not employee.ikut_bpjs_ketenagakerjaan and not employee.ikut_bpjs_kesehatan:
        return
    
    try:
        # Get BPJS Settings with validation
        try:
            bpjs_settings = frappe.get_single("BPJS Settings")
        except Exception as e:
            frappe.throw(_("Error retrieving BPJS Settings: {0}. Please configure BPJS Settings properly.").format(str(e)))
            
        # Validate required fields in BPJS Settings
        required_bpjs_fields = [
            'kesehatan_max_salary', 'kesehatan_employee_percent',
            'jht_employee_percent', 'jp_max_salary', 'jp_employee_percent'
        ]
        
        for field in required_bpjs_fields:
            if not hasattr(bpjs_settings, field) or getattr(bpjs_settings, field) is None:
                frappe.throw(_("BPJS Settings missing required field: {0}").format(field))
        
        # Initialize values
        kesehatan_employee = 0
        jht_employee = 0
        jp_employee = 0
        
        # Calculate Kesehatan contribution
        if employee.ikut_bpjs_kesehatan:
            # Limit salary for BPJS Kesehatan calculation
            kesehatan_salary = min(gaji_pokok, bpjs_settings.kesehatan_max_salary)
            kesehatan_employee = kesehatan_salary * (bpjs_settings.kesehatan_employee_percent / 100)
            
            update_component_amount(
                doc,
                "BPJS Kesehatan Employee", 
                kesehatan_employee,
                "deductions"
            )
        
        # Calculate Ketenagakerjaan contributions
        if employee.ikut_bpjs_ketenagakerjaan:
            # JHT has no salary limit
            jht_employee = gaji_pokok * (bpjs_settings.jht_employee_percent / 100)
            
            # Limit salary for JP calculation
            jp_salary = min(gaji_pokok, bpjs_settings.jp_max_salary)
            jp_employee = jp_salary * (bpjs_settings.jp_employee_percent / 100)
            
            # Update components
            update_component_amount(
                doc,
                "BPJS JHT Employee", 
                jht_employee,
                "deductions"
            )
            
            update_component_amount(
                doc,
                "BPJS JP Employee",
                jp_employee,
                "deductions"
            )
        
        # Calculate total BPJS for tax purposes with double verification
        total_bpjs_kesehatan = 0
        total_bpjs_jht = 0
        total_bpjs_jp = 0
        
        if employee.ikut_bpjs_kesehatan:
            for d in doc.deductions:
                if d.salary_component == "BPJS Kesehatan Employee":
                    total_bpjs_kesehatan = flt(d.amount)
                    break
            
        if employee.ikut_bpjs_ketenagakerjaan:
            for d in doc.deductions:
                if d.salary_component == "BPJS JHT Employee":
                    total_bpjs_jht = flt(d.amount)
                elif d.salary_component == "BPJS JP Employee":
                    total_bpjs_jp = flt(d.amount)
        
        doc.total_bpjs = total_bpjs_kesehatan + total_bpjs_jht + total_bpjs_jp
        
        # Update payroll note with BPJS details
        doc.payroll_note += "\n\n=== Perhitungan BPJS ==="
        
        if employee.ikut_bpjs_kesehatan:
            doc.payroll_note += f"\nBPJS Kesehatan ({bpjs_settings.kesehatan_employee_percent}%): Rp {total_bpjs_kesehatan:,.0f}"
        
        if employee.ikut_bpjs_ketenagakerjaan:
            doc.payroll_note += f"\nBPJS JHT ({bpjs_settings.jht_employee_percent}%): Rp {total_bpjs_jht:,.0f}"
            doc.payroll_note += f"\nBPJS JP ({bpjs_settings.jp_employee_percent}%): Rp {total_bpjs_jp:,.0f}"
        
        doc.payroll_note += f"\nTotal BPJS: Rp {doc.total_bpjs:,.0f}"
            
    except Exception as e:
        frappe.log_error(
            f"BPJS Calculation Error for Employee {employee.name}: {str(e)}",
            "BPJS Calculation Error"
        )
        # Convert to user-friendly error
        frappe.throw(_("Error calculating BPJS components: {0}").format(str(e)))