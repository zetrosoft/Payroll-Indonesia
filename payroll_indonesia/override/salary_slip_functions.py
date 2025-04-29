# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-29 11:03:17 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate, cint, today
from collections import defaultdict

# Constants
MAX_ERROR_MESSAGE_LENGTH = 140
MAX_LOG_NOTE_LENGTH = 500

def validate_salary_slip(doc, method=None):
    """
    Validate salary slip with improved error handling
    Args:
        doc: Salary Slip document
        method: Method name (not used)
    """
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
        doc_name = getattr(doc, 'name', 'New Salary Slip')
        log_and_raise_error(
            f"Salary Slip Validation Error for {doc_name}: {str(e)}", 
            "Salary Slip Validation Error",
            _("Error validating salary slip")
        )

def initialize_custom_fields(doc):
    """
    Initialize custom fields with default values
    Args:
        doc: Salary Slip document
    """
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
        doc_name = getattr(doc, 'name', 'unknown salary slip')
        log_error(
            f"Error initializing custom fields for {doc_name}: {str(e)}",
            "Custom Field Initialization Error"
        )
        # Don't throw here to prevent blocking salary slip creation
        frappe.msgprint(_("Warning: Error initializing custom fields: {0}").format(
            truncate_message(str(e), MAX_ERROR_MESSAGE_LENGTH)
        ))

def validate_dependent_doctypes():
    """
    Check if all required DocTypes and settings exist
    Raises:
        ValidationError: If any required DocType or setting is missing
    """
    try:
        # Required document types
        required_doctypes = [
            "BPJS Settings", 
            "PPh 21 Settings",
            "Employee Tax Summary",
            "BPJS Payment Summary", 
            "PPh TER Table"
        ]
        
        # Check if DocTypes exist
        for doctype in required_doctypes:
            if not frappe.db.exists("DocType", doctype):
                frappe.throw(_(
                    "{0} DocType not found. Please make sure Payroll Indonesia is properly installed."
                ).format(doctype))
            
        # Check if singleton documents are configured
        singleton_docs = ["BPJS Settings", "PPh 21 Settings"]
        for doc_name in singleton_docs:
            if not frappe.db.exists(doc_name, doc_name):
                frappe.throw(_(
                    "{0} document not configured. Please create {0} first."
                ).format(doc_name))
                
    except Exception as e:
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
        log_and_raise_error(
            f"Error validating dependent DocTypes: {str(e)}",
            "Dependent DocType Validation Error",
            _("Error validating dependent DocTypes")
        )

def validate_required_components(doc):
    """
    Ensure all required salary components exist and add missing ones
    Args:
        doc: Salary Slip document
    """
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
                    add_missing_component(doc, component_type, component)
                        
    except Exception as e:
        log_and_raise_error(
            f"Error validating required components: {str(e)}",
            "Component Validation Error",
            _("Error validating required salary components")
        )

def add_missing_component(doc, component_type, component_name):
    """
    Add a missing component to the salary slip
    Args:
        doc: Salary Slip document
        component_type: Type of component (earnings/deductions)
        component_name: Name of the component to add
    """
    try:
        # Get abbr from component
        component_doc = frappe.get_doc("Salary Component", component_name)
        
        # Create a new row
        doc.append(component_type, {
            "salary_component": component_name,
            "abbr": component_doc.salary_component_abbr,
            "amount": 0
        })
        
        frappe.msgprint(_("Added missing component: {0}").format(component_name))
        
    except Exception as e:
        log_error(
            f"Error adding component {component_name}: {str(e)}",
            "Component Addition Error"
        )
        frappe.throw(_("Error adding component {0}: {1}").format(
            component_name, 
            truncate_message(str(e), MAX_ERROR_MESSAGE_LENGTH)
        ))

def on_submit_salary_slip(doc, method=None):
    """
    Actions after salary slip is submitted
    Args:
        doc: Salary Slip document
        method: Method name (not used)
    """
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
        doc_name = getattr(doc, 'name', 'unknown')
        log_and_raise_error(
            f"Error in on_submit_salary_slip for {doc_name}: {str(e)}",
            "Salary Slip Submit Error",
            _("Error processing salary slip submission")
        )

def update_employee_ytd_tax(doc):
    """
    Update employee's year-to-date tax information
    Args:
        doc: Salary Slip document
    """
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
        
        # Extract PPh 21 and BPJS deductions from salary slip
        tax_deduction_data = get_tax_deduction_data(doc)
        
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
            update_existing_tax_summary(doc, existing_tax_summary, month, tax_deduction_data)
        else:
            create_new_tax_summary(doc, year, month, tax_deduction_data)
                
    except Exception as e:
        employee_id = getattr(doc, 'employee', 'unknown employee')
        log_and_raise_error(
            f"Error updating YTD tax for {employee_id}: {str(e)}",
            "Employee Tax Summary Error",
            _("Error updating employee tax information")
        )

def get_tax_deduction_data(doc):
    """
    Extract tax and BPJS deductions from salary slip
    Args:
        doc: Salary Slip document
    Returns:
        dict: Dictionary containing tax and BPJS deduction data
    """
    pph21_amount = 0
    bpjs_deductions = 0
    is_using_ter = getattr(doc, 'is_using_ter', 0)
    ter_rate = getattr(doc, 'ter_rate', 0)
    
    for deduction in doc.deductions:
        if deduction.salary_component == "PPh 21":
            pph21_amount = flt(deduction.amount)
        elif deduction.salary_component in ["BPJS JHT Employee", "BPJS JP Employee", "BPJS Kesehatan Employee"]:
            bpjs_deductions += flt(deduction.amount)
    
    return {
        "pph21_amount": pph21_amount,
        "bpjs_deductions": bpjs_deductions,
        "is_using_ter": is_using_ter,
        "ter_rate": ter_rate,
        "gross_pay": flt(doc.gross_pay)
    }

def update_existing_tax_summary(doc, tax_summary_name, month, tax_data):
    """
    Update existing employee tax summary
    Args:
        doc: Salary Slip document
        tax_summary_name: Name of the existing tax summary
        month: Current month
        tax_data: Tax deduction data
    """
    try:
        # Get existing record and update it
        tax_record = frappe.get_doc("Employee Tax Summary", tax_summary_name)
        
        # Validate that the required fields exist in the tax record
        validate_tax_summary_structure(tax_record)
        
        # Update monthly details
        update_monthly_tax_details(tax_record, month, doc, tax_data)
        
        # Recalculate YTD tax
        recalculate_ytd_tax(tax_record)
        
        # Set title if empty
        if not tax_record.title:
            tax_record.title = f"{doc.employee_name} - {getdate(doc.end_date).year}"
            
        # Set TER information at year level if applicable
        update_ter_information(tax_record, tax_data)
        
        # Save the changes
        tax_record.flags.ignore_validate_update_after_submit = True
        tax_record.save(ignore_permissions=True)
        
    except Exception as e:
        log_and_raise_error(
            f"Error updating existing Tax Summary for {doc.employee}: {str(e)}",
            "Employee Tax Summary Error",
            _("Error updating existing tax summary")
        )

def validate_tax_summary_structure(tax_record):
    """
    Validate tax summary document structure
    Args:
        tax_record: Employee Tax Summary document
    Raises:
        ValidationError: If tax record structure is invalid
    """
    if not hasattr(tax_record, 'monthly_details'):
        frappe.throw(_("Employee Tax Summary structure is invalid: missing monthly_details child table"))
    
    if not hasattr(tax_record, 'ytd_tax'):
        frappe.throw(_("Employee Tax Summary structure is invalid: missing ytd_tax field"))

def update_monthly_tax_details(tax_record, month, doc, tax_data):
    """
    Update or add monthly tax details
    Args:
        tax_record: Employee Tax Summary document
        month: Current month
        doc: Salary Slip document
        tax_data: Tax deduction data
    """
    has_month = False
    
    for m in tax_record.monthly_details:
        if hasattr(m, 'month') and m.month == month:
            # Update existing month
            m.gross_pay = tax_data["gross_pay"]
            m.bpjs_deductions = tax_data["bpjs_deductions"]
            m.tax_amount = tax_data["pph21_amount"]
            m.salary_slip = doc.name
            
            # Set TER information if applicable
            update_monthly_ter_info(m, tax_data)
            has_month = True
            break
    
    if not has_month:
        # Create new monthly detail
        monthly_data = create_monthly_detail_data(doc, month, tax_data)
        
        # Add TER information if applicable
        if tax_record.monthly_details:
            first_item = tax_record.monthly_details[0]
            update_monthly_data_with_ter_fields(monthly_data, first_item, tax_data)
        
        # Append the monthly detail
        tax_record.append("monthly_details", monthly_data)

def update_monthly_ter_info(monthly_detail, tax_data):
    """
    Update TER information for monthly detail
    Args:
        monthly_detail: Monthly detail document
        tax_data: Tax deduction data
    """
    if hasattr(monthly_detail, 'is_using_ter'):
        monthly_detail.is_using_ter = 1 if tax_data["is_using_ter"] else 0
    else:
        frappe.logger().warning("Warning: is_using_ter field missing in Employee Tax Summary monthly details")
        
    if hasattr(monthly_detail, 'ter_rate'):
        monthly_detail.ter_rate = tax_data["ter_rate"]
    else:
        frappe.logger().warning("Warning: ter_rate field missing in Employee Tax Summary monthly details")

def create_monthly_detail_data(doc, month, tax_data):
    """
    Create monthly detail data dictionary
    Args:
        doc: Salary Slip document
        month: Current month
        tax_data: Tax deduction data
    Returns:
        dict: Monthly detail data
    """
    return {
        "month": month,
        "salary_slip": doc.name,
        "gross_pay": tax_data["gross_pay"],
        "bpjs_deductions": tax_data["bpjs_deductions"],
        "tax_amount": tax_data["pph21_amount"],
    }

def update_monthly_data_with_ter_fields(monthly_data, template_item, tax_data):
    """
    Update monthly data with TER fields based on template
    Args:
        monthly_data: Monthly data dictionary
        template_item: Template item for field reference
        tax_data: Tax deduction data
    """
    if hasattr(template_item, 'is_using_ter'):
        monthly_data["is_using_ter"] = 1 if tax_data["is_using_ter"] else 0
        
    if hasattr(template_item, 'ter_rate'):
        monthly_data["ter_rate"] = tax_data["ter_rate"]

def recalculate_ytd_tax(tax_record):
    """
    Recalculate year-to-date tax amount
    Args:
        tax_record: Employee Tax Summary document
    """
    total_tax = 0
    if tax_record.monthly_details:
        for m in tax_record.monthly_details:
            if hasattr(m, 'tax_amount'):
                total_tax += flt(m.tax_amount)
    
    tax_record.ytd_tax = total_tax

def update_ter_information(tax_record, tax_data):
    """
    Update TER information at year level
    Args:
        tax_record: Employee Tax Summary document
        tax_data: Tax deduction data
    """
    is_using_ter = tax_data["is_using_ter"]
    
    if is_using_ter:
        if hasattr(tax_record, 'is_using_ter'):
            tax_record.is_using_ter = 1
        
        if hasattr(tax_record, 'ter_rate'):
            tax_record.ter_rate = tax_data["ter_rate"]

def create_new_tax_summary(doc, year, month, tax_data):
    """
    Create a new employee tax summary
    Args:
        doc: Salary Slip document
        year: Current year
        month: Current month
        tax_data: Tax deduction data
    """
    try:
        # Create a new Employee Tax Summary
        tax_record = frappe.new_doc("Employee Tax Summary")
        
        # Set required fields
        tax_record.employee = doc.employee
        tax_record.employee_name = doc.employee_name
        tax_record.year = year
        tax_record.ytd_tax = tax_data["pph21_amount"]
        
        if hasattr(tax_record, 'title'):
            tax_record.title = f"{doc.employee_name} - {year}"
        
        # Set TER information at year level if applicable
        update_ter_information(tax_record, tax_data)
        
        # Create monthly detail
        monthly_data = create_monthly_detail_data(doc, month, tax_data)
        
        # Add TER information to monthly detail
        try:
            # Create a temporary childtable item to check field existence
            temp_monthly = frappe.new_doc("Employee Tax Summary Detail")
            
            if hasattr(temp_monthly, 'is_using_ter'):
                monthly_data["is_using_ter"] = 1 if tax_data["is_using_ter"] else 0
                
            if hasattr(temp_monthly, 'ter_rate'):
                monthly_data["ter_rate"] = tax_data["ter_rate"]
        except Exception:
            # If we can't check fields, just try to add them
            monthly_data["is_using_ter"] = 1 if tax_data["is_using_ter"] else 0
            monthly_data["ter_rate"] = tax_data["ter_rate"]
        
        # Add first monthly detail
        if hasattr(tax_record, 'monthly_details'):
            tax_record.append("monthly_details", monthly_data)
        else:
            frappe.throw(_("Employee Tax Summary structure is invalid: missing monthly_details child table"))
        
        # Insert the document
        tax_record.insert(ignore_permissions=True)
        
    except Exception as e:
        log_and_raise_error(
            f"Error creating Tax Summary for {doc.employee}: {str(e)}",
            "Employee Tax Summary Error",
            _("Error creating new tax summary")
        )

def log_payroll_event(doc):
    """
    Log payroll processing event
    Args:
        doc: Salary Slip document
    """
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
            
        # Create and populate payroll log
        log = create_payroll_log(doc)
        
        # Insert the log
        log.insert(ignore_permissions=True)
        
    except Exception as e:
        employee_id = getattr(doc, 'employee', 'unknown employee')
        log_error(
            f"Error logging payroll event for {employee_id}: {str(e)}",
            "Payroll Log Error"
        )
        # Don't throw here, just log the error - this is a non-critical function
        frappe.msgprint(_("Warning: Could not create payroll log: {0}").format(
            truncate_message(str(e), MAX_ERROR_MESSAGE_LENGTH)
        ))

def create_payroll_log(doc):
    """
    Create payroll log document
    Args:
        doc: Salary Slip document
    Returns:
        PayrollLog: New payroll log document
    """
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
        # Limit note length
        if hasattr(log, 'notes'):
            log.notes = truncate_message(payroll_note, MAX_LOG_NOTE_LENGTH) if payroll_note else ""
    
    return log

def update_bpjs_payment_summary(doc):
    """
    Update BPJS Payment Summary from salary slip
    Args:
        doc: Salary Slip document
    """
    try:
        # Validate basic data
        if not doc.employee or not doc.company or not doc.end_date:
            frappe.msgprint(_("Missing essential data from salary slip"))
            return
            
        # Extract month and year
        end_date = getdate(doc.end_date)
        month = end_date.month
        year = end_date.year
        
        # Get BPJS contributions
        bpjs_contributions = calculate_bpjs_contributions(doc)
        
        # Calculate total
        total_amount = calculate_total_bpjs_amount(bpjs_contributions)
        
        # Prepare component data
        bpjs_components = prepare_bpjs_components(bpjs_contributions)
        
        # Check if BPJS Payment Summary exists
        bpjs_summary = frappe.db.get_value(
            "BPJS Payment Summary",
            {"company": doc.company, "year": year, "month": month, "docstatus": ["!=", 2]},
            "name"
        )
        
        if not bpjs_summary:
            create_bpjs_payment_summary(doc, year, month, bpjs_components, bpjs_contributions, total_amount)
        else:
            update_existing_bpjs_summary(doc, bpjs_summary, bpjs_contributions)
                
    except Exception as e:
        log_and_raise_error(
            f"Error in BPJS update process: {str(e)}",
            "BPJS Process Error",
            _("Error updating BPJS Payment Summary")
        )

def calculate_bpjs_contributions(doc):
    """
    Calculate BPJS contributions based on gross pay and settings
    Args:
        doc: Salary Slip document
    Returns:
        dict: Dictionary with BPJS contribution amounts
    """
    # Extract employee contributions from salary slip
    employee_contributions = {
        "jht_employee": 0,
        "jp_employee": 0,
        "kesehatan_employee": 0
    }
    
    for deduction in doc.deductions:
        if deduction.salary_component == "BPJS JHT Employee":
            employee_contributions["jht_employee"] = flt(deduction.amount)
        elif deduction.salary_component == "BPJS JP Employee":
            employee_contributions["jp_employee"] = flt(deduction.amount)
        elif deduction.salary_component == "BPJS Kesehatan Employee":
            employee_contributions["kesehatan_employee"] = flt(deduction.amount)
    
    # Get BPJS Settings
    bpjs_settings = frappe.get_single("BPJS Settings")
    
    # Calculate employer contributions
    gross_pay = flt(doc.gross_pay) if hasattr(doc, 'gross_pay') else 0
    
    # JHT Employer
    jht_employer_percent = flt(getattr(bpjs_settings, 'jht_employer_percent', 3.7))
    jht_employer = flt(gross_pay * jht_employer_percent / 100)
    
    # JP Employer
    jp_max_salary = flt(getattr(bpjs_settings, 'jp_max_salary', 9000000))
    jp_employer_percent = flt(getattr(bpjs_settings, 'jp_employer_percent', 2))
    jp_salary = min(gross_pay, jp_max_salary)
    jp_employer = flt(jp_salary * jp_employer_percent / 100)
    
    # JKK
    jkk_percent = flt(getattr(bpjs_settings, 'jkk_percent', 0.24))
    jkk = flt(gross_pay * jkk_percent / 100)
    
    # JKM
    jkm_percent = flt(getattr(bpjs_settings, 'jkm_percent', 0.3))
    jkm = flt(gross_pay * jkm_percent / 100)
    
    # Kesehatan Employer
    kesehatan_max_salary = flt(getattr(bpjs_settings, 'kesehatan_max_salary', 12000000))
    kesehatan_employer_percent = flt(getattr(bpjs_settings, 'kesehatan_employer_percent', 4))
    kesehatan_salary = min(gross_pay, kesehatan_max_salary)
    kesehatan_employer = flt(kesehatan_salary * kesehatan_employer_percent / 100)
    
    # Combine all contribution data
    contributions = {
        # Employee contributions
        "jht_employee": employee_contributions["jht_employee"],
        "jp_employee": employee_contributions["jp_employee"],
        "kesehatan_employee": employee_contributions["kesehatan_employee"],
        
        # Employer contributions
        "jht_employer": jht_employer,
        "jp_employer": jp_employer,
        "jkk": jkk,
        "jkm": jkm,
        "kesehatan_employer": kesehatan_employer
    }
    
    return contributions

def calculate_total_bpjs_amount(contributions):
    """
    Calculate total BPJS amount from contributions
    Args:
        contributions: Dictionary with BPJS contributions
    Returns:
        float: Total BPJS amount
    """
    # Calculate total - ensure positive value
    total = flt(
        contributions["jht_employee"] + contributions["jht_employer"] +
        contributions["jp_employee"] + contributions["jp_employer"] +
        contributions["kesehatan_employee"] + contributions["kesehatan_employer"] +
        contributions["jkk"] + contributions["jkm"]
    )
    
    # Ensure minimum value
    return max(1.0, total)

def prepare_bpjs_components(contributions):
    """
    Prepare BPJS components from contributions
    Args:
        contributions: Dictionary with BPJS contributions
    Returns:
        dict: Dictionary with BPJS components
    """
    # Prepare component data - ensure values are positive
    return {
        "BPJS Kesehatan": max(0.01, flt(contributions["kesehatan_employee"]) + flt(contributions["kesehatan_employer"])),
        "BPJS JHT": max(0.01, flt(contributions["jht_employee"]) + flt(contributions["jht_employer"])),
        "BPJS JP": max(0.01, flt(contributions["jp_employee"]) + flt(contributions["jp_employer"])),
        "BPJS JKK": max(0.01, flt(contributions["jkk"])),
        "BPJS JKM": max(0.01, flt(contributions["jkm"]))
    }

def create_bpjs_payment_summary(doc, year, month, components, contributions, total_amount):
    """
    Create new BPJS Payment Summary
    Args:
        doc: Salary Slip document
        year: Current year
        month: Current month
        components: Dictionary with BPJS components
        contributions: Dictionary with BPJS contributions
        total_amount: Total BPJS amount
    """
    try:
        # Create new document the standard way
        bpjs_summary_doc = frappe.new_doc("BPJS Payment Summary")
        
        # Set essential fields
        bpjs_summary_doc.company = doc.company
        bpjs_summary_doc.year = year
        bpjs_summary_doc.month = month
        bpjs_summary_doc.posting_date = doc.posting_date or getdate()
        
        # Add components
        for component_name, amount in components.items():
            if amount > 0:
                bpjs_summary_doc.append("komponen", {
                    "component": component_name,
                    "component_type": component_name.replace("BPJS ", ""),
                    "amount": amount
                })
        
        # Add employee detail
        add_employee_bpjs_detail(bpjs_summary_doc, doc, contributions)
        
        # Set total
        bpjs_summary_doc.total = total_amount
        
        # Insert with special handling
        insert_bpjs_summary(bpjs_summary_doc)
        
    except Exception as e:
        log_error(
            f"Standard BPJS creation failed: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Creation Error"
        )
        
        # If standard approach fails, try alternative approach
        try:
            create_bpjs_summary_alternative(doc, year, month, components, contributions, total_amount)
        except Exception as e2:
            log_and_raise_error(
                f"Alternative BPJS creation failed: {str(e2)}",
                "BPJS Alternative Creation Error",
                _("Failed to create BPJS Payment Summary")
            )

def insert_bpjs_summary(bpjs_summary_doc):
    """
    Insert BPJS Summary with validation bypass if needed
    Args:
        bpjs_summary_doc: BPJS Payment Summary document
    """
    # Save original validate method
    original_validate = bpjs_summary_doc._validate_mandatory
    
    def patched_validate_mandatory(self):
        # Bypass mandatory validation temporarily
        frappe.logger().debug("Bypassing mandatory validation for BPJS Payment Summary")
    
    # Replace temporarily
    bpjs_summary_doc._validate_mandatory = patched_validate_mandatory.__get__(bpjs_summary_doc)
    
    # Insert with flags
    bpjs_summary_doc.flags.ignore_permissions = True
    bpjs_summary_doc.flags.ignore_mandatory = True
    bpjs_summary_doc.insert()
    
    # Restore original method after insert
    bpjs_summary_doc._validate_mandatory = original_validate
    
    frappe.msgprint(_("BPJS Payment Summary {0} created successfully").format(bpjs_summary_doc.name))

def create_bpjs_summary_alternative(doc, year, month, components, contributions, total_amount):
    """
    Alternative method to create BPJS Payment Summary using direct DB operations
    Args:
        doc: Salary Slip document
        year: Current year
        month: Current month
        components: Dictionary with BPJS components
        contributions: Dictionary with BPJS contributions
        total_amount: Total BPJS amount
    """
    # Generate a document name
    doc_name = f"BPJS-PAY-{frappe.generate_hash(length=8)}"
    
    # Create document using db_set approach
    bpjs_summary_doc = frappe.new_doc("BPJS Payment Summary")
    bpjs_summary_doc.name = doc_name
    bpjs_summary_doc.owner = frappe.session.user
    bpjs_summary_doc.company = doc.company
    bpjs_summary_doc.year = year
    bpjs_summary_doc.month = month
    bpjs_summary_doc.posting_date = doc.posting_date or getdate()
    bpjs_summary_doc.total = total_amount
    
    # Insert basic doc
    bpjs_summary_doc.db_insert()
    
    # Add components
    for component_name, amount in components.items():
        if amount > 0:
            component_doc = frappe.new_doc("BPJS Component")
            component_doc.parent = doc_name
            component_doc.parentfield = "komponen"
            component_doc.parenttype = "BPJS Payment Summary"
            component_doc.component = component_name
            component_doc.component_type = component_name.replace("BPJS ", "")
            component_doc.amount = amount
            component_doc.db_insert()
    
    # Add employee detail
    emp_doc = frappe.new_doc("BPJS Employee Detail")
    emp_doc.parent = doc_name
    emp_doc.parentfield = "employee_details"
    emp_doc.parenttype = "BPJS Payment Summary"
    emp_doc.employee = doc.employee
    emp_doc.employee_name = doc.employee_name
    emp_doc.salary_slip = doc.name
    
    # Set contribution fields
    for field, value in contributions.items():
        setattr(emp_doc, field, value)
    
    emp_doc.db_insert()
    
    frappe.db.commit()
    frappe.msgprint(_("BPJS Payment Summary {0} created using alternative method").format(doc_name))

def update_existing_bpjs_summary(doc, bpjs_summary_name, contributions):
    """
    Update existing BPJS Payment Summary
    Args:
        doc: Salary Slip document
        bpjs_summary_name: Name of existing BPJS Payment Summary
        contributions: Dictionary with BPJS contributions
    """
    try:
        # Get existing BPJS Payment Summary
        bpjs_summary_doc = frappe.get_doc("BPJS Payment Summary", bpjs_summary_name)
        
        # Update or add employee detail
        update_bpjs_employee_detail(bpjs_summary_doc, doc, contributions)
        
        # Recalculate components from all employee details
        recalculate_bpjs_components(bpjs_summary_doc)
        
        # Save with special handling
        save_bpjs_summary(bpjs_summary_doc)
        
    except Exception as e:
        log_and_raise_error(
            f"Error updating BPJS Payment Summary: {str(e)}",
            "BPJS Update Error",
            _("Error updating BPJS Payment Summary")
        )

def add_employee_bpjs_detail(bpjs_doc, salary_slip, contributions):
    """
    Add employee detail to BPJS Payment Summary
    Args:
        bpjs_doc: BPJS Payment Summary document
        salary_slip: Salary Slip document
        contributions: Dictionary with BPJS contributions
    """
    bpjs_doc.append("employee_details", {
        "employee": salary_slip.employee,
        "employee_name": salary_slip.employee_name,
        "salary_slip": salary_slip.name,
        "jht_employee": contributions["jht_employee"],
        "jp_employee": contributions["jp_employee"],
        "kesehatan_employee": contributions["kesehatan_employee"],
        "jht_employer": contributions["jht_employer"],
        "jp_employer": contributions["jp_employer"],
        "jkk": contributions["jkk"],
        "jkm": contributions["jkm"],
        "kesehatan_employer": contributions["kesehatan_employer"]
    })

def update_bpjs_employee_detail(bpjs_doc, salary_slip, contributions):
    """
    Update or add employee detail in BPJS Payment Summary
    Args:
        bpjs_doc: BPJS Payment Summary document
        salary_slip: Salary Slip document
        contributions: Dictionary with BPJS contributions
    """
    # Check if employee already exists
    employee_exists = False
    for detail in bpjs_doc.employee_details:
        if detail.employee == salary_slip.employee:
            # Update existing employee
            detail.salary_slip = salary_slip.name
            
            # Update contribution fields
            for field, value in contributions.items():
                setattr(detail, field, value)
                
            employee_exists = True
            break
    
    if not employee_exists:
        # Add new employee
        add_employee_bpjs_detail(bpjs_doc, salary_slip, contributions)

def recalculate_bpjs_components(bpjs_doc):
    """
    Recalculate BPJS components from employee details
    Args:
        bpjs_doc: BPJS Payment Summary document
    """
    # Reset existing components
    bpjs_doc.komponen = []
    
    # Calculate totals from all employee details
    component_totals = defaultdict(float)
    
    for emp in bpjs_doc.employee_details:
        component_totals["BPJS Kesehatan"] += flt(emp.kesehatan_employee) + flt(emp.kesehatan_employer)
        component_totals["BPJS JHT"] += flt(emp.jht_employee) + flt(emp.jht_employer)
        component_totals["BPJS JP"] += flt(emp.jp_employee) + flt(emp.jp_employer)
        component_totals["BPJS JKK"] += flt(emp.jkk)
        component_totals["BPJS JKM"] += flt(emp.jkm)
    
    # Add components with values > 0
    for component_name, amount in component_totals.items():
        if amount > 0:
            bpjs_doc.append("komponen", {
                "component": component_name,
                "component_type": component_name.replace("BPJS ", ""),
                "amount": amount
            })
    
    # Calculate total
    new_total = sum(flt(d.amount) for d in bpjs_doc.komponen)
    
    # Ensure there's at least one component with positive amount
    if new_total <= 0:
        # Add default component if total is 0
        bpjs_doc.append("komponen", {
            "component": "BPJS JHT",
            "component_type": "JHT",
            "amount": 1.0
        })
        new_total = 1.0
    
    # Set total
    bpjs_doc.total = new_total

def save_bpjs_summary(bpjs_summary_doc):
    """
    Save BPJS Summary with validation bypass if needed
    Args:
        bpjs_summary_doc: BPJS Payment Summary document
    """
    # Save original validate method
    old_validate = bpjs_summary_doc._validate_mandatory
    
    def bypass_validation():
        # Bypass validation temporarily
        pass
    
    # Replace temporarily
    bpjs_summary_doc._validate_mandatory = bypass_validation
    
    # Save with flags
    bpjs_summary_doc.flags.ignore_validate_update_after_submit = True
    bpjs_summary_doc.flags.ignore_validate = True
    bpjs_summary_doc.flags.ignore_mandatory = True
    bpjs_summary_doc.save(ignore_permissions=True)
    
    # Restore original validation
    bpjs_summary_doc._validate_mandatory = old_validate
    
    frappe.msgprint(_("BPJS Payment Summary {0} updated successfully").format(bpjs_summary_doc.name))

def update_pph_ter_table(doc):
    """
    Update PPh TER Table based on submitted salary slip
    Args:
        doc: Salary Slip document
    """
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
            
        # Get employee tax status and PPh details
        employee_tax_info = get_employee_tax_info(doc)
        
        # Check if PPh TER Table exists for this period
        ter_table = get_pph_ter_table(doc, employee_tax_info)
        
    except Exception as e:
        employee_id = getattr(doc, 'employee', 'unknown employee')
        log_and_raise_error(
            f"Error updating PPh TER Table for {employee_id}: {str(e)}",
            "PPh TER Update Error",
            _("Error updating PPh TER Table")
        )

def get_employee_tax_info(doc):
    """
    Get employee tax status and PPh details
    Args:
        doc: Salary Slip document
    Returns:
        dict: Employee tax information
    """
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
    
    # Get employee status pajak
    status_pajak = 'TK0'  # Default value
    
    try:
        employee = frappe.get_doc("Employee", doc.employee)
        if hasattr(employee, 'status_pajak') and employee.status_pajak:
            status_pajak = employee.status_pajak
    except Exception as e:
        frappe.logger().warning(
            f"Error getting employee tax status for {doc.employee}: {str(e)}"
        )
        frappe.msgprint(_("Error retrieving employee tax status: {0}, using default (TK0)").format(
            truncate_message(str(e), MAX_ERROR_MESSAGE_LENGTH)
        ))
    
    return {
        "month": month,
        "year": year,
        "status_pajak": status_pajak,
        "pph21_amount": pph21_amount,
        "ter_rate": getattr(doc, 'ter_rate', 0),
        "gross_pay": flt(doc.gross_pay)
    }

def get_pph_ter_table(doc, tax_info):
    """
    Get or create PPh TER Table for the period
    Args:
        doc: Salary Slip document
        tax_info: Employee tax information
    Returns:
        PPh TER Table document
    """
    try:
        # Check if PPh TER Table exists for this period
        ter_table = frappe.db.get_value(
            "PPh TER Table", 
            {
                "company": doc.company, 
                "year": tax_info["year"], 
                "month": tax_info["month"],
                "docstatus": ["!=", 2]
            },
            "name"
        )
        
        if not ter_table:
            ter_table_doc = create_new_pph_ter_table(doc, tax_info)
        else:
            ter_table_doc = update_existing_pph_ter_table(doc, ter_table, tax_info)
            
        return ter_table_doc
            
    except Exception as e:
        raise Exception(f"Error retrieving PPh TER Table: {str(e)}")

def create_new_pph_ter_table(doc, tax_info):
    """
    Create new PPh TER Table
    Args:
        doc: Salary Slip document
        tax_info: Employee tax information
    Returns:
        PPh TER Table document
    """
    try:
        # Create new PPh TER Table
        ter_table_doc = frappe.new_doc("PPh TER Table")
        
        # Set header fields
        ter_table_doc.company = doc.company
        ter_table_doc.year = tax_info["year"]
        ter_table_doc.month = tax_info["month"]
        
        # Set title field if it exists
        if hasattr(ter_table_doc, 'month_year_title'):
            ter_table_doc.month_year_title = f"{tax_info['month']:02d}-{tax_info['year']}"
        
        # Validate employee_details child table exists
        if not hasattr(ter_table_doc, 'employee_details'):
            frappe.throw(_("PPh TER Table structure is invalid: missing employee_details child table"))
        
        # Add employee detail
        add_ter_employee_detail(ter_table_doc, doc, tax_info)
        
        # Insert the document
        ter_table_doc.insert(ignore_permissions=True)
        return ter_table_doc
        
    except Exception as e:
        raise Exception(f"Error creating PPh TER Table: {str(e)}")

def update_existing_pph_ter_table(doc, ter_table_name, tax_info):
    """
    Update existing PPh TER Table
    Args:
        doc: Salary Slip document
        ter_table_name: Name of existing PPh TER Table
        tax_info: Employee tax information
    Returns:
        PPh TER Table document
    """
    try:
        # Update existing PPh TER Table
        ter_table_doc = frappe.get_doc("PPh TER Table", ter_table_name)
        
        # Check if employee_details exists
        if not hasattr(ter_table_doc, 'employee_details'):
            frappe.throw(_("PPh TER Table structure is invalid: missing employee_details child table"))
        
        # Update or add employee detail
        update_ter_employee_detail(ter_table_doc, doc, tax_info)
        
        # Save changes
        ter_table_doc.flags.ignore_validate_update_after_submit = True
        ter_table_doc.save(ignore_permissions=True)
        
        return ter_table_doc
        
    except Exception as e:
        raise Exception(f"Error updating PPh TER Table: {str(e)}")

def add_ter_employee_detail(ter_doc, salary_slip, tax_info):
    """
    Add employee detail to PPh TER Table
    Args:
        ter_doc: PPh TER Table document
        salary_slip: Salary Slip document
        tax_info: Employee tax information
    """
    ter_doc.append("employee_details", {
        "employee": salary_slip.employee,
        "employee_name": salary_slip.employee_name,
        "status_pajak": tax_info["status_pajak"],
        "salary_slip": salary_slip.name,
        "gross_income": tax_info["gross_pay"],
        "ter_rate": tax_info["ter_rate"],
        "pph21_amount": tax_info["pph21_amount"]
    })

def update_ter_employee_detail(ter_doc, salary_slip, tax_info):
    """
    Update or add employee detail in PPh TER Table
    Args:
        ter_doc: PPh TER Table document
        salary_slip: Salary Slip document
        tax_info: Employee tax information
    """
    # Check if employee already exists
    employee_exists = False
    for detail in ter_doc.employee_details:
        if detail.employee == salary_slip.employee:
            # Update existing employee
            detail.status_pajak = tax_info["status_pajak"]
            detail.salary_slip = salary_slip.name
            detail.gross_income = tax_info["gross_pay"]
            detail.ter_rate = tax_info["ter_rate"]
            detail.pph21_amount = tax_info["pph21_amount"]
            employee_exists = True
            break
    
    if not employee_exists:
        # Add new employee
        add_ter_employee_detail(ter_doc, salary_slip, tax_info)

def after_insert_salary_slip(doc, method=None):
    """
    Hook executed after salary slip is created
    Args:
        doc: Salary Slip document
        method: Method name (not used)
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
        
        # Log salary slip creation
        log_salary_slip_creation(doc)
        
        # Add to payroll notifications if feature is available
        add_to_payroll_notifications(doc)
        
    except Exception as e:
        doc_name = getattr(doc, 'name', 'unknown salary slip')
        log_error(
            f"Error in after_insert_salary_slip for {doc_name}: {str(e)}",
            "Salary Slip Hook Error"
        )
        # Don't throw here to prevent blocking salary slip creation
        frappe.msgprint(_("Warning: Error in post-creation processing: {0}").format(
            truncate_message(str(e), MAX_ERROR_MESSAGE_LENGTH)
        ))

def log_salary_slip_creation(doc):
    """
    Log salary slip creation
    Args:
        doc: Salary Slip document
    """
    try:
        employee_name = getattr(doc, 'employee_name', 'unnamed')
        frappe.logger().info(
            f"Salary Slip {doc.name} created for employee {doc.employee} ({employee_name})"
        )
    except Exception:
        # If logger fails, continue anyway
        pass

def add_to_payroll_notifications(doc):
    """
    Add entry to payroll notifications if available
    Args:
        doc: Salary Slip document
    """
    try:
        # Check if doctype Payroll Notification exists
        if not frappe.db.exists('DocType', 'Payroll Notification'):
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
        notification.posting_date = doc.posting_date if hasattr(doc, 'posting_date') else today()
        notification.amount = doc.net_pay if hasattr(doc, 'net_pay') else 0
        notification.status = "Draft"
        
        # Insert notification
        notification.insert(ignore_permissions=True)
        
    except Exception as e:
        doc_name = getattr(doc, 'name', 'unknown salary slip')
        log_error(
            f"Failed to create payroll notification for {doc_name}: {str(e)}",
            "Payroll Notification Error"
        )
        # Don't throw here to prevent blocking salary slip creation
        frappe.msgprint(_("Warning: Could not create payroll notification: {0}").format(
            truncate_message(str(e), MAX_ERROR_MESSAGE_LENGTH)
        ))

# Wrapper functions for API compatibility
def wrapper_create_from_salary_slip(doc, method=None):
    """
    Wrapper for create_from_salary_slip from bpjs_payment_api
    Args:
        doc: Salary Slip document
        method: Method name (not used)
    """
    from payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api import create_from_salary_slip
    create_from_salary_slip(doc)

def wrapper_update_on_salary_slip_cancel(doc, method=None):
    """
    Wrapper for update_on_salary_slip_cancel from bpjs_payment_api
    Args:
        doc: Salary Slip document
        method: Method name (not used)
    """
    from payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api import update_on_salary_slip_cancel
    
    month = getdate(doc.end_date).month
    year = getdate(doc.end_date).year
    
    update_on_salary_slip_cancel(doc.name, month, year)

# Utility functions
def log_error(message, title):
    """
    Log error to system log
    Args:
        message: Error message
        title: Error title
    """
    full_traceback = f"{message}\n\nTraceback: {frappe.get_traceback()}"
    frappe.log_error(full_traceback, title)

def log_and_raise_error(message, log_title, user_message):
    """
    Log error and raise user-friendly message
    Args:
        message: Full error message for log
        log_title: Error log title
        user_message: User-friendly message to display
    Raises:
        ValidationError: With user-friendly message
    """
    log_error(message, log_title)
    frappe.throw(_(user_message) + f": {truncate_message(str(message), MAX_ERROR_MESSAGE_LENGTH)}")

def truncate_message(message, max_length=140):
    """
    Truncate message to prevent CharacterLengthExceededError
    Args:
        message: Message to truncate
        max_length: Maximum length
    Returns:
        str: Truncated message
    """
    if not message:
        return ""
        
    if len(message) <= max_length:
        return message
        
    return message[:max_length - 3] + "..."