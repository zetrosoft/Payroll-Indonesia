# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import today, flt, getdate
from .bpjs_payment_utils import debug_log, add_component_if_positive
from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import hitung_bpjs

def extract_bpjs_from_salary_slip(slip):
    """Extract BPJS components from salary slip"""
    bpjs_components = {
        "employee": {},
        "employer": {}
    }
    
    # Extract employee contributions from deductions
    for deduction in slip.deductions:
        if deduction.salary_component == "BPJS JHT Employee":
            bpjs_components["employee"]["jht"] = flt(deduction.amount)
        elif deduction.salary_component == "BPJS JP Employee":
            bpjs_components["employee"]["jp"] = flt(deduction.amount)
        elif deduction.salary_component == "BPJS Kesehatan Employee":
            bpjs_components["employee"]["kesehatan"] = flt(deduction.amount)
    
    # Extract employer contributions from earnings
    for earning in slip.earnings:
        if earning.salary_component == "BPJS JHT Employer":
            bpjs_components["employer"]["jht"] = flt(earning.amount)
        elif earning.salary_component == "BPJS JP Employer":
            bpjs_components["employer"]["jp"] = flt(earning.amount)
        elif earning.salary_component == "BPJS Kesehatan Employer":
            bpjs_components["employer"]["kesehatan"] = flt(earning.amount)
        elif earning.salary_component == "BPJS JKK":
            bpjs_components["employer"]["jkk"] = flt(earning.amount)
        elif earning.salary_component == "BPJS JKM":
            bpjs_components["employer"]["jkm"] = flt(earning.amount)
            
    return bpjs_components

def create_new_bpjs_summary(slip, month, year):
    """Create a new BPJS Payment Summary"""
    debug_log(f"Creating new BPJS Payment Summary for {slip.company}, {month}/{year}")
    
    bpjs_summary = frappe.new_doc("BPJS Payment Summary")
    bpjs_summary.company = slip.company
    bpjs_summary.month = month
    bpjs_summary.year = year
    bpjs_summary.posting_date = today()
    
    # Get company details
    company_doc = frappe.get_doc("Company", slip.company)
    if company_doc:
        # Set company details like BPJS registration numbers if available
        for field in ['bpjs_company_registration', 'npwp', 'bpjs_branch_office']:
            if hasattr(company_doc, field):
                setattr(bpjs_summary, field, getattr(company_doc, field))
    
    # Initialize employee details and totals
    bpjs_summary.employee_details = []
    bpjs_summary.komponen = []
    
    return bpjs_summary

def add_employee_to_bpjs_summary(bpjs_summary, slip, bpjs_components):
    """Add an employee to BPJS Payment Summary"""
    debug_log(f"Adding employee {slip.employee} to BPJS Payment Summary {bpjs_summary.name}")
    
    employee = frappe.get_doc("Employee", slip.employee)
    
    # Create new employee detail
    employee_detail = {
        "employee": slip.employee,
        "employee_name": slip.employee_name,
        "salary_slip": slip.name,
        "department": getattr(employee, "department", ""),
        "designation": getattr(employee, "designation", ""),
        "bpjs_number": getattr(employee, "bpjs_number", ""),
        "nik": getattr(employee, "ktp", ""),
        "jht_employee": bpjs_components["employee"].get("jht", 0),
        "jp_employee": bpjs_components["employee"].get("jp", 0),
        "kesehatan_employee": bpjs_components["employee"].get("kesehatan", 0),
        "jht_employer": bpjs_components["employer"].get("jht", 0),
        "jp_employer": bpjs_components["employer"].get("jp", 0),
        "jkk": bpjs_components["employer"].get("jkk", 0),
        "jkm": bpjs_components["employer"].get("jkm", 0),
        "kesehatan_employer": bpjs_components["employer"].get("kesehatan", 0)
    }
    
    # Add to the employee_details child table
    bpjs_summary.append("employee_details", employee_detail)
    
    debug_log(f"Successfully added employee {slip.employee} to BPJS Payment Summary")

def update_employee_bpjs_details(employee_detail, slip, bpjs_components):
    """Update an employee's BPJS details"""
    debug_log(f"Updating BPJS details for employee {slip.employee}")
    
    # Update employee information
    employee_detail.employee_name = slip.employee_name
    employee_detail.salary_slip = slip.name
    
    # Update component amounts
    employee_detail.jht_employee = bpjs_components["employee"].get("jht", 0)
    employee_detail.jp_employee = bpjs_components["employee"].get("jp", 0)
    employee_detail.kesehatan_employee = bpjs_components["employee"].get("kesehatan", 0)
    employee_detail.jht_employer = bpjs_components["employer"].get("jht", 0)
    employee_detail.jp_employer = bpjs_components["employer"].get("jp", 0)
    employee_detail.jkk = bpjs_components["employer"].get("jkk", 0)
    employee_detail.jkm = bpjs_components["employer"].get("jkm", 0)
    employee_detail.kesehatan_employer = bpjs_components["employer"].get("kesehatan", 0)
    
    debug_log(f"Successfully updated BPJS details for employee {slip.employee}")

def recalculate_bpjs_totals(bpjs_summary):
    """Recalculate BPJS Payment Summary totals"""
    debug_log(f"Recalculating totals for BPJS Payment Summary {bpjs_summary.name}")
    
    # Calculate totals
    jht_total = 0
    jp_total = 0
    kesehatan_total = 0
    jkk_total = 0
    jkm_total = 0
    
    for emp in bpjs_summary.employee_details:
        jht_total += flt(emp.jht_employee) + flt(emp.jht_employer)
        jp_total += flt(emp.jp_employee) + flt(emp.jp_employer)
        kesehatan_total += flt(emp.kesehatan_employee) + flt(emp.kesehatan_employer)
        jkk_total += flt(emp.jkk)
        jkm_total += flt(emp.jkm)
    
    # Clear existing components
    bpjs_summary.komponen = []
    
    # Add components
    add_component_if_positive(bpjs_summary, "BPJS JHT", "JHT Contribution (Employee + Employer)", jht_total)
    add_component_if_positive(bpjs_summary, "BPJS JP", "JP Contribution (Employee + Employer)", jp_total)
    add_component_if_positive(bpjs_summary, "BPJS Kesehatan", "Kesehatan Contribution (Employee + Employer)", kesehatan_total)
    add_component_if_positive(bpjs_summary, "BPJS JKK", "JKK Contribution (Employer)", jkk_total)
    add_component_if_positive(bpjs_summary, "BPJS JKM", "JKM Contribution (Employer)", jkm_total)
    
    # Calculate grand total
    bpjs_summary.total = jht_total + jp_total + kesehatan_total + jkk_total + jkm_total
    
    debug_log(f"Successfully recalculated totals for BPJS Payment Summary {bpjs_summary.name}")

def get_or_create_bpjs_summary(slip, month, year):
    """Get existing BPJS Payment Summary or create a new one"""
    # Check if a BPJS Payment Summary already exists for this period
    bpjs_summary_name = frappe.db.get_value(
        "BPJS Payment Summary",
        {"company": slip.company, "year": year, "month": month, "docstatus": ["!=", 2]},
        "name"
    )
    
    if bpjs_summary_name:
        debug_log(f"Found existing BPJS Payment Summary: {bpjs_summary_name}")
        bpjs_summary = frappe.get_doc("BPJS Payment Summary", bpjs_summary_name)
        
        # Check if already submitted
        if bpjs_summary.docstatus > 0:
            debug_log(f"BPJS Payment Summary {bpjs_summary_name} already submitted, creating a new one")
            bpjs_summary = create_new_bpjs_summary(slip, month, year)
    else:
        debug_log(f"Creating new BPJS Payment Summary for {slip.company}, {year}, {month}")
        bpjs_summary = create_new_bpjs_summary(slip, month, year)
        
    return bpjs_summary

def trigger_bpjs_payment_component_creation(salary_slip, bpjs_summary_name):
    """Trigger creation of BPJS payment component if enabled in settings"""
    try:
        bpjs_settings = frappe.get_single("BPJS Settings")
        if hasattr(bpjs_settings, 'auto_create_component') and bpjs_settings.auto_create_component:
            debug_log(f"Auto-creating BPJS payment component for {salary_slip}")
            frappe.enqueue(
                method="payroll_indonesia.doctype.bpjs_payment_component.bpjs_payment_component.create_from_salary_slip",
                queue="short",
                timeout=300,
                is_async=True,
                **{"salary_slip": salary_slip, "bpjs_summary": bpjs_summary_name}
            )
    except Exception as e:
        debug_log(f"Error checking BPJS settings: {str(e)}")