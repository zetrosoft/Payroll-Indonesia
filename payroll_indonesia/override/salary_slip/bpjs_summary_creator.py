# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 10:22:12 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate, now
import json

# Setup debugging logger
def get_logger():
    """Get a logger instance for BPJS module"""
    return frappe.logger("bpjs_module", with_more_info=True)

def create_bpjs_payment_summary(doc):
    """Create or update BPJS Payment Summary based on submitted salary slip"""
    logger = get_logger()
    logger.info(f"Starting BPJS Payment Summary creation for salary slip {doc.name}")
    
    try:
        # Check if BPJS Payment Summary DocType exists
        if not frappe.db.exists("DocType", "BPJS Payment Summary"):
            logger.error("BPJS Payment Summary DocType not found")
            frappe.msgprint(_("BPJS Payment Summary DocType not found. Cannot create BPJS summary."))
            return
            
        # Determine year and month from salary slip
        end_date = getdate(doc.end_date)
        month = end_date.month
        year = end_date.year
        logger.debug(f"Processing for period: Year={year}, Month={month}")
    
        # Get BPJS components from salary slip
        logger.debug(f"Extracting BPJS employee components from salary slip {doc.name}")
        bpjs_employee_components = get_bpjs_employee_components(doc)
        logger.debug(f"Employee components: {json.dumps(bpjs_employee_components)}")
        
        logger.debug(f"Calculating BPJS employer components for salary slip {doc.name}")
        bpjs_employer_components = calculate_bpjs_employer_components(doc)
        logger.debug(f"Employer components: {json.dumps(bpjs_employer_components)}")
    
        # Check if BPJS Payment Summary exists for this period
        logger.debug(f"Looking for existing BPJS summary for {year}-{month}")
        bpjs_summary = find_existing_bpjs_summary(doc, year, month)
        logger.debug(f"Existing BPJS summary found: {bpjs_summary or 'None'}")
    
        if not bpjs_summary:
            logger.info(f"Creating new BPJS summary for {year}-{month}")
            create_new_bpjs_summary(doc, year, month, bpjs_employee_components, bpjs_employer_components)
        else:
            logger.info(f"Updating existing BPJS summary {bpjs_summary}")
            update_existing_bpjs_summary(doc, bpjs_summary, bpjs_employee_components, bpjs_employer_components)
        
        logger.info(f"BPJS Payment Summary processing completed for salary slip {doc.name}")
        
    except Exception as e:
        logger.error(f"Error in create_bpjs_payment_summary: {str(e)}\n{frappe.get_traceback()}")
        frappe.log_error(
            f"Error creating/updating BPJS Payment Summary for {doc.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Summary Error"
        )
        frappe.throw(_("Error creating/updating BPJS Payment Summary: {0}").format(str(e)))

def get_bpjs_employee_components(doc):
    """Get BPJS employee components from salary slip"""
    logger = get_logger()
    logger.debug(f"Extracting BPJS employee components from salary slip {doc.name}")
    
    bpjs_data = {
        "jht_employee": 0,
        "jp_employee": 0,
        "kesehatan_employee": 0
    }

    # Get employee components
    for deduction in doc.deductions:
        if deduction.salary_component == "BPJS JHT Employee":
            bpjs_data["jht_employee"] = flt(deduction.amount)
            logger.debug(f"Found JHT Employee: {bpjs_data['jht_employee']}")
        elif deduction.salary_component == "BPJS JP Employee":
            bpjs_data["jp_employee"] = flt(deduction.amount)
            logger.debug(f"Found JP Employee: {bpjs_data['jp_employee']}")
        elif deduction.salary_component == "BPJS Kesehatan Employee":
            bpjs_data["kesehatan_employee"] = flt(deduction.amount)
            logger.debug(f"Found Kesehatan Employee: {bpjs_data['kesehatan_employee']}")
    
    logger.debug(f"Total employee contribution: {sum(bpjs_data.values())}")
    return bpjs_data

def calculate_bpjs_employer_components(doc):
    """Calculate BPJS employer components based on BPJS settings"""
    logger = get_logger()
    logger.debug(f"Calculating BPJS employer components for salary slip {doc.name}")
    
    try:
        # Get BPJS Settings for employer calculations
        logger.debug("Fetching BPJS Settings")
        bpjs_settings = frappe.get_single("BPJS Settings")
        
        # Validate required fields exist in BPJS Settings
        required_fields = [
            'jht_employer_percent', 'jp_max_salary', 'jp_employer_percent',
            'jkk_percent', 'jkm_percent', 'kesehatan_max_salary',
            'kesehatan_employer_percent'
        ]
    
        for field in required_fields:
            if not hasattr(bpjs_settings, field) or getattr(bpjs_settings, field) is None:
                logger.error(f"BPJS Settings missing required field: {field}")
                frappe.throw(_("BPJS Settings missing required field: {0}").format(field))
        
        logger.debug(f"BPJS Settings validated, calculating with gross pay: {doc.gross_pay}")
    
        # Calculate employer components
        # JHT Employer (3.7%)
        jht_employer = doc.gross_pay * (bpjs_settings.jht_employer_percent / 100)
        logger.debug(f"JHT Employer calculated: {jht_employer} ({bpjs_settings.jht_employer_percent}%)")
    
        # JP Employer (2%)
        jp_salary = min(doc.gross_pay, bpjs_settings.jp_max_salary)
        jp_employer = jp_salary * (bpjs_settings.jp_employer_percent / 100)
        logger.debug(f"JP Employer calculated: {jp_employer} ({bpjs_settings.jp_employer_percent}% of {jp_salary})")
    
        # JKK (0.24% - 1.74% depending on risk)
        jkk = doc.gross_pay * (bpjs_settings.jkk_percent / 100)
        logger.debug(f"JKK calculated: {jkk} ({bpjs_settings.jkk_percent}%)")
    
        # JKM (0.3%)
        jkm = doc.gross_pay * (bpjs_settings.jkm_percent / 100)
        logger.debug(f"JKM calculated: {jkm} ({bpjs_settings.jkm_percent}%)")
    
        # Kesehatan Employer (4%)
        kesehatan_salary = min(doc.gross_pay, bpjs_settings.kesehatan_max_salary)
        kesehatan_employer = kesehatan_salary * (bpjs_settings.kesehatan_employer_percent / 100)
        logger.debug(f"Kesehatan Employer calculated: {kesehatan_employer} ({bpjs_settings.kesehatan_employer_percent}% of {kesehatan_salary})")
        
        employer_components = {
            "jht_employer": jht_employer,
            "jp_employer": jp_employer,
            "jkk": jkk,
            "jkm": jkm,
            "kesehatan_employer": kesehatan_employer
        }
        
        total_employer = sum(employer_components.values())
        logger.debug(f"Total employer contribution: {total_employer}")
        
        return employer_components
        
    except Exception as e:
        logger.error(f"Error calculating employer BPJS components: {str(e)}\n{frappe.get_traceback()}")
        frappe.throw(_("Error calculating employer BPJS components: {0}").format(str(e)))

def find_existing_bpjs_summary(doc, year, month):
    """Find existing BPJS Payment Summary for this period"""
    logger = get_logger()
    logger.debug(f"Looking for existing BPJS Payment Summary for {year}-{month}")
    
    try:
        # Check column structure first
        logger.debug("Validating BPJS Payment Summary DocType structure")
        doctype_meta = frappe.get_meta("BPJS Payment Summary")
        if not (doctype_meta.has_field("year") and doctype_meta.has_field("month")):
            logger.error("BPJS Payment Summary missing required fields 'year' and/or 'month'")
            frappe.throw(_("BPJS Payment Summary DocType missing required fields 'year' and/or 'month'"))
        
        bpjs_summary = frappe.db.get_value(
            "BPJS Payment Summary",
            {"company": doc.company, "year": year, "month": month, "docstatus": ["!=", 2]},
            "name"
        )
        
        logger.debug(f"BPJS Payment Summary search result: {bpjs_summary or 'Not found'}")
        return bpjs_summary
        
    except Exception as e:
        logger.error(f"Error in find_existing_bpjs_summary: {str(e)}\n{frappe.get_traceback()}")
        if "Unknown column" in str(e):
            frappe.throw(_(
                "Database structure issue: {0} - Please run 'bench migrate' "
                "or fix the BPJS Payment Summary DocType structure."
            ).format(str(e)))
        else:
            frappe.throw(_("Error querying BPJS Payment Summary: {0}").format(str(e)))

def create_new_bpjs_summary(doc, year, month, employee_components, employer_components):
    """Create a new BPJS Payment Summary"""
    logger = get_logger()
    logger.info(f"Creating new BPJS Payment Summary for {year}-{month}")
    
    try:
        bpjs_summary_doc = frappe.new_doc("BPJS Payment Summary")
        bpjs_summary_doc.company = doc.company
        bpjs_summary_doc.year = year
        bpjs_summary_doc.month = month
        bpjs_summary_doc.posting_date = getdate()
        bpjs_summary_doc.status = "Draft"
        
        logger.debug(f"Created new BPJS summary document: company={doc.company}, year={year}, month={month}")
        
        # Set month name if field exists
        if hasattr(bpjs_summary_doc, 'month_name'):
            month_names = ['January', 'February', 'March', 'April', 'May', 'June', 
                          'July', 'August', 'September', 'October', 'November', 'December']
            if month >= 1 and month <= 12:
                bpjs_summary_doc.month_name = month_names[month-1]
                logger.debug(f"Set month_name to {bpjs_summary_doc.month_name}")
    
        # Set title if field exists
        if hasattr(bpjs_summary_doc, 'month_year_title'):
            month_name = month_names[month-1] if month >= 1 and month <= 12 else str(month)
            bpjs_summary_doc.month_year_title = f"{month_name} {year}"
            logger.debug(f"Set month_year_title to {bpjs_summary_doc.month_year_title}")
    
        # Check if employee_details field exists
        if not hasattr(bpjs_summary_doc, 'employee_details'):
            logger.error("BPJS Payment Summary structure is invalid. Missing employee_details child table.")
            frappe.throw(_("BPJS Payment Summary structure is invalid. Missing employee_details child table."))
    
        # Create first employee detail
        logger.debug(f"Adding employee {doc.employee} to BPJS summary")
        add_employee_to_bpjs_summary(bpjs_summary_doc, doc, employee_components, employer_components)
    
        # Add BPJS Payment Components for detailed tracking
        logger.debug("Creating BPJS payment summary components")
        create_bpjs_payment_summary_components(bpjs_summary_doc, employee_components, employer_components)
    
        logger.debug("Inserting BPJS summary document")
        bpjs_summary_doc.insert(ignore_permissions=True)
        logger.info(f"BPJS Summary document created with name: {bpjs_summary_doc.name}")
        
        # Trigger the set_account_details method manually
        # This will populate account_details from BPJS Settings
        if hasattr(bpjs_summary_doc, 'set_account_details'):
            logger.debug("Setting account details from BPJS Settings")
            bpjs_summary_doc.set_account_details()
            bpjs_summary_doc.save(ignore_permissions=True)
            logger.debug("BPJS summary saved with account details")
        
    except Exception as e:
        logger.error(f"Error in create_new_bpjs_summary: {str(e)}\n{frappe.get_traceback()}")
        frappe.throw(_("Error creating BPJS Payment Summary: {0}").format(str(e)))

def update_existing_bpjs_summary(doc, bpjs_summary_name, employee_components, employer_components):
    """Update existing BPJS Payment Summary"""
    logger = get_logger()
    logger.info(f"Updating existing BPJS Payment Summary {bpjs_summary_name}")
    
    try:
        bpjs_summary_doc = frappe.get_doc("BPJS Payment Summary", bpjs_summary_name)
        logger.debug(f"Loaded BPJS summary document: {bpjs_summary_name}, status={bpjs_summary_doc.docstatus}")
        
        # Skip if document is already submitted
        if bpjs_summary_doc.docstatus == 1:
            logger.warning(f"BPJS Payment Summary {bpjs_summary_name} is already submitted. Cannot update.")
            frappe.msgprint(_("BPJS Payment Summary {0} is already submitted. Cannot update.").format(bpjs_summary_name))
            return
    
        # Check if employee_details field exists
        if not hasattr(bpjs_summary_doc, 'employee_details'):
            logger.error("BPJS Payment Summary structure is invalid. Missing employee_details child table.")
            frappe.throw(_("BPJS Payment Summary structure is invalid. Missing employee_details child table."))
    
        # Check if employee already exists
        employee_exists = False
        for detail in bpjs_summary_doc.employee_details:
            if detail.employee == doc.employee:
                # Update existing employee
                logger.debug(f"Employee {doc.employee} already exists in BPJS summary, updating details")
                update_bpjs_summary_detail(detail, doc, employee_components, employer_components)
                employee_exists = True
                break
    
        if not employee_exists:
            # Add new employee
            logger.debug(f"Adding new employee {doc.employee} to existing BPJS summary")
            add_employee_to_bpjs_summary(bpjs_summary_doc, doc, employee_components, employer_components)
    
        # Update komponen table
        logger.debug("Updating BPJS payment summary components")
        update_bpjs_payment_summary_components(bpjs_summary_doc)
    
        # Save changes
        logger.debug("Saving updated BPJS summary document")
        bpjs_summary_doc.save(ignore_permissions=True)
        logger.info(f"BPJS Summary document {bpjs_summary_name} updated successfully")
        
        # Trigger the set_account_details method manually
        # This will update account_details from BPJS Settings
        if hasattr(bpjs_summary_doc, 'set_account_details'):
            logger.debug("Updating account details from BPJS Settings")
            bpjs_summary_doc.set_account_details()
            bpjs_summary_doc.save(ignore_permissions=True)
            logger.debug("BPJS summary saved with updated account details")
        
    except Exception as e:
        logger.error(f"Error in update_existing_bpjs_summary: {str(e)}\n{frappe.get_traceback()}")
        frappe.throw(_("Error updating BPJS Payment Summary: {0}").format(str(e)))

def add_employee_to_bpjs_summary(bpjs_doc, salary_slip, employee_components, employer_components):
    """Add employee details to BPJS Summary document"""
    logger = get_logger()
    logger.debug(f"Adding employee {salary_slip.employee} to BPJS summary")
    
    try:
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
        logger.debug(f"Employee {salary_slip.employee} added with JHT:{employee_components['jht_employee']}, JP:{employee_components['jp_employee']}")
    except Exception as e:
        logger.error(f"Error in add_employee_to_bpjs_summary: {str(e)}")
        raise

def update_bpjs_summary_detail(detail, salary_slip, employee_components, employer_components):
    """Update BPJS summary detail for an existing employee"""
    logger = get_logger()
    logger.debug(f"Updating details for employee {salary_slip.employee} in BPJS summary")
    
    try:
        old_values = {
            "salary_slip": detail.salary_slip,
            "jht_employee": detail.jht_employee,
            "jp_employee": detail.jp_employee,
            "kesehatan_employee": detail.kesehatan_employee
        }
        
        detail.salary_slip = salary_slip.name
        detail.jht_employee = employee_components["jht_employee"]
        detail.jp_employee = employee_components["jp_employee"]
        detail.kesehatan_employee = employee_components["kesehatan_employee"]
        detail.jht_employer = employer_components["jht_employer"]
        detail.jp_employer = employer_components["jp_employer"]
        detail.jkk = employer_components["jkk"]
        detail.jkm = employer_components["jkm"]
        detail.kesehatan_employer = employer_components["kesehatan_employer"]
        
        logger.debug(f"Updated employee {salary_slip.employee} details: Old values={json.dumps(old_values)}, New values={json.dumps(employee_components)}")
    except Exception as e:
        logger.error(f"Error in update_bpjs_summary_detail: {str(e)}")
        raise

def create_bpjs_payment_summary_components(bpjs_summary_doc, employee_components, employer_components):
    """Create BPJS Payment Components for the payment summary"""
    logger = get_logger()
    logger.debug("Creating BPJS Payment Components for summary")
    
    try:
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
            logger.debug(f"Added JHT component with total: {jht_total}")
        
        # Add JP component (employee + employer)
        jp_total = employee_components["jp_employee"] + employer_components["jp_employer"]
        if jp_total > 0:
            bpjs_summary_doc.append("komponen", {
                "component": "BPJS JP",
                "description": "JP Contribution (Employee + Employer)",
                "amount": jp_total
            })
            logger.debug(f"Added JP component with total: {jp_total}")
        
        # Add JKK component
        if employer_components["jkk"] > 0:
            bpjs_summary_doc.append("komponen", {
                "component": "BPJS JKK",
                "description": "JKK Contribution (Employer)",
                "amount": employer_components["jkk"]
            })
            logger.debug(f"Added JKK component with total: {employer_components['jkk']}")
        
        # Add JKM component
        if employer_components["jkm"] > 0:
            bpjs_summary_doc.append("komponen", {
                "component": "BPJS JKM",
                "description": "JKM Contribution (Employer)",
                "amount": employer_components["jkm"]
            })
            logger.debug(f"Added JKM component with total: {employer_components['jkm']}")
        
        # Add Kesehatan component (employee + employer)
        kesehatan_total = employee_components["kesehatan_employee"] + employer_components["kesehatan_employer"]
        if kesehatan_total > 0:
            bpjs_summary_doc.append("komponen", {
                "component": "BPJS Kesehatan",
                "description": "Kesehatan Contribution (Employee + Employer)",
                "amount": kesehatan_total
            })
            logger.debug(f"Added Kesehatan component with total: {kesehatan_total}")
    except Exception as e:
        logger.error(f"Error in create_bpjs_payment_summary_components: {str(e)}")
        raise

def update_bpjs_payment_summary_components(bpjs_summary_doc):
    """Update BPJS Payment Components based on employee details"""
    logger = get_logger()
    logger.debug("Updating BPJS Payment Components based on employee details")
    
    try:
        # Aggregates for each component
        jht_total = 0
        jp_total = 0
        jkk_total = 0
        jkm_total = 0
        kesehatan_total = 0
        
        # Calculate totals from employee_details
        logger.debug(f"Calculating totals from {len(bpjs_summary_doc.employee_details)} employee records")
        for detail in bpjs_summary_doc.employee_details:
            jht_total += flt(detail.jht_employee) + flt(detail.jht_employer)
            jp_total += flt(detail.jp_employee) + flt(detail.jp_employer)
            jkk_total += flt(detail.jkk)
            jkm_total += flt(detail.jkm)
            kesehatan_total += flt(detail.kesehatan_employee) + flt(detail.kesehatan_employer)
        
        logger.debug(f"Calculated totals - JHT: {jht_total}, JP: {jp_total}, JKK: {jkk_total}, JKM: {jkm_total}, Kesehatan: {kesehatan_total}")
        
        # Clear existing components
        bpjs_summary_doc.komponen = []
        logger.debug("Cleared existing components")
        
        # Create new components with updated totals
        if jht_total > 0:
            bpjs_summary_doc.append("komponen", {
                "component": "BPJS JHT",
                "description": "JHT Contribution (Employee + Employer)",
                "amount": jht_total
            })
            logger.debug(f"Added JHT component with total: {jht_total}")
        
        if jp_total > 0:
            bpjs_summary_doc.append("komponen", {
                "component": "BPJS JP",
                "description": "JP Contribution (Employee + Employer)",
                "amount": jp_total
            })
            logger.debug(f"Added JP component with total: {jp_total}")
        
        if jkk_total > 0:
            bpjs_summary_doc.append("komponen", {
                "component": "BPJS JKK",
                "description": "JKK Contribution (Employer)",
                "amount": jkk_total
            })
            logger.debug(f"Added JKK component with total: {jkk_total}")
        
        if jkm_total > 0:
            bpjs_summary_doc.append("komponen", {
                "component": "BPJS JKM",
                "description": "JKM Contribution (Employer)",
                "amount": jkm_total
            })
            logger.debug(f"Added JKM component with total: {jkm_total}")
        
        if kesehatan_total > 0:
            bpjs_summary_doc.append("komponen", {
                "component": "BPJS Kesehatan",
                "description": "Kesehatan Contribution (Employee + Employer)",
                "amount": kesehatan_total
            })
            logger.debug(f"Added Kesehatan component with total: {kesehatan_total}")
    except Exception as e:
        logger.error(f"Error in update_bpjs_payment_summary_components: {str(e)}")
        raise

def create_bpjs_payment_component(doc, bpjs_summary_doc=None):
    """
    Create BPJS Payment Component based on salary slip
    
    Args:
        doc: The salary slip document
        bpjs_summary_doc: Optional BPJS Payment Summary document
                          If not provided, will try to find it
    """
    logger = get_logger()
    logger.info(f"Starting creation of BPJS Payment Component for salary slip {doc.name}")
    
    try:
        # Check if BPJS Payment Component DocType exists
        if not frappe.db.exists("DocType", "BPJS Payment Component"):
            logger.warning("BPJS Payment Component DocType not found")
            frappe.msgprint(_("BPJS Payment Component DocType not found. Cannot create component."))
            return
        
        # Get the employee BPJS component data
        logger.debug("Extracting employee BPJS components")
        bpjs_employee_components = get_bpjs_employee_components(doc)
        
        # Skip if no BPJS components found in salary slip
        if sum(bpjs_employee_components.values()) <= 0:
            logger.info("No BPJS components found in salary slip, skipping component creation")
            return
        
        # Get employer components from BPJS settings
        logger.debug("Calculating employer BPJS components")
        bpjs_employer_components = calculate_bpjs_employer_components(doc)
            
        # Find or get BPJS Payment Summary if not provided
        if not bpjs_summary_doc:
            month = getdate(doc.end_date).month
            year = getdate(doc.end_date).year
            logger.debug(f"Looking for BPJS Payment Summary for {year}-{month}")
            
            bpjs_summary = find_existing_bpjs_summary(doc, year, month)
            
            if not bpjs_summary:
                logger.info(f"No BPJS Payment Summary found for {month}-{year}. Creating new summary.")
                frappe.msgprint(_("No BPJS Payment Summary found for {0}-{1}. Creating new summary.").format(month, year))
                # Create new BPJS Payment Summary
                create_new_bpjs_summary(doc, year, month, bpjs_employee_components, bpjs_employer_components)
                bpjs_summary = find_existing_bpjs_summary(doc, year, month)
                
            if not bpjs_summary:
                logger.error(f"Failed to create BPJS Payment Summary for {month}-{year}")
                frappe.msgprint(_("Failed to create BPJS Payment Summary for {0}-{1}").format(month, year))
                return
                
            bpjs_summary_doc = frappe.get_doc("BPJS Payment Summary", bpjs_summary)
            logger.debug(f"Using BPJS Payment Summary: {bpjs_summary}")
        
        # Check if BPJS Payment Component already exists for this employee and salary slip
        logger.debug(f"Checking if BPJS Payment Component already exists for employee {doc.employee} and salary slip {doc.name}")
        existing_component = find_existing_bpjs_payment_component(doc, bpjs_summary_doc.name)
        logger.debug(f"Existing component found: {existing_component or 'None'}")
        
        if existing_component:
            # Update existing BPJS Payment Component
            logger.info(f"Updating existing BPJS Payment Component {existing_component}")
            return update_bpjs_payment_component(existing_component, doc, bpjs_summary_doc, 
                                             bpjs_employee_components, bpjs_employer_components)
        else:
            # Create new BPJS Payment Component
            logger.info("Creating new BPJS Payment Component")
            return create_new_bpjs_payment_component(doc, bpjs_summary_doc, 
                                                  bpjs_employee_components, bpjs_employer_components)
        
    except Exception as e:
        logger.error(f"Error in create_bpjs_payment_component: {str(e)}\n{frappe.get_traceback()}")
        frappe.log_error(
            f"Error creating BPJS Payment Component for {doc.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Component Creation Error"
        )
        frappe.msgprint(_("Error creating BPJS Payment Component: {0}").format(str(e)))
        return None

def find_existing_bpjs_payment_component(salary_slip, bpjs_summary_name):
    """Find existing BPJS Payment Component for this employee and salary slip"""
    logger = get_logger()
    logger.debug(f"Looking for existing BPJS Payment Component for employee {salary_slip.employee}, salary slip {salary_slip.name}")
    
    try:
        component_name = frappe.db.get_value(
            "BPJS Payment Component", 
            {
                "employee": salary_slip.employee, 
                "salary_slip": salary_slip.name,
                "bpjs_payment_summary": bpjs_summary_name,
                "docstatus": ["!=", 2]
            },
            "name"
        )
        logger.debug(f"BPJS Payment Component search result: {component_name or 'Not found'}")
        return component_name
        
    except Exception as e:
        logger.error(f"Error in find_existing_bpjs_payment_component: {str(e)}\n{frappe.get_traceback()}")
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
    logger = get_logger()
    logger.info(f"Creating new BPJS Payment Component for employee {salary_slip.employee}, salary slip {salary_slip.name}")
    
    try:
        # Create BPJS Payment Component
        bpjs_component = frappe.new_doc("BPJS Payment Component")
        
        # Set document fields
        bpjs_component.employee = salary_slip.employee
        bpjs_component.employee_name = salary_slip.employee_name
        bpjs_component.salary_slip = salary_slip.name
        bpjs_component.bpjs_payment_summary = bpjs_summary_doc.name
        bpjs_component.posting_date = getdate()
        
        logger.debug(f"Created new BPJS component document: employee={salary_slip.employee}, salary_slip={salary_slip.name}")
        
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
        
        logger.debug(f"Added employee components: {json.dumps(employee_components)}")
        logger.debug(f"Added employer components: {json.dumps(employer_components)}")
        
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
        
        logger.debug(f"Calculated totals - Employee: {bpjs_component.total_employee}, Employer: {bpjs_component.total_employer}, Grand Total: {bpjs_component.grand_total}")
        
        # Add BPJS components for detailed tracking (if the field exists)
        if hasattr(bpjs_component, 'bpjs_components'):
            logger.debug("Adding detailed BPJS components")
            
            # Add JHT Employee component
            if employee_components["jht_employee"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JHT", 
                    "description": "JHT Employee Contribution",
                    "amount": employee_components["jht_employee"]
                })
                logger.debug(f"Added JHT Employee component: {employee_components['jht_employee']}")
                
            # Add JP Employee component
            if employee_components["jp_employee"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JP",
                    "description": "JP Employee Contribution",
                    "amount": employee_components["jp_employee"]
                })
                logger.debug(f"Added JP Employee component: {employee_components['jp_employee']}")
                
            # Add Kesehatan Employee component
            if employee_components["kesehatan_employee"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS Kesehatan",
                    "description": "Kesehatan Employee Contribution",
                    "amount": employee_components["kesehatan_employee"]
                })
                logger.debug(f"Added Kesehatan Employee component: {employee_components['kesehatan_employee']}")
                
            # Add JHT Employer component
            if employer_components["jht_employer"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JHT",
                    "description": "JHT Employer Contribution",
                    "amount": employer_components["jht_employer"]
                })
                logger.debug(f"Added JHT Employer component: {employer_components['jht_employer']}")
                
            # Add JP Employer component
            if employer_components["jp_employer"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JP",
                    "description": "JP Employer Contribution",
                    "amount": employer_components["jp_employer"]
                })
                logger.debug(f"Added JP Employer component: {employer_components['jp_employer']}")
                
            # Add JKK component
            if employer_components["jkk"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JKK",
                    "description": "JKK Employer Contribution",
                    "amount": employer_components["jkk"]
                })
                logger.debug(f"Added JKK component: {employer_components['jkk']}")
                
            # Add JKM component
            if employer_components["jkm"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JKM",
                    "description": "JKM Employer Contribution",
                    "amount": employer_components["jkm"]
                })
                logger.debug(f"Added JKM component: {employer_components['jkm']}")
                
            # Add Kesehatan Employer component
            if employer_components["kesehatan_employer"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS Kesehatan",
                    "description": "Kesehatan Employer Contribution",
                    "amount": employer_components["kesehatan_employer"]
                })
                logger.debug(f"Added Kesehatan Employer component: {employer_components['kesehatan_employer']}")
        
        # Save the document
        logger.debug("Inserting BPJS component document")
        bpjs_component.insert(ignore_permissions=True)
        logger.info(f"BPJS Payment Component created with name: {bpjs_component.name}")
        frappe.msgprint(_("Created BPJS Payment Component {0}").format(bpjs_component.name))
        
        return bpjs_component.name
        
    except Exception as e:
        logger.error(f"Error in create_new_bpjs_payment_component: {str(e)}\n{frappe.get_traceback()}")
        frappe.log_error(
            f"Error creating BPJS Payment Component for {salary_slip.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Component Creation Error"
        )
        frappe.msgprint(_("Error creating BPJS Payment Component: {0}").format(str(e)))
        return None

def update_bpjs_payment_component(component_name, salary_slip, bpjs_summary_doc, employee_components, employer_components):
    """Update an existing BPJS Payment Component"""
    logger = get_logger()
    logger.info(f"Updating existing BPJS Payment Component {component_name}")
    
    try:
        # Get the BPJS Payment Component document
        bpjs_component = frappe.get_doc("BPJS Payment Component", component_name)
        logger.debug(f"Loaded BPJS component document: {component_name}")
        
        # Update the fields
        bpjs_component.employee_name = salary_slip.employee_name  # In case employee name changed
        bpjs_component.posting_date = getdate()
        
        # Store old values for debugging
        old_values = {
            "jht_employee": bpjs_component.jht_employee,
            "jp_employee": bpjs_component.jp_employee,
            "kesehatan_employee": bpjs_component.kesehatan_employee,
        }
        logger.debug(f"Previous values: {json.dumps(old_values)}")
        
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
        
        logger.debug(f"Updated to new values - Employee: {json.dumps(employee_components)}, Employer: {json.dumps(employer_components)}")
        
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
        
        logger.debug(f"Recalculated totals - Employee: {bpjs_component.total_employee}, Employer: {bpjs_component.total_employer}, Grand Total: {bpjs_component.grand_total}")
        
        # Update BPJS components for detailed tracking (if the field exists)
        if hasattr(bpjs_component, 'bpjs_components'):
            # Clear existing components if any
            bpjs_component.set('bpjs_components', [])
            logger.debug("Cleared existing detailed components")
            
            # Add JHT Employee component
            if employee_components["jht_employee"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JHT", 
                    "description": "JHT Employee Contribution",
                    "amount": employee_components["jht_employee"]
                })
                logger.debug(f"Added JHT Employee component: {employee_components['jht_employee']}")
                
            # Add JP Employee component
            if employee_components["jp_employee"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JP",
                    "description": "JP Employee Contribution",
                    "amount": employee_components["jp_employee"]
                })
                logger.debug(f"Added JP Employee component: {employee_components['jp_employee']}")
                
            # Add Kesehatan Employee component
            if employee_components["kesehatan_employee"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS Kesehatan",
                    "description": "Kesehatan Employee Contribution",
                    "amount": employee_components["kesehatan_employee"]
                })
                logger.debug(f"Added Kesehatan Employee component: {employee_components['kesehatan_employee']}")
                
            # Add JHT Employer component
            if employer_components["jht_employer"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JHT",
                    "description": "JHT Employer Contribution",
                    "amount": employer_components["jht_employer"]
                })
                logger.debug(f"Added JHT Employer component: {employer_components['jht_employer']}")
                
            # Add JP Employer component
            if employer_components["jp_employer"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JP",
                    "description": "JP Employer Contribution",
                    "amount": employer_components["jp_employer"]
                })
                logger.debug(f"Added JP Employer component: {employer_components['jp_employer']}")
                
            # Add JKK component
            if employer_components["jkk"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JKK",
                    "description": "JKK Employer Contribution",
                    "amount": employer_components["jkk"]
                })
                logger.debug(f"Added JKK component: {employer_components['jkk']}")
                
            # Add JKM component
            if employer_components["jkm"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS JKM",
                    "description": "JKM Employer Contribution",
                    "amount": employer_components["jkm"]
                })
                logger.debug(f"Added JKM component: {employer_components['jkm']}")
                
            # Add Kesehatan Employer component
            if employer_components["kesehatan_employer"] > 0:
                bpjs_component.append("bpjs_components", {
                    "component": "BPJS Kesehatan",
                    "description": "Kesehatan Employer Contribution",
                    "amount": employer_components["kesehatan_employer"]
                })
                logger.debug(f"Added Kesehatan Employer component: {employer_components['kesehatan_employer']}")
        
        # Save the document
        logger.debug("Saving updated BPJS component document")
        bpjs_component.save(ignore_permissions=True)
        logger.info(f"BPJS Payment Component {component_name} updated successfully")
        frappe.msgprint(_("Updated BPJS Payment Component {0}").format(bpjs_component.name))
        
        return bpjs_component.name
        
    except Exception as e:
        logger.error(f"Error in update_bpjs_payment_component: {str(e)}\n{frappe.get_traceback()}")
        frappe.log_error(
            f"Error updating BPJS Payment Component {component_name} for {salary_slip.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Component Update Error"
        )
        frappe.msgprint(_("Error updating BPJS Payment Component: {0}").format(str(e)))
        return None