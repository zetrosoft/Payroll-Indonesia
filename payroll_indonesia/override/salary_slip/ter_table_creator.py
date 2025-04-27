# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 07:54:38 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate

from .base import get_component_amount

def create_pph_ter_table(doc):
    """Create or update PPh TER Table entry if using TER method"""
    try:
        # Only proceed if using TER
        if not getattr(doc, 'is_using_ter', 0):
            return
        
        # Check if PPh TER Table DocType exists
        if not frappe.db.exists("DocType", "PPh TER Table"):
            frappe.msgprint(_("PPh TER Table DocType not found. Cannot create TER entry."))
            return
    
        # Determine year and month from salary slip
        end_date = getdate(doc.end_date)
        month = end_date.month
        year = end_date.year
    
        # Get PPh 21 amount
        pph21_amount = get_component_amount(doc, "PPh 21", "deductions")
    
        # Get employee data
        employee_data = get_employee_data(doc)
    
        # Check if PPh TER Table exists for this period
        ter_table = find_existing_ter_table(doc, year, month)
    
        if not ter_table:
            create_new_ter_table(doc, year, month, pph21_amount, employee_data)
        else:
            update_existing_ter_table(doc, ter_table, pph21_amount, employee_data)
        
    except Exception as e:
        frappe.log_error(
            f"Error processing PPh TER Table for {doc.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "PPh TER Table Error"
        )
        frappe.throw(_("Error processing PPh TER Table: {0}").format(str(e)))

def get_employee_data(doc):
    """Get employee tax data"""
    try:
        employee = frappe.get_doc("Employee", doc.employee)
        
        # Get status pajak with fallback
        status_pajak = "TK0"  # Default
        if hasattr(employee, 'status_pajak') and employee.status_pajak:
            status_pajak = employee.status_pajak
            
        # Get NPWP with fallback
        npwp = ""
        if hasattr(employee, 'npwp'):
            npwp = employee.npwp
            
        # Get KTP with fallback  
        ktp = ""
        if hasattr(employee, 'ktp'):
            ktp = employee.ktp
            
        return {
            "status_pajak": status_pajak,
            "npwp": npwp,
            "ktp": ktp
        }
    except Exception as e:
        frappe.log_error(
            f"Error getting employee data for {doc.employee}: {str(e)}",
            "Employee Data Error"
        )
        return {"status_pajak": "TK0", "npwp": "", "ktp": ""}

def find_existing_ter_table(doc, year, month):
    """Find existing TER table for this period"""
    try:
        # Check column structure first
        doctype_meta = frappe.get_meta("PPh TER Table")
        if not (doctype_meta.has_field("year") and doctype_meta.has_field("month")):
            frappe.throw(_("PPh TER Table DocType missing required fields 'year' and/or 'month'"))
        
        return frappe.db.get_value(
            "PPh TER Table",
            {"company": doc.company, "year": year, "month": month, "docstatus": ["!=", 2]},
            "name"
        )
    except Exception as e:
        if "Unknown column" in str(e):
            frappe.throw(_(
                "Database structure issue: {0} - Please run 'bench migrate' "
                "or fix the PPh TER Table DocType structure."
            ).format(str(e)))
        else:
            frappe.throw(_("Error querying PPh TER Table: {0}").format(str(e)))

def create_new_ter_table(doc, year, month, pph21_amount, employee_data):
    """Create a new PPh TER Table"""
    try:
        ter_table_doc = frappe.new_doc("PPh TER Table")
        ter_table_doc.company = doc.company
        ter_table_doc.year = year
        ter_table_doc.month = month
        
        # Set period if field exists
        if hasattr(ter_table_doc, 'period'):
            month_names = ['January', 'February', 'March', 'April', 'May', 'June', 
                         'July', 'August', 'September', 'October', 'November', 'December']
            if month >= 1 and month <= 12:
                ter_table_doc.period = month_names[month-1]
    
        # Set title if field exists
        if hasattr(ter_table_doc, 'month_year_title'):
            month_names = ['January', 'February', 'March', 'April', 'May', 'June', 
                         'July', 'August', 'September', 'October', 'November', 'December']
            ter_table_doc.month_year_title = f"{month_names[month-1]} {year}" if month >= 1 and month <= 12 else f"{month}-{year}"
    
        # Check if details field exists
        if not hasattr(ter_table_doc, 'details'):
            frappe.throw(_("PPh TER Table structure is invalid. Missing details child table."))
    
        # Create first employee detail
        add_employee_to_ter_table(ter_table_doc, doc, pph21_amount, employee_data)
    
        ter_table_doc.insert(ignore_permissions=True)
    except Exception as e:
        frappe.throw(_("Error creating PPh TER Table: {0}").format(str(e)))

def update_existing_ter_table(doc, ter_table_name, pph21_amount, employee_data):
    """Update existing PPh TER Table"""
    try:
        ter_table_doc = frappe.get_doc("PPh TER Table", ter_table_name)
    
        # Check if details field exists
        if not hasattr(ter_table_doc, 'details'):
            frappe.throw(_("PPh TER Table structure is invalid. Missing details child table."))
    
        # Check if employee already exists
        employee_exists = False
        for detail in ter_table_doc.details:
            if detail.employee == doc.employee:
                # Update existing employee
                update_ter_table_detail(detail, doc, pph21_amount, employee_data)
                employee_exists = True
                break
    
        if not employee_exists:
            # Add new employee
            add_employee_to_ter_table(ter_table_doc, doc, pph21_amount, employee_data)
    
        # Save changes
        ter_table_doc.save(ignore_permissions=True)
    except Exception as e:
        frappe.throw(_("Error updating PPh TER Table: {0}").format(str(e)))

def add_employee_to_ter_table(ter_doc, salary_slip, pph21_amount, employee_data):
    """Add employee details to TER Table document"""
    ter_doc.append("details", {
        "employee": salary_slip.employee,
        "employee_name": salary_slip.employee_name,
        "npwp": employee_data["npwp"],
        "ktp": employee_data["ktp"],
        "biaya_jabatan": getattr(salary_slip, 'biaya_jabatan', 0),
        "penghasilan_bruto": salary_slip.gross_pay,
        "penghasilan_netto": getattr(salary_slip, 'netto', salary_slip.gross_pay),
        "penghasilan_kena_pajak": getattr(salary_slip, 'netto', salary_slip.gross_pay),
        "amount": pph21_amount
    })

def update_ter_table_detail(detail, salary_slip, pph21_amount, employee_data):
    """Update TER table detail for an existing employee"""
    detail.npwp = employee_data["npwp"]
    detail.ktp = employee_data["ktp"]
    detail.biaya_jabatan = getattr(salary_slip, 'biaya_jabatan', 0)
    detail.penghasilan_bruto = salary_slip.gross_pay
    detail.penghasilan_netto = getattr(salary_slip, 'netto', salary_slip.gross_pay)
    detail.penghasilan_kena_pajak = getattr(salary_slip, 'netto', salary_slip.gross_pay)
    detail.amount = pph21_amount