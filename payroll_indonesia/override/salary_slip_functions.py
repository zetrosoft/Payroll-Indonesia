# -*- coding: utf-8 -*-
# Copyright (c) 2025, Danny Audian and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt

def validate_salary_slip(doc, method=None):
    """Additional validation for salary slip"""
    # Check if all required components exist in salary slip
    required_components = {
        "earnings": ["Gaji Pokok"],
        "deductions": [
            "BPJS JHT Employee",
            "BPJS JP Employee", 
            "BPJS Kesehatan Employee",
            "PPh 21"
        ]
    }
    
    for component_type, components in required_components.items():
        components_in_slip = [d.salary_component for d in getattr(doc, component_type)]
        for component in components:
            if component not in components_in_slip:
                # Add the missing component if it exists in the system
                if frappe.db.exists("Salary Component", component):
                    try:
                        # Get abbr from component
                        component_doc = frappe.get_doc("Salary Component", component)
                        
                        # Create a new row
                        doc.append(component_type, {
                            "salary_component": component,
                            "abbr": component_doc.salary_component_abbr,
                            "amount": 0
                        })
                        
                        frappe.msgprint(f"Added missing component: {component}")
                    except Exception as e:
                        frappe.log_error(f"Error adding component {component}: {str(e)}")

def on_submit_salary_slip(doc, method=None):
    """Actions after salary slip is submitted"""
    # Update employee YTD tax paid
    update_employee_ytd_tax(doc)
    
    # Log payroll event
    log_payroll_event(doc)

def update_employee_ytd_tax(doc):
    """Update employee's year-to-date tax information"""
    try:
        # Get the current year
        import datetime
        current_year = doc.end_date.year
        
        # Get the PPh 21 amount
        pph21_amount = 0
        for deduction in doc.deductions:
            if deduction.salary_component == "PPh 21":
                pph21_amount = flt(deduction.amount)
                break
        
        if pph21_amount > 0:
            # Check if we have a YTD tax record for this employee
            ytd_tax = frappe.db.get_value(
                "Employee Tax Summary",
                {"employee": doc.employee, "year": current_year},
                ["name", "ytd_tax"]
            )
            
            if ytd_tax:
                # Update existing record
                tax_doc = frappe.get_doc("Employee Tax Summary", ytd_tax[0])
                tax_doc.ytd_tax = flt(ytd_tax[1]) + pph21_amount
                tax_doc.save(ignore_permissions=True)
            else:
                # Create new record
                tax_doc = frappe.new_doc("Employee Tax Summary")
                tax_doc.employee = doc.employee
                tax_doc.year = current_year
                tax_doc.ytd_tax = pph21_amount
                tax_doc.insert(ignore_permissions=True)
                
    except Exception as e:
        frappe.log_error(f"Error updating YTD tax for {doc.employee}: {str(e)}")

def log_payroll_event(doc):
    """Log payroll processing event"""
    try:
        log = frappe.new_doc("Payroll Log")
        log.employee = doc.employee
        log.employee_name = doc.employee_name
        log.salary_slip = doc.name
        log.posting_date = doc.posting_date
        log.gross_pay = doc.gross_pay
        log.net_pay = doc.net_pay
        log.status = "Success"
        log.insert(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(f"Error logging payroll event for {doc.employee}: {str(e)}")