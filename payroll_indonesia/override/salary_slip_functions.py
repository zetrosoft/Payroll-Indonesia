# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 02:17:34 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate, cint

def validate_salary_slip(doc, method=None):
    """Additional validation for salary slip with improved error handling"""
    try:
        # Validate employee is specified
        if not doc.employee:
            frappe.throw(_("Employee is mandatory for Salary Slip"))
        
        # Initialize custom fields
        initialize_custom_fields(doc)
        
        # Validate required DocTypes and settings exist
        validate_dependent_doctypes()
        
        # Check if all required components exist in salary slip
        validate_required_components(doc)
        
    except Exception as e:
        frappe.log_error(
            f"Salary Slip Validation Error for {doc.name if hasattr(doc, 'name') else 'New Salary Slip'}: {str(e)}",
            "Salary Slip Validation Error"
        )
        frappe.throw(_("Error validating salary slip: {0}").format(str(e)))

def validate_dependent_doctypes():
    """Check if all dependent DocTypes and settings exist"""
    try:
        # Check BPJS Settings
        if not frappe.db.exists("DocType", "BPJS Settings"):
            frappe.throw(_("BPJS Settings DocType not found. Please make sure Payroll Indonesia is properly installed."))
            
        # Check if BPJS Settings document exists
        if not frappe.db.exists("BPJS Settings", "BPJS Settings"):
            frappe.throw(_("BPJS Settings document not configured. Please create BPJS Settings first."))
            
        # Check PPh 21 Settings
        if not frappe.db.exists("DocType", "PPh 21 Settings"):
            frappe.throw(_("PPh 21 Settings DocType not found. Please make sure Payroll Indonesia is properly installed."))
            
        # Check if PPh 21 Settings document exists
        if not frappe.db.exists("PPh 21 Settings", "PPh 21 Settings"):
            frappe.throw(_("PPh 21 Settings document not configured. Please create PPh 21 Settings first."))
            
        # Check required dependent DocTypes
        required_doctypes = [
            "Employee Tax Summary",
            "BPJS Payment Summary",
            "PPh TER Table"
        ]
        
        for doctype in required_doctypes:
            if not frappe.db.exists("DocType", doctype):
                frappe.throw(_("{0} DocType not found. Please make sure Payroll Indonesia is properly installed.").format(doctype))
                
    except Exception as e:
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
        frappe.log_error(
            f"Error validating dependent DocTypes: {str(e)}",
            "Dependent DocType Validation Error"
        )
        frappe.throw(_("Error validating dependent DocTypes: {0}").format(str(e)))

def validate_required_components(doc):
    """Check if all required components exist in the salary slip"""
    try:
        required_components = {
            "earnings": ["Gaji Pokok"],
            "deductions": [
                "BPJS JHT Employee",
                "BPJS JP Employee", 
                "BPJS Kesehatan Employee",
                "PPh 21"
            ]
        }
        
        # First check if all required components exist in the system
        missing_components = []
        for component_type, components in required_components.items():
            for component in components:
                if not frappe.db.exists("Salary Component", component):
                    missing_components.append(component)
                    
        if missing_components:
            frappe.throw(_("Required salary components not found in the system: {0}").format(
                ", ".join(missing_components)
            ))
        
        # Then check if all required components are in the salary slip
        for component_type, components in required_components.items():
            if not hasattr(doc, component_type) or not getattr(doc, component_type):
                frappe.throw(_("Salary slip doesn't have {0}").format(component_type))
                
            components_in_slip = [d.salary_component for d in getattr(doc, component_type)]
            for component in components:
                if component not in components_in_slip:
                    # Add the missing component
                    try:
                        # Get abbr from component
                        component_doc = frappe.get_doc("Salary Component", component)
                        
                        # Create a new row
                        doc.append(component_type, {
                            "salary_component": component,
                            "abbr": component_doc.salary_component_abbr,
                            "amount": 0
                        })
                        
                        frappe.msgprint(_("Added missing component: {0}").format(component))
                    except Exception as e:
                        frappe.log_error(
                            f"Error adding component {component}: {str(e)}",
                            "Component Addition Error"
                        )
                        frappe.throw(_("Error adding component {0}: {1}").format(component, str(e)))
                        
    except Exception as e:
        frappe.log_error(
            f"Error validating required components: {str(e)}",
            "Component Validation Error"
        )
        frappe.throw(_("Error validating required salary components: {0}").format(str(e)))

def on_submit_salary_slip(doc, method=None):
    """Actions after salary slip is submitted"""
    try:
        # Update employee YTD tax paid
        update_employee_ytd_tax(doc)
        
        # Log payroll event
        log_payroll_event(doc)
        
        # Update BPJS Payment Summary
        update_bpjs_payment_summary(doc)
        
        # Update PPh TER Table if using TER
        if getattr(doc, 'is_using_ter', 0):
            update_pph_ter_table(doc)
            
    except Exception as e:
        frappe.log_error(
            f"Error in on_submit_salary_slip for {doc.name}: {str(e)}",
            "Salary Slip Submit Error"
        )
        frappe.throw(_("Error processing salary slip submission: {0}").format(str(e)))

def update_employee_ytd_tax(doc):
    """Update employee's year-to-date tax information with improved validation"""
    try:
        # Validate the required parameters
        if not doc.employee:
            frappe.throw(_("Employee is required for updating tax information"))
            
        if not hasattr(doc, 'end_date') or not doc.end_date:
            frappe.throw(_("Salary slip end date is required for updating tax information"))
            
        # Get the current year and month
        end_date = getdate(doc.end_date)
        year = end_date.year
        month = end_date.month
        
        # Get the PPh 21 amount
        pph21_amount = 0
        for deduction in doc.deductions:
            if deduction.salary_component == "PPh 21":
                pph21_amount = flt(deduction.amount)
                break
        
        # Get BPJS components from salary slip
        bpjs_deductions = 0
        for deduction in doc.deductions:
            if deduction.salary_component in ["BPJS JHT Employee", "BPJS JP Employee", "BPJS Kesehatan Employee"]:
                bpjs_deductions += flt(deduction.amount)
        
        # Validate Employee Tax Summary DocType exists
        if not frappe.db.exists("DocType", "Employee Tax Summary"):
            frappe.throw(_("Employee Tax Summary DocType not found. Cannot update tax information."))
        
        # Check if we already have a record for this employee/year combination
        existing_tax_summary = frappe.db.get_value(
            "Employee Tax Summary", 
            {"employee": doc.employee, "year": year},
            "name"
        )
        
        if existing_tax_summary:
            try:
                # Get existing record and update it
                tax_record = frappe.get_doc("Employee Tax Summary", existing_tax_summary)
                
                # Validate that the required fields exist in the tax record
                if not hasattr(tax_record, 'monthly_details'):
                    frappe.throw(_("Employee Tax Summary structure is invalid: missing monthly_details child table"))
                
                if not hasattr(tax_record, 'ytd_tax'):
                    frappe.throw(_("Employee Tax Summary structure is invalid: missing ytd_tax field"))
                
                # Append monthly detail
                has_month = False
                for m in tax_record.monthly_details:
                    if hasattr(m, 'month') and m.month == month:
                        # Update existing month
                        m.gross_pay = doc.gross_pay
                        m.bpjs_deductions = bpjs_deductions
                        m.tax_amount = pph21_amount
                        m.salary_slip = doc.name
                        
                        # Set TER information if applicable
                        if hasattr(m, 'is_using_ter'):
                            m.is_using_ter = 1 if getattr(doc, 'is_using_ter', 0) else 0
                        else:
                            frappe.msgprint(_("Warning: is_using_ter field missing in Employee Tax Summary monthly details"))
                            
                        if hasattr(m, 'ter_rate'):
                            m.ter_rate = getattr(doc, 'ter_rate', 0)
                        else:
                            frappe.msgprint(_("Warning: ter_rate field missing in Employee Tax Summary monthly details"))
                            
                        has_month = True
                        break
                
                if not has_month:
                    # Create monthly detail dictionary with validation
                    monthly_data = {
                        "month": month,
                        "salary_slip": doc.name,
                        "gross_pay": doc.gross_pay,
                        "bpjs_deductions": bpjs_deductions,
                        "tax_amount": pph21_amount,
                    }
                    
                    # Add TER information if applicable
                    if hasattr(tax_record, 'monthly_details') and tax_record.monthly_details:
                        first_item = tax_record.monthly_details[0]
                        
                        if hasattr(first_item, 'is_using_ter'):
                            monthly_data["is_using_ter"] = 1 if getattr(doc, 'is_using_ter', 0) else 0
                            
                        if hasattr(first_item, 'ter_rate'):
                            monthly_data["ter_rate"] = getattr(doc, 'ter_rate', 0)
                    
                    # Append the monthly detail
                    tax_record.append("monthly_details", monthly_data)
                
                # Recalculate YTD tax with validation
                total_tax = 0
                if tax_record.monthly_details:
                    for m in tax_record.monthly_details:
                        if hasattr(m, 'tax_amount'):
                            total_tax += flt(m.tax_amount)
                
                tax_record.ytd_tax = total_tax
                
                # Set title if empty
                if not hasattr(tax_record, 'title') or not tax_record.title:
                    tax_record.title = f"{doc.employee_name} - {year}"
                    
                # Set TER information at year level if applicable
                is_using_ter = getattr(doc, 'is_using_ter', 0)
                if is_using_ter:
                    if hasattr(tax_record, 'is_using_ter'):
                        tax_record.is_using_ter = 1
                    
                    if hasattr(tax_record, 'ter_rate'):
                        tax_record.ter_rate = getattr(doc, 'ter_rate', 0)
                    
                # Save the changes
                tax_record.flags.ignore_validate_update_after_submit = True
                tax_record.save(ignore_permissions=True)
                
                # Remove individual commits from functions to prevent transaction issues
                # frappe.db.commit() - removed to allow proper transaction handling
                
            except Exception as e:
                frappe.log_error(
                    f"Error updating existing Tax Summary for {doc.employee}: {str(e)}",
                    "Employee Tax Summary Error"
                )
                raise
                
        else:
            try:
                # Create a new Employee Tax Summary
                tax_record = frappe.new_doc("Employee Tax Summary")
                
                # Set required fields
                tax_record.employee = doc.employee
                tax_record.employee_name = doc.employee_name
                tax_record.year = year
                tax_record.ytd_tax = pph21_amount
                
                if hasattr(tax_record, 'title'):
                    tax_record.title = f"{doc.employee_name} - {year}"
                
                # Set TER information at year level if applicable
                is_using_ter = getattr(doc, 'is_using_ter', 0)
                if is_using_ter:
                    if hasattr(tax_record, 'is_using_ter'):
                        tax_record.is_using_ter = 1
                    
                    if hasattr(tax_record, 'ter_rate'):
                        tax_record.ter_rate = getattr(doc, 'ter_rate', 0)
                
                # Create monthly details dictionary
                monthly_data = {
                    "month": month,
                    "salary_slip": doc.name,
                    "gross_pay": doc.gross_pay,
                    "bpjs_deductions": bpjs_deductions,
                    "tax_amount": pph21_amount,
                }
                
                # Add TER information if monthly_details has these fields
                try:
                    # Create a temporary childtable item to check field existence
                    temp_monthly = frappe.new_doc("Employee Tax Summary Detail")
                    
                    if hasattr(temp_monthly, 'is_using_ter'):
                        monthly_data["is_using_ter"] = 1 if is_using_ter else 0
                        
                    if hasattr(temp_monthly, 'ter_rate'):
                        monthly_data["ter_rate"] = getattr(doc, 'ter_rate', 0)
                except Exception:
                    # If we can't check fields, just try to add them
                    monthly_data["is_using_ter"] = 1 if is_using_ter else 0
                    monthly_data["ter_rate"] = getattr(doc, 'ter_rate', 0)
                
                # Add first monthly detail
                if hasattr(tax_record, 'monthly_details'):
                    tax_record.append("monthly_details", monthly_data)
                else:
                    frappe.throw(_("Employee Tax Summary structure is invalid: missing monthly_details child table"))
                
                # Insert the document
                tax_record.insert(ignore_permissions=True)
                
                # Remove individual commits from functions to prevent transaction issues
                # frappe.db.commit() - removed to allow proper transaction handling
                
            except Exception as e:
                frappe.log_error(
                    f"Error creating Tax Summary for {doc.employee}: {str(e)}",
                    "Employee Tax Summary Error"
                )
                raise
                
    except Exception as e:
        frappe.log_error(
            f"Error updating YTD tax for {doc.employee if hasattr(doc, 'employee') else 'unknown employee'}: {str(e)}",
            "Employee Tax Summary Error"
        )
        frappe.throw(_("Error updating employee tax information: {0}").format(str(e)))

def log_payroll_event(doc):
    """Log payroll processing event with error handling"""
    try:
        # Validate that Payroll Log DocType exists
        if not frappe.db.exists("DocType", "Payroll Log"):
            frappe.msgprint(_("Payroll Log DocType not found. Skipping payroll event logging."))
            return
        
        # Validate required fields
        if not doc.employee or not doc.employee_name:
            frappe.msgprint(_("Employee details missing. Skipping payroll event logging."))
            return
            
        if not doc.name:
            frappe.msgprint(_("Salary slip name missing. Skipping payroll event logging."))
            return
            
        # Record the payroll processing event
        log = frappe.new_doc("Payroll Log")
        
        # Set required fields
        log.employee = doc.employee
        log.employee_name = doc.employee_name
        log.salary_slip = doc.name
        log.posting_date = getattr(doc, 'posting_date', getdate())
        
        # Set dates if available
        if hasattr(doc, 'start_date') and doc.start_date:
            log.start_date = doc.start_date
            
        if hasattr(doc, 'end_date') and doc.end_date:
            log.end_date = doc.end_date
            
        # Set pay details
        log.gross_pay = getattr(doc, 'gross_pay', 0)
        log.net_pay = getattr(doc, 'net_pay', 0)
        log.total_deduction = getattr(doc, 'total_deduction', 0)
        
        # Add TER information if applicable
        is_using_ter = getattr(doc, 'is_using_ter', 0)
        
        # Check if Payroll Log has these fields
        if hasattr(log, 'calculation_method'):
            log.calculation_method = "TER" if is_using_ter else "Progressive"
        
        if is_using_ter and hasattr(log, 'ter_rate'):
            log.ter_rate = getattr(doc, 'ter_rate', 0)
            
        # Add correction information if December
        end_date = getdate(doc.end_date) if hasattr(doc, 'end_date') else None
        koreksi_pph21 = getattr(doc, 'koreksi_pph21', 0)
        
        if end_date and end_date.month == 12 and koreksi_pph21 != 0:
            if hasattr(log, 'has_correction'):
                log.has_correction = 1
                
            if hasattr(log, 'correction_amount'):
                log.correction_amount = koreksi_pph21
            
        # Set status and notes
        log.status = "Success"
        
        if hasattr(doc, 'payroll_note'):
            payroll_note = doc.payroll_note
            # Limit note length if needed
            if hasattr(log, 'notes'):
                log.notes = payroll_note[:500] if payroll_note else ""
        
        # Insert the log
        log.insert(ignore_permissions=True)
        
        # Remove individual commits from functions to prevent transaction issues
        # frappe.db.commit() - removed to allow proper transaction handling
        
    except Exception as e:
        frappe.log_error(
            f"Error logging payroll event for {doc.employee if hasattr(doc, 'employee') else 'unknown employee'}: {str(e)}",
            "Payroll Log Error"
        )
        # Don't throw here, just log the error - this is a non-critical function
        frappe.msgprint(_("Warning: Could not create payroll log: {0}").format(str(e)))

def update_bpjs_payment_summary(doc):
    """Update BPJS Payment Summary based on submitted salary slip with improved validation"""
    try:
        # Check if BPJS Payment Summary DocType exists
        if not frappe.db.exists("DocType", "BPJS Payment Summary"):
            frappe.throw(_("BPJS Payment Summary DocType not found. Cannot update BPJS information."))
            
        # Validate required data
        if not doc.employee or not doc.employee_name:
            frappe.throw(_("Employee details missing. Cannot update BPJS summary."))
        
        if not hasattr(doc, 'end_date') or not doc.end_date:
            frappe.throw(_("Salary slip end date missing. Cannot update BPJS summary."))
            
        if not doc.company:
            frappe.throw(_("Company is required for BPJS Payment Summary."))
            
        # Determine year and month from salary slip
        end_date = getdate(doc.end_date)
        month = end_date.month
        year = end_date.year
        
        # Get BPJS components from salary slip
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
        
        # Get BPJS Settings with validation
        try:
            bpjs_settings = frappe.get_single("BPJS Settings")
            
            # Validate required settings
            required_settings = [
                'jht_employer_percent', 'jp_max_salary', 'jp_employer_percent',
                'jkk_percent', 'jkm_percent', 'kesehatan_max_salary',
                'kesehatan_employer_percent'
            ]
            
            for setting in required_settings:
                if not hasattr(bpjs_settings, setting):
                    frappe.throw(_("BPJS Settings missing required field: {0}").format(setting))
            
        except Exception as e:
            frappe.throw(_("Error retrieving BPJS Settings: {0}").format(str(e)))
        
        # Calculate employer components with validation
        gross_pay = getattr(doc, 'gross_pay', 0)
        
        # JHT Employer (typically 3.7%)
        jht_employer_percent = getattr(bpjs_settings, 'jht_employer_percent', 0)
        jht_employer = gross_pay * (jht_employer_percent / 100)
        
        # JP Employer (typically 2%)
        jp_max_salary = getattr(bpjs_settings, 'jp_max_salary', 0)
        jp_employer_percent = getattr(bpjs_settings, 'jp_employer_percent', 0)
        jp_salary = min(gross_pay, jp_max_salary)
        jp_employer = jp_salary * (jp_employer_percent / 100)
        
        # JKK (typically 0.24% - 1.74% depending on risk)
        jkk_percent = getattr(bpjs_settings, 'jkk_percent', 0)
        jkk = gross_pay * (jkk_percent / 100)
        
        # JKM (typically 0.3%)
        jkm_percent = getattr(bpjs_settings, 'jkm_percent', 0)
        jkm = gross_pay * (jkm_percent / 100)
        
        # Kesehatan Employer (typically 4%)
        kesehatan_max_salary = getattr(bpjs_settings, 'kesehatan_max_salary', 0)
        kesehatan_employer_percent = getattr(bpjs_settings, 'kesehatan_employer_percent', 0)
        kesehatan_salary = min(gross_pay, kesehatan_max_salary)
        kesehatan_employer = kesehatan_salary * (kesehatan_employer_percent / 100)
        
        # Check if BPJS Payment Summary exists for this period
        try:
            bpjs_summary = frappe.db.get_value(
                "BPJS Payment Summary",
                {"company": doc.company, "year": year, "month": month, "docstatus": ["!=", 2]},
                "name"
            )
        except Exception as e:
            frappe.throw(_("Error querying BPJS Payment Summary: {0}").format(str(e)))
        
        # Calculate total amount of all BPJS contributions
        total_amount = (
            flt(bpjs_data["jht_employee"]) + jht_employer +
            flt(bpjs_data["jp_employee"]) + jp_employer +
            flt(bpjs_data["kesehatan_employee"]) + kesehatan_employer +
            jkk + jkm
        )
        
        if not bpjs_summary:
            try:
                # Create new BPJS Payment Summary
                bpjs_summary_doc = frappe.new_doc("BPJS Payment Summary")
                
                # Set header fields
                bpjs_summary_doc.company = doc.company
                bpjs_summary_doc.year = year
                bpjs_summary_doc.month = month
                
                # Set mandatory fields that were missing
                bpjs_summary_doc.posting_date = doc.posting_date or getdate()  # Use salary slip posting date or today
                bpjs_summary_doc.amount = total_amount  # Set calculated total as amount
                
                # Set title field if it exists
                if hasattr(bpjs_summary_doc, 'month_year_title'):
                    bpjs_summary_doc.month_year_title = f"{month:02d}-{year}"
                
                # Validate employee_details child table exists
                if not hasattr(bpjs_summary_doc, 'employee_details'):
                    frappe.throw(_("BPJS Payment Summary structure is invalid: missing employee_details child table"))
                
                # Create employee detail
                employee_data = {
                    "employee": doc.employee,
                    "employee_name": doc.employee_name,
                    "salary_slip": doc.name,
                    "jht_employee": bpjs_data["jht_employee"],
                    "jp_employee": bpjs_data["jp_employee"],
                    "kesehatan_employee": bpjs_data["kesehatan_employee"],
                    "jht_employer": jht_employer,
                    "jp_employer": jp_employer,
                    "jkk": jkk,
                    "jkm": jkm,
                    "kesehatan_employer": kesehatan_employer
                }
                
                # Add employee detail
                bpjs_summary_doc.append("employee_details", employee_data)
                
                # Insert the document
                bpjs_summary_doc.insert(ignore_permissions=True)
                
                # Remove individual commits from functions to prevent transaction issues
                # frappe.db.commit() - removed to allow proper transaction handling
                
            except Exception as e:
                frappe.log_error(
                    f"Error creating BPJS Payment Summary for {doc.employee}: {str(e)}",
                    "BPJS Summary Error"
                )
                raise
                
        else:
            try:
                # Update existing BPJS Payment Summary
                bpjs_summary_doc = frappe.get_doc("BPJS Payment Summary", bpjs_summary)
                
                # Check if employee_details exists
                if not hasattr(bpjs_summary_doc, 'employee_details'):
                    frappe.throw(_("BPJS Payment Summary structure is invalid: missing employee_details child table"))
                
                # Check if employee already exists
                employee_exists = False
                for detail in bpjs_summary_doc.employee_details:
                    if detail.employee == doc.employee:
                        # Update existing employee
                        detail.salary_slip = doc.name
                        detail.jht_employee = bpjs_data["jht_employee"]
                        detail.jp_employee = bpjs_data["jp_employee"] 
                        detail.kesehatan_employee = bpjs_data["kesehatan_employee"]
                        detail.jht_employer = jht_employer
                        detail.jp_employer = jp_employer
                        detail.jkk = jkk
                        detail.jkm = jkm
                        detail.kesehatan_employer = kesehatan_employer
                        employee_exists = True
                        break
                
                if not employee_exists:
                    # Add new employee
                    employee_data = {
                        "employee": doc.employee,
                        "employee_name": doc.employee_name,
                        "salary_slip": doc.name,
                        "jht_employee": bpjs_data["jht_employee"],
                        "jp_employee": bpjs_data["jp_employee"],
                        "kesehatan_employee": bpjs_data["kesehatan_employee"],
                        "jht_employer": jht_employer,
                        "jp_employer": jp_employer,
                        "jkk": jkk,
                        "jkm": jkm,
                        "kesehatan_employer": kesehatan_employer
                    }
                    
                    bpjs_summary_doc.append("employee_details", employee_data)
                
                # Update amount field to reflect current total
                # Re-calculate totals considering all employee entries
                updated_amount = 0
                for emp in bpjs_summary_doc.employee_details:
                    updated_amount += (
                        flt(emp.jht_employee) + flt(emp.jht_employer) +
                        flt(emp.jp_employee) + flt(emp.jp_employer) +
                        flt(emp.kesehatan_employee) + flt(emp.kesehatan_employer) +
                        flt(emp.jkk) + flt(emp.jkm)
                    )
                
                bpjs_summary_doc.amount = updated_amount
                
                # Save changes
                bpjs_summary_doc.flags.ignore_validate_update_after_submit = True
                bpjs_summary_doc.save(ignore_permissions=True)
                
                # Remove individual commits from functions to prevent transaction issues
                # frappe.db.commit() - removed to allow proper transaction handling
                
            except Exception as e:
                frappe.log_error(
                    f"Error updating BPJS Payment Summary for {doc.employee}: {str(e)}",
                    "BPJS Summary Error"
                )
                raise
        
    except Exception as e:
        frappe.log_error(
            f"Error updating BPJS Payment Summary for {doc.employee if hasattr(doc, 'employee') else 'unknown employee'}: {str(e)}",
            "BPJS Update Error"
        )
        frappe.throw(_("Error updating BPJS Payment Summary: {0}").format(str(e)))
        
def update_pph_ter_table(doc):
    """Update PPh TER Table based on submitted salary slip with improved validation"""
    try:
        # Only proceed if using TER
        is_using_ter = getattr(doc, 'is_using_ter', 0)
        if not is_using_ter:
            return
        
        # Check if PPh TER Table DocType exists
        if not frappe.db.exists("DocType", "PPh TER Table"):
            frappe.throw(_("PPh TER Table DocType not found. Cannot update TER information."))
            
        # Validate required data
        if not doc.employee or not doc.employee_name:
            frappe.throw(_("Employee details missing. Cannot update PPh TER Table."))
        
        if not hasattr(doc, 'end_date') or not doc.end_date:
            frappe.throw(_("Salary slip end date missing. Cannot update PPh TER Table."))
            
        if not doc.company:
            frappe.throw(_("Company is required for PPh TER Table."))
            
        # Determine year and month from salary slip
        end_date = getdate(doc.end_date)
        month = end_date.month
        year = end_date.year
        
        # Get PPh 21 amount
        pph21_amount = 0
        for deduction in doc.deductions:
            if deduction.salary_component == "PPh 21":
                pph21_amount = flt(deduction.amount)
                break
        
        # Get employee status pajak with validation
        try:
            employee = frappe.get_doc("Employee", doc.employee)
            status_pajak = getattr(employee, 'status_pajak', 'TK0')
            if not status_pajak:
                status_pajak = 'TK0'
                frappe.msgprint(_("Tax status not set for employee {0}, using default (TK0)").format(doc.employee))
        except Exception as e:
            frappe.log_error(
                f"Error getting employee tax status for {doc.employee}: {str(e)}",
                "Employee Status Error"
            )
            status_pajak = 'TK0'
            frappe.msgprint(_("Error retrieving employee tax status: {0}, using default (TK0)").format(str(e)))
        
        # Check if PPh TER Table exists for this period
        try:
            ter_table = frappe.db.get_value(
                "PPh TER Table", 
                {"company": doc.company, "year": year, "month": month, "docstatus": ["!=", 2]},
                "name"
            )
        except Exception as e:
            frappe.throw(_("Error querying PPh TER Table: {0}").format(str(e)))
        
        if not ter_table:
            try:
                # Create new PPh TER Table
                ter_table_doc = frappe.new_doc("PPh TER Table")
                
                # Set header fields
                ter_table_doc.company = doc.company
                ter_table_doc.year = year
                ter_table_doc.month = month
                
                # Set title field if it exists
                if hasattr(ter_table_doc, 'month_year_title'):
                    ter_table_doc.month_year_title = f"{month:02d}-{year}"
                
                # Validate employee_details child table exists
                if not hasattr(ter_table_doc, 'employee_details'):
                    frappe.throw(_("PPh TER Table structure is invalid: missing employee_details child table"))
                
                # Create employee detail
                employee_data = {
                    "employee": doc.employee,
                    "employee_name": doc.employee_name,
                    "status_pajak": status_pajak,
                    "salary_slip": doc.name,
                    "gross_income": doc.gross_pay,
                    "ter_rate": getattr(doc, 'ter_rate', 0),
                    "pph21_amount": pph21_amount
                }
                
                # Add employee detail
                ter_table_doc.append("employee_details", employee_data)
                
                # Insert the document
                ter_table_doc.insert(ignore_permissions=True)
                
                # Remove individual commits from functions to prevent transaction issues
                # frappe.db.commit() - removed to allow proper transaction handling
                
            except Exception as e:
                frappe.log_error(
                    f"Error creating PPh TER Table for {doc.employee}: {str(e)}",
                    "TER Table Error"
                )
                raise
                
        else:
            try:
                # Update existing PPh TER Table
                ter_table_doc = frappe.get_doc("PPh TER Table", ter_table)
                
                # Check if employee_details exists
                if not hasattr(ter_table_doc, 'employee_details'):
                    frappe.throw(_("PPh TER Table structure is invalid: missing employee_details child table"))
                
                # Check if employee already exists
                employee_exists = False
                for detail in ter_table_doc.employee_details:
                    if detail.employee == doc.employee:
                        # Update existing employee
                        detail.status_pajak = status_pajak
                        detail.salary_slip = doc.name
                        detail.gross_income = doc.gross_pay
                        detail.ter_rate = getattr(doc, 'ter_rate', 0)
                        detail.pph21_amount = pph21_amount
                        employee_exists = True
                        break
                
                if not employee_exists:
                    # Add new employee
                    employee_data = {
                        "employee": doc.employee,
                        "employee_name": doc.employee_name,
                        "status_pajak": status_pajak,
                        "salary_slip": doc.name,
                        "gross_income": doc.gross_pay,
                        "ter_rate": getattr(doc, 'ter_rate', 0),
                        "pph21_amount": pph21_amount
                    }
                    
                    ter_table_doc.append("employee_details", employee_data)
                
                # Save changes
                ter_table_doc.flags.ignore_validate_update_after_submit = True
                ter_table_doc.save(ignore_permissions=True)
                
                # Remove individual commits from functions to prevent transaction issues
                # frappe.db.commit() - removed to allow proper transaction handling
                
            except Exception as e:
                frappe.log_error(
                    f"Error updating PPh TER Table for {doc.employee}: {str(e)}",
                    "TER Table Error"
                )
                raise
        
    except Exception as e:
        frappe.log_error(
            f"Error updating PPh TER Table for {doc.employee if hasattr(doc, 'employee') else 'unknown employee'}: {str(e)}",
            "PPh TER Update Error"
        )
        frappe.throw(_("Error updating PPh TER Table: {0}").format(str(e)))

def after_insert_salary_slip(doc, method=None):
    """
    Hook yang dijalankan setelah Salary Slip dibuat dengan validasi yang lebih baik
    
    Args:
        doc: Object dari Salary Slip yang baru dibuat
        method: Metode yang memanggil hook (tidak digunakan)
    """
    try:
        # Validate required fields
        if not doc.name:
            frappe.msgprint(_("Salary Slip name is missing."))
            return
            
        if not doc.employee:
            frappe.msgprint(_("Employee is missing in Salary Slip."))
            return
            
        # Initialize custom fields
        initialize_custom_fields(doc)
        
        # Log salary slip creation with more information
        try:
            frappe.logger().info(
                f"Salary Slip {doc.name} created for employee {doc.employee} ({doc.employee_name if hasattr(doc, 'employee_name') else 'unnamed'})"
            )
        except Exception:
            # If logger fails, continue anyway
            pass
        
        # Add to payroll notifications if feature is available
        add_to_payroll_notifications(doc)
        
    except Exception as e:
        frappe.log_error(
            f"Error in after_insert_salary_slip for {doc.name if hasattr(doc, 'name') else 'unknown salary slip'}: {str(e)}",
            "Salary Slip Hook Error"
        )
        # Don't throw here to prevent blocking salary slip creation
        frappe.msgprint(_("Warning: Error in post-creation processing: {0}").format(str(e)))

def initialize_custom_fields(doc):
    """Initialize custom fields with better error handling"""
    try:
        # Define all custom fields with their default values
        custom_fields = {
            'is_final_gabung_suami': 0,
            'koreksi_pph21': 0,
            'payroll_note': "",
            'biaya_jabatan': 0,
            'netto': 0,
            'total_bpjs': 0,
            'is_using_ter': 0,
            'ter_rate': 0
        }
        
        # Set default values for all fields
        has_changed = False
        for field, default_value in custom_fields.items():
            if not hasattr(doc, field) or getattr(doc, field) is None:
                setattr(doc, field, default_value)
                has_changed = True
        
        # Update database if needed
        if has_changed and hasattr(doc, 'db_update') and callable(doc.db_update):
            doc.db_update()
            
    except Exception as e:
        frappe.log_error(
            f"Error initializing custom fields for {doc.name if hasattr(doc, 'name') else 'unknown salary slip'}: {str(e)}",
            "Custom Field Initialization Error"
        )
        # Don't throw here to prevent blocking salary slip creation
        frappe.msgprint(_("Warning: Error initializing custom fields: {0}").format(str(e)))

def add_to_payroll_notifications(doc):
    """Add entry to payroll notifications if available with error handling"""
    try:
        # Check if doctype Payroll Notification exists
        if not frappe.db.exists('DocType', 'Payroll Notification'):
            # No need to log or notify, just return
            return
            
        # Validate required fields
        if not doc.employee or not doc.name:
            frappe.msgprint(_("Employee or salary slip name is missing. Skipping notification."))
            return
            
        # Create notification
        notification = frappe.new_doc("Payroll Notification")
        
        # Set required fields
        notification.employee = doc.employee
        notification.employee_name = doc.employee_name if hasattr(doc, 'employee_name') else doc.employee
        notification.salary_slip = doc.name
        notification.posting_date = doc.posting_date if hasattr(doc, 'posting_date') else frappe.utils.today()
        notification.amount = doc.net_pay if hasattr(doc, 'net_pay') else 0
        notification.status = "Draft"
        
        # Insert notification
        notification.insert(ignore_permissions=True)
        
        # Remove individual commits from functions to prevent transaction issues
        # frappe.db.commit() - removed to allow proper transaction handling
        
    except Exception as e:
        frappe.log_error(
            f"Failed to create payroll notification for {doc.name if hasattr(doc, 'name') else 'unknown salary slip'}: {str(e)}",
            "Payroll Notification Error"
        )
        # Don't throw here to prevent blocking salary slip creation
        frappe.msgprint(_("Warning: Could not create payroll notification: {0}").format(str(e)))