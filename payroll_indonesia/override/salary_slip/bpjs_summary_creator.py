# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 09:05:21 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate

def create_bpjs_payment_summary(doc):
    """Create or update BPJS Payment Summary based on submitted salary slip"""
    try:
        # Check if BPJS Payment Summary DocType exists
        if not frappe.db.exists("DocType", "BPJS Payment Summary"):
            frappe.msgprint(_("BPJS Payment Summary DocType not found. Cannot create BPJS summary."))
            return
            
        # Determine year and month from salary slip
        end_date = getdate(doc.end_date)
        month = end_date.month
        year = end_date.year
    
        # Get BPJS components from salary slip
        bpjs_employee_components = get_bpjs_employee_components(doc)
        bpjs_employer_components = calculate_bpjs_employer_components(doc)
    
        # Check if BPJS Payment Summary exists for this period
        bpjs_summary = find_existing_bpjs_summary(doc, year, month)
    
        if not bpjs_summary:
            create_new_bpjs_summary(doc, year, month, bpjs_employee_components, bpjs_employer_components)
        else:
            update_existing_bpjs_summary(doc, bpjs_summary, bpjs_employee_components, bpjs_employer_components)
        
    except Exception as e:
        frappe.log_error(
            f"Error creating/updating BPJS Payment Summary for {doc.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Summary Error"
        )
        frappe.throw(_("Error creating/updating BPJS Payment Summary: {0}").format(str(e)))

def get_bpjs_employee_components(doc):
    """Get BPJS employee components from salary slip"""
    bpjs_data = {
        "jht_employee": 0,
        "jp_employee": 0,
        "kesehatan_employee": 0
    }

    # Get employee components
    for deduction in doc.deductions:
        if deduction.salary_component == "BPJS JHT Employee":
            bpjs_data["jht_employee"] = flt(deduction.amount)
        elif deduction.salary_component == "BPJS JP Employee":
            bpjs_data["jp_employee"] = flt(deduction.amount)
        elif deduction.salary_component == "BPJS Kesehatan Employee":
            bpjs_data["kesehatan_employee"] = flt(deduction.amount)
            
    return bpjs_data

def calculate_bpjs_employer_components(doc):
    """Calculate BPJS employer components based on BPJS settings"""
    try:
        # Get BPJS Settings for employer calculations
        bpjs_settings = frappe.get_single("BPJS Settings")
        
        # Validate required fields exist in BPJS Settings
        required_fields = [
            'jht_employer_percent', 'jp_max_salary', 'jp_employer_percent',
            'jkk_percent', 'jkm_percent', 'kesehatan_max_salary',
            'kesehatan_employer_percent'
        ]
    
        for field in required_fields:
            if not hasattr(bpjs_settings, field) or getattr(bpjs_settings, field) is None:
                frappe.throw(_("BPJS Settings missing required field: {0}").format(field))
    
        # Calculate employer components
        # JHT Employer (3.7%)
        jht_employer = doc.gross_pay * (bpjs_settings.jht_employer_percent / 100)
    
        # JP Employer (2%)
        jp_salary = min(doc.gross_pay, bpjs_settings.jp_max_salary)
        jp_employer = jp_salary * (bpjs_settings.jp_employer_percent / 100)
    
        # JKK (0.24% - 1.74% depending on risk)
        jkk = doc.gross_pay * (bpjs_settings.jkk_percent / 100)
    
        # JKM (0.3%)
        jkm = doc.gross_pay * (bpjs_settings.jkm_percent / 100)
    
        # Kesehatan Employer (4%)
        kesehatan_salary = min(doc.gross_pay, bpjs_settings.kesehatan_max_salary)
        kesehatan_employer = kesehatan_salary * (bpjs_settings.kesehatan_employer_percent / 100)
        
        return {
            "jht_employer": jht_employer,
            "jp_employer": jp_employer,
            "jkk": jkk,
            "jkm": jkm,
            "kesehatan_employer": kesehatan_employer
        }
        
    except Exception as e:
        frappe.throw(_("Error calculating employer BPJS components: {0}").format(str(e)))

def find_existing_bpjs_summary(doc, year, month):
    """Find existing BPJS Payment Summary for this period"""
    try:
        # Check column structure first
        doctype_meta = frappe.get_meta("BPJS Payment Summary")
        if not (doctype_meta.has_field("year") and doctype_meta.has_field("month")):
            frappe.throw(_("BPJS Payment Summary DocType missing required fields 'year' and/or 'month'"))
        
        return frappe.db.get_value(
            "BPJS Payment Summary",
            {"company": doc.company, "year": year, "month": month, "docstatus": ["!=", 2]},
            "name"
        )
    except Exception as e:
        if "Unknown column" in str(e):
            frappe.throw(_(
                "Database structure issue: {0} - Please run 'bench migrate' "
                "or fix the BPJS Payment Summary DocType structure."
            ).format(str(e)))
        else:
            frappe.throw(_("Error querying BPJS Payment Summary: {0}").format(str(e)))

def create_new_bpjs_summary(doc, year, month, employee_components, employer_components):
    """Create a new BPJS Payment Summary"""
    try:
        bpjs_summary_doc = frappe.new_doc("BPJS Payment Summary")
        bpjs_summary_doc.company = doc.company
        bpjs_summary_doc.year = year
        bpjs_summary_doc.month = month
        bpjs_summary_doc.posting_date = getdate()
        
        # Set month name if field exists
        if hasattr(bpjs_summary_doc, 'month_name'):
            month_names = ['January', 'February', 'March', 'April', 'May', 'June', 
                          'July', 'August', 'September', 'October', 'November', 'December']
            if month >= 1 and month <= 12:
                bpjs_summary_doc.month_name = month_names[month-1]
    
        # Set title if field exists
        if hasattr(bpjs_summary_doc, 'month_year_title'):
            bpjs_summary_doc.month_year_title = f"{month_names[month-1]} {year}" if month >= 1 and month <= 12 else f"{month}-{year}"
    
        # Check if employee_details field exists
        if not hasattr(bpjs_summary_doc, 'employee_details'):
            frappe.throw(_("BPJS Payment Summary structure is invalid. Missing employee_details child table."))
    
        # Create first employee detail
        add_employee_to_bpjs_summary(bpjs_summary_doc, doc, employee_components, employer_components)
    
        # Add BPJS Payment Components for detailed tracking
        create_bpjs_payment_summary_components(bpjs_summary_doc, employee_components, employer_components)
    
        bpjs_summary_doc.insert(ignore_permissions=True)
        
        # Trigger the set_account_details method manually
        # This will populate account_details from BPJS Settings
        bpjs_summary_doc.set_account_details()
        bpjs_summary_doc.save(ignore_permissions=True)
        
    except Exception as e:
        frappe.throw(_("Error creating BPJS Payment Summary: {0}").format(str(e)))

def update_existing_bpjs_summary(doc, bpjs_summary_name, employee_components, employer_components):
    """Update existing BPJS Payment Summary"""
    try:
        bpjs_summary_doc = frappe.get_doc("BPJS Payment Summary", bpjs_summary_name)
    
        # Check if employee_details field exists
        if not hasattr(bpjs_summary_doc, 'employee_details'):
            frappe.throw(_("BPJS Payment Summary structure is invalid. Missing employee_details child table."))
    
        # Check if employee already exists
        employee_exists = False
        for detail in bpjs_summary_doc.employee_details:
            if detail.employee == doc.employee:
                # Update existing employee
                update_bpjs_summary_detail(detail, doc, employee_components, employer_components)
                employee_exists = True
                break
    
        if not employee_exists:
            # Add new employee
            add_employee_to_bpjs_summary(bpjs_summary_doc, doc, employee_components, employer_components)
    
        # Update komponen table
        update_bpjs_payment_summary_components(bpjs_summary_doc)
    
        # Save changes
        bpjs_summary_doc.save(ignore_permissions=True)
        
        # Trigger the set_account_details method manually
        # This will update account_details from BPJS Settings
        bpjs_summary_doc.set_account_details()
        bpjs_summary_doc.save(ignore_permissions=True)
        
    except Exception as e:
        frappe.throw(_("Error updating BPJS Payment Summary: {0}").format(str(e)))

def add_employee_to_bpjs_summary(bpjs_doc, salary_slip, employee_components, employer_components):
    """Add employee details to BPJS Summary document"""
    bpjs_doc.append("employee_details", {
        "employee": salary_slip.employee,
        "employee_name": salary_slip.employee_name,
        "salary_slip": salary_slip.name,
        "jht_employee": employee_components["jht_employee"],
        "jp_employee": employee_components["jp_employee"],
        "kesehatan_employee": employee_components["kesehatan_employee"],
        "jht_employer": employer_components["jht_employer"],
        "jp_employer": employer_components["jp_employer"],
        "jkk": employer_components["jkk"],
        "jkm": employer_components["jkm"],
        "kesehatan_employer": employer_components["kesehatan_employer"]
    })

def update_bpjs_summary_detail(detail, salary_slip, employee_components, employer_components):
    """Update BPJS summary detail for an existing employee"""
    detail.salary_slip = salary_slip.name
    detail.jht_employee = employee_components["jht_employee"]
    detail.jp_employee = employee_components["jp_employee"]
    detail.kesehatan_employee = employee_components["kesehatan_employee"]
    detail.jht_employer = employer_components["jht_employer"]
    detail.jp_employer = employer_components["jp_employer"]
    detail.jkk = employer_components["jkk"]
    detail.jkm = employer_components["jkm"]
    detail.kesehatan_employer = employer_components["kesehatan_employer"]

def create_bpjs_payment_summary_components(bpjs_summary_doc, employee_components, employer_components):
    """Create BPJS Payment Components for the payment summary"""
    # Clear existing components if any
    bpjs_summary_doc.komponen = []
    
    # Add JHT component (employee + employer)
    jht_total = employee_components["jht_employee"] + employer_components["jht_employer"]
    if jht_total > 0:
        bpjs_summary_doc.append("komponen", {
            "component": "BPJS JHT",
            "description": "JHT Contribution (Employee + Employer)",
            "amount": jht_total
        })
    
    # Add JP component (employee + employer)
    jp_total = employee_components["jp_employee"] + employer_components["jp_employer"]
    if jp_total > 0:
        bpjs_summary_doc.append("komponen", {
            "component": "BPJS JP",
            "description": "JP Contribution (Employee + Employer)",
            "amount": jp_total
        })
    
    # Add JKK component
    if employer_components["jkk"] > 0:
        bpjs_summary_doc.append("komponen", {
            "component": "BPJS JKK",
            "description": "JKK Contribution (Employer)",
            "amount": employer_components["jkk"]
        })
    
    # Add JKM component
    if employer_components["jkm"] > 0:
        bpjs_summary_doc.append("komponen", {
            "component": "BPJS JKM",
            "description": "JKM Contribution (Employer)",
            "amount": employer_components["jkm"]
        })
    
    # Add Kesehatan component (employee + employer)
    kesehatan_total = employee_components["kesehatan_employee"] + employer_components["kesehatan_employer"]
    if kesehatan_total > 0:
        bpjs_summary_doc.append("komponen", {
            "component": "BPJS Kesehatan",
            "description": "Kesehatan Contribution (Employee + Employer)",
            "amount": kesehatan_total
        })

def update_bpjs_payment_summary_components(bpjs_summary_doc):
    """Update BPJS Payment Components based on employee details"""
    # Aggregates for each component
    jht_total = 0
    jp_total = 0
    jkk_total = 0
    jkm_total = 0
    kesehatan_total = 0
    
    # Calculate totals from employee_details
    for detail in bpjs_summary_doc.employee_details:
        jht_total += flt(detail.jht_employee) + flt(detail.jht_employer)
        jp_total += flt(detail.jp_employee) + flt(detail.jp_employer)
        jkk_total += flt(detail.jkk)
        jkm_total += flt(detail.jkm)
        kesehatan_total += flt(detail.kesehatan_employee) + flt(detail.kesehatan_employer)
    
    # Clear existing components
    bpjs_summary_doc.komponen = []
    
    # Create new components with updated totals
    if jht_total > 0:
        bpjs_summary_doc.append("komponen", {
            "component": "BPJS JHT",
            "description": "JHT Contribution (Employee + Employer)",
            "amount": jht_total
        })
    
    if jp_total > 0:
        bpjs_summary_doc.append("komponen", {
            "component": "BPJS JP",
            "description": "JP Contribution (Employee + Employer)",
            "amount": jp_total
        })
    
    if jkk_total > 0:
        bpjs_summary_doc.append("komponen", {
            "component": "BPJS JKK",
            "description": "JKK Contribution (Employer)",
            "amount": jkk_total
        })
    
    if jkm_total > 0:
        bpjs_summary_doc.append("komponen", {
            "component": "BPJS JKM",
            "description": "JKM Contribution (Employer)",
            "amount": jkm_total
        })
    
    if kesehatan_total > 0:
        bpjs_summary_doc.append("komponen", {
            "component": "BPJS Kesehatan",
            "description": "Kesehatan Contribution (Employee + Employer)",
            "amount": kesehatan_total
        })

def create_bpjs_payment_component(doc, bpjs_summary_doc=None):
    """
    Create BPJS Payment Component based on salary slip
    
    Args:
        doc: The salary slip document
        bpjs_summary_doc: Optional BPJS Payment Summary document
                          If not provided, will try to find it
    """
    try:
        # Check if BPJS Payment Component DocType exists
        if not frappe.db.exists("DocType", "BPJS Payment Component"):
            frappe.msgprint(_("BPJS Payment Component DocType not found. Cannot create component."))
            return
        
        # Get the employee BPJS component data
        bpjs_employee_components = get_bpjs_employee_components(doc)
        
        # Skip if no BPJS components found in salary slip
        if sum(bpjs_employee_components.values()) <= 0:
            return
        
        # Get employer components from BPJS settings
        bpjs_employer_components = calculate_bpjs_employer_components(doc)
            
        # Find or get BPJS Payment Summary if not provided
        if not bpjs_summary_doc:
            month = getdate(doc.end_date).month
            year = getdate(doc.end_date).year
            
            bpjs_summary = find_existing_bpjs_summary(doc, year, month)
            
            if not bpjs_summary:
                frappe.msgprint(_("No BPJS Payment Summary found for {0}-{1}. Creating new summary.").format(month, year))
                # Create new BPJS Payment Summary
                create_new_bpjs_summary(doc, year, month, bpjs_employee_components, bpjs_employer_components)
                bpjs_summary = find_existing_bpjs_summary(doc, year, month)
                
            if not bpjs_summary:
                frappe.msgprint(_("Failed to create BPJS Payment Summary for {0}-{1}").format(month, year))
                return
                
            bpjs_summary_doc = frappe.get_doc("BPJS Payment Summary", bpjs_summary)
        
        # Check if BPJS Payment Component already exists for this employee and salary slip
        existing_component = find_existing_bpjs_payment_component(doc, bpjs_summary_doc.name)
        
        if existing_component:
            # Update existing BPJS Payment Component
            return update_bpjs_payment_component(existing_component, doc, bpjs_summary_doc, 
                                             bpjs_employee_components, bpjs_employer_components)
        else:
            # Create new BPJS Payment Component
            return create_new_bpjs_payment_component(doc, bpjs_summary_doc, 
                                                  bpjs_employee_components, bpjs_employer_components)
        
    except Exception as e:
        frappe.log_error(
            f"Error creating BPJS Payment Component for {doc.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Component Creation Error"
        )
        frappe.msgprint(_("Error creating BPJS Payment Component: {0}").format(str(e)))
        return None

def find_existing_bpjs_payment_component(salary_slip, bpjs_summary_name):
    """Find existing BPJS Payment Component for this employee and salary slip"""
    try:
        return frappe.db.get_value(
            "BPJS Payment Component", 
            {
                "employee": salary_slip.employee, 
                "salary_slip": salary_slip.name,
                "bpjs_payment_summary": bpjs_summary_name,
                "docstatus": ["!=", 2]
            },
            "name"
        )
    except Exception as e:
        if "Unknown column" in str(e):
            frappe.log_error(
                f"Database structure issue: {str(e)}\nPlease run 'bench migrate' "
                f"or fix the BPJS Payment Component DocType structure.",
                "BPJS Component Query Error"
            )
        else:
            frappe.log_error(
                f"Error querying BPJS Payment Component: {str(e)}",
                "BPJS Component Query Error"
            )
        return None

def create_new_bpjs_payment_component(salary_slip, bpjs_summary_doc, employee_components, employer_components):
    """Create a new BPJS Payment Component"""
    try:
        # Create BPJS Payment Component
        bpjs_component = frappe.new_doc("BPJS Payment Component")
        
        # Set document fields
        bpjs_component.employee = salary_slip.employee
        bpjs_component.employee_name = salary_slip.employee_name
        bpjs_component.salary_slip = salary_slip.name
        bpjs_component.bpjs_payment_summary = bpjs_summary_doc.name
        bpjs_component.posting_date = getdate()
        
        # Add employee components
        bpjs_component.jht_employee = employee_components["jht_employee"]
        bpjs_component.jp_employee = employee_components["jp_employee"]
        bpjs_component.kesehatan_employee = employee_components["kesehatan_employee"]
        
        # Add employer components
        bpjs_component.jht_employer = employer_components["jht_employer"]
        bpjs_component.jp_employer = employer_components["jp_employer"]
        bpjs_component.jkk = employer_components["jkk"]
        bpjs_component.jkm = employer_components["jkm"]
        bpjs_component.kesehatan_employer = employer_components["kesehatan_employer"]
        
        # Calculate totals
        bpjs_component.total_employee = (
            bpjs_component.jht_employee + 
            bpjs_component.jp_employee + 
            bpjs_component.kesehatan_employee
        )
        
        bpjs_component.total_employer = (
            bpjs_component.jht_employer + 
            bpjs_component.jp_employer + 
            bpjs_component.kesehatan_employer +
            bpjs_component.jkk +
            bpjs_component.jkm
        )
        
        bpjs_component.grand_total = bpjs_component.total_employee + bpjs_component.total_employer
        
        # Add BPJS components for detailed tracking (if the field exists)
        if hasattr(bpjs_component, 'bpjs_components'):
            # Add JHT Employee component
            if employee_components["jht_employee"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JHT", 
                    "description": "JHT Employee Contribution",
                    "amount": employee_components["jht_employee"]
                })
                
            # Add JP Employee component
            if employee_components["jp_employee"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JP",
                    "description": "JP Employee Contribution",
                    "amount": employee_components["jp_employee"]
                })
                
            # Add Kesehatan Employee component
            if employee_components["kesehatan_employee"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS Kesehatan",
                    "description": "Kesehatan Employee Contribution",
                    "amount": employee_components["kesehatan_employee"]
                })
                
            # Add JHT Employer component
            if employer_components["jht_employer"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JHT",
                    "description": "JHT Employer Contribution",
                    "amount": employer_components["jht_employer"]
                })
                
            # Add JP Employer component
            if employer_components["jp_employer"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JP",
                    "description": "JP Employer Contribution",
                    "amount": employer_components["jp_employer"]
                })
                
            # Add JKK component
            if employer_components["jkk"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JKK",
                    "description": "JKK Employer Contribution",
                    "amount": employer_components["jkk"]
                })
                
            # Add JKM component
            if employer_components["jkm"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JKM",
                    "description": "JKM Employer Contribution",
                    "amount": employer_components["jkm"]
                })
                
            # Add Kesehatan Employer component
            if employer_components["kesehatan_employer"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS Kesehatan",
                    "description": "Kesehatan Employer Contribution",
                    "amount": employer_components["kesehatan_employer"]
                })
        
        # Save the document
        bpjs_component.insert(ignore_permissions=True)
        frappe.msgprint(_("Created BPJS Payment Component {0}").format(bpjs_component.name))
        
        return bpjs_component.name
        
    except Exception as e:
        frappe.log_error(
            f"Error creating BPJS Payment Component for {salary_slip.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Component Creation Error"
        )
        frappe.msgprint(_("Error creating BPJS Payment Component: {0}").format(str(e)))
        return None

def update_bpjs_payment_component(component_name, salary_slip, bpjs_summary_doc, employee_components, employer_components):
    """Update an existing BPJS Payment Component"""
    try:
        # Get the BPJS Payment Component document
        bpjs_component = frappe.get_doc("BPJS Payment Component", component_name)
        
        # Update the fields
        bpjs_component.employee_name = salary_slip.employee_name  # In case employee name changed
        bpjs_component.posting_date = getdate()
        
        # Update employee components
        bpjs_component.jht_employee = employee_components["jht_employee"]
        bpjs_component.jp_employee = employee_components["jp_employee"]
        bpjs_component.kesehatan_employee = employee_components["kesehatan_employee"]
        
        # Update employer components
        bpjs_component.jht_employer = employer_components["jht_employer"]
        bpjs_component.jp_employer = employer_components["jp_employer"]
        bpjs_component.jkk = employer_components["jkk"]
        bpjs_component.jkm = employer_components["jkm"]
        bpjs_component.kesehatan_employer = employer_components["kesehatan_employer"]
        
        # Recalculate totals
        bpjs_component.total_employee = (
            bpjs_component.jht_employee + 
            bpjs_component.jp_employee + 
            bpjs_component.kesehatan_employee
        )
        
        bpjs_component.total_employer = (
            bpjs_component.jht_employer + 
            bpjs_component.jp_employer + 
            bpjs_component.kesehatan_employer +
            bpjs_component.jkk +
            bpjs_component.jkm
        )
        
        bpjs_component.grand_total = bpjs_component.total_employee + bpjs_component.total_employer
        
        # Update BPJS components for detailed tracking (if the field exists)
        if hasattr(bpjs_component, 'bpjs_components'):
            # Clear existing components if any
            bpjs_component.set('bpjs_components', [])
            
            # Add JHT Employee component
            if employee_components["jht_employee"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JHT", 
                    "description": "JHT Employee Contribution",
                    "amount": employee_components["jht_employee"]
                })
                
            # Add JP Employee component
            if employee_components["jp_employee"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JP",
                    "description": "JP Employee Contribution",
                    "amount": employee_components["jp_employee"]
                })
                
            # Add Kesehatan Employee component
            if employee_components["kesehatan_employee"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS Kesehatan",
                    "description": "Kesehatan Employee Contribution",
                    "amount": employee_components["kesehatan_employee"]
                })
                
            # Add JHT Employer component
            if employer_components["jht_employer"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JHT",
                    "description": "JHT Employer Contribution",
                    "amount": employer_components["jht_employer"]
                })
                
            # Add JP Employer component
            if employer_components["jp_employer"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JP",
                    "description": "JP Employer Contribution",
                    "amount": employer_components["jp_employer"]
                })
                
            # Add JKK component
            if employer_components["jkk"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JKK",
                    "description": "JKK Employer Contribution",
                    "amount": employer_components["jkk"]
                })
                
            # Add JKM component
            if employer_components["jkm"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JKM",
                    "description": "JKM Employer Contribution",
                    "amount": employer_components["jkm"]
                })
                
            # Add Kesehatan Employer component
            if employer_components["kesehatan_employer"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS Kesehatan",
                    "description": "Kesehatan Employer Contribution",
                    "amount": employer_components["kesehatan_employer"]
                })
        
        # Save the document
        bpjs_component.save(ignore_permissions=True)
        frappe.msgprint(_("Updated BPJS Payment Component {0}").format(bpjs_component.name))
        
        return bpjs_component.name
        
    except Exception as e:
        frappe.log_error(
            f"Error updating BPJS Payment Component {component_name} for {salary_slip.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Component Update Error"
        )
        frappe.msgprint(_("Error updating BPJS Payment Component: {0}").format(str(e)))
        return None