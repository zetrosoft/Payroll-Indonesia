# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 07:54:38 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate

from .base import get_component_amount

def create_tax_summary(doc):
    """Create or update Employee Tax Summary entry"""
    try:
        year = getdate(doc.end_date).year
        month = getdate(doc.end_date).month
    
        # Get the PPh 21 amount
        pph21_amount = get_component_amount(doc, "PPh 21", "deductions")
    
        # Get BPJS components from salary slip
        bpjs_deductions = 0
        for deduction in doc.deductions:
            if deduction.salary_component in ["BPJS JHT Employee", "BPJS JP Employee", "BPJS Kesehatan Employee"]:
                bpjs_deductions += flt(deduction.amount)
    
        # Check if Employee Tax Summary DocType exists
        if not frappe.db.exists("DocType", "Employee Tax Summary"):
            frappe.msgprint(_("Employee Tax Summary DocType not found. Cannot create tax summary."))
            return
    
        # Check if we already have a record for this employee/year combination
        existing_tax_summary = frappe.db.get_value("Employee Tax Summary", 
            {"employee": doc.employee, "year": year}, "name")
    
        if existing_tax_summary:
            update_tax_summary(doc, existing_tax_summary, month, pph21_amount, bpjs_deductions)
        else:
            create_new_tax_summary(doc, year, month, pph21_amount, bpjs_deductions)
        
    except Exception as e:
        frappe.log_error(
            f"Error processing Tax Summary for {doc.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Tax Summary Error"
        )
        frappe.throw(_("Error processing Tax Summary: {0}").format(str(e)))

def update_tax_summary(doc, existing_tax_summary, month, pph21_amount, bpjs_deductions):
    """Update existing tax summary record"""
    try:
        tax_record = frappe.get_doc("Employee Tax Summary", existing_tax_summary)
    
        # Check if monthly_details field exists
        if not hasattr(tax_record, 'monthly_details'):
            frappe.throw(_("Employee Tax Summary structure is invalid. Missing monthly_details child table."))
    
        # Append monthly detail
        has_month = False
        for m in tax_record.monthly_details:
            if hasattr(m, 'month') and m.month == month:
                m.gross_pay = doc.gross_pay
                m.bpjs_deductions = bpjs_deductions
                m.tax_amount = pph21_amount
                m.salary_slip = doc.name
                m.is_using_ter = 1 if getattr(doc, 'is_using_ter', 0) else 0
                m.ter_rate = getattr(doc, 'ter_rate', 0)
                has_month = True
                break
    
        if not has_month:
            # Create new monthly entry
            monthly_data = {
                "month": month,
                "salary_slip": doc.name,
                "gross_pay": doc.gross_pay,
                "bpjs_deductions": bpjs_deductions,
                "tax_amount": pph21_amount,
                "is_using_ter": 1 if getattr(doc, 'is_using_ter', 0) else 0,
                "ter_rate": getattr(doc, 'ter_rate', 0)
            }
        
            # Add to monthly_details
            tax_record.append("monthly_details", monthly_data)
    
        # Recalculate YTD tax
        total_tax = 0
        if tax_record.monthly_details:
            for m in tax_record.monthly_details:
                if hasattr(m, 'tax_amount'):
                    total_tax += flt(m.tax_amount)
    
        tax_record.ytd_tax = total_tax
    
        # Set title if empty
        if not tax_record.title:
            tax_record.title = f"{doc.employee_name} - {tax_record.year}"
        
        # Set TER information at year level if applicable
        if hasattr(tax_record, 'is_using_ter') and hasattr(tax_record, 'ter_rate'):
            if getattr(doc, 'is_using_ter', 0):
                tax_record.is_using_ter = 1
                tax_record.ter_rate = getattr(doc, 'ter_rate', 0)
        
        tax_record.save(ignore_permissions=True)
    except Exception as e:
        frappe.throw(_("Error updating Tax Summary: {0}").format(str(e)))

def create_new_tax_summary(doc, year, month, pph21_amount, bpjs_deductions):
    """Create a new tax summary record"""
    try:
        tax_record = frappe.new_doc("Employee Tax Summary")
    
        # Set basic fields
        tax_record.employee = doc.employee
        tax_record.employee_name = doc.employee_name
        tax_record.year = year
        tax_record.ytd_tax = pph21_amount
        tax_record.title = f"{doc.employee_name} - {year}"
    
        # Set TER information if applicable and fields exist
        if hasattr(tax_record, 'is_using_ter') and hasattr(tax_record, 'ter_rate'):
            if getattr(doc, 'is_using_ter', 0):
                tax_record.is_using_ter = 1
                tax_record.ter_rate = getattr(doc, 'ter_rate', 0)
    
        # Add monthly detail
        monthly_data = {
            "month": month,
            "salary_slip": doc.name,
            "gross_pay": doc.gross_pay,
            "bpjs_deductions": bpjs_deductions,
            "tax_amount": pph21_amount,
            "is_using_ter": 1 if getattr(doc, 'is_using_ter', 0) else 0,
            "ter_rate": getattr(doc, 'ter_rate', 0)
        }
    
        # Add to monthly_details if field exists
        if hasattr(tax_record, 'monthly_details'):
            tax_record.append("monthly_details", monthly_data)
        else:
            frappe.throw(_("Employee Tax Summary structure is invalid. Missing monthly_details child table."))
    
        tax_record.insert(ignore_permissions=True)
    except Exception as e:
        frappe.throw(_("Error creating new Tax Summary: {0}").format(str(e)))