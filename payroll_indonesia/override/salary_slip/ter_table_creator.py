# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 07:54:38 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate, now
import json

from .base import get_component_amount

# Setup debugging logger
def get_logger():
    """Get a logger instance for PPh TER Table module"""
    return frappe.logger("pph_ter_module", with_more_info=True)

def create_pph_ter_table(doc):
    """Create or update PPh TER Table entry if using TER method"""
    logger = get_logger()
    logger.info(f"Starting PPh TER Table creation for salary slip {doc.name} | Employee: {doc.employee} ({doc.employee_name})")
    
    try:
        # Only proceed if using TER
        is_using_ter = getattr(doc, 'is_using_ter', 0)
        logger.debug(f"Checking TER eligibility - is_using_ter: {is_using_ter}")
        
        if not is_using_ter:
            logger.info(f"Skipping PPh TER Table creation, is_using_ter=0 for salary slip {doc.name}")
            return
        
        # Check if PPh TER Table DocType exists
        logger.debug("Checking if PPh TER Table DocType exists")
        if not frappe.db.exists("DocType", "PPh TER Table"):
            logger.error("PPh TER Table DocType not found")
            frappe.msgprint(_("PPh TER Table DocType not found. Cannot create TER entry."))
            return
    
        # Determine year and month from salary slip
        end_date = getdate(doc.end_date)
        month = end_date.month
        year = end_date.year
        logger.debug(f"Processing for period: Year={year}, Month={month}")
    
        # Get PPh 21 amount
        logger.debug(f"Getting PPh 21 amount from salary slip {doc.name}")
        pph21_amount = get_component_amount(doc, "PPh 21", "deductions")
        logger.debug(f"PPh 21 amount found: {pph21_amount}")
    
        # Get employee data
        logger.debug(f"Getting additional employee data for {doc.employee}")
        employee_data = get_employee_data(doc)
        logger.debug(f"Employee data retrieved: {json.dumps(employee_data)}")
    
        # Check if PPh TER Table exists for this period
        logger.debug(f"Looking for existing PPh TER Table for {year}-{month}")
        ter_table = find_existing_ter_table(doc, year, month)
        logger.debug(f"Existing PPh TER Table found: {ter_table or 'None'}")
    
        if not ter_table:
            logger.info(f"Creating new PPh TER Table for {year}-{month}")
            create_new_ter_table(doc, year, month, pph21_amount, employee_data)
        else:
            logger.info(f"Updating existing PPh TER Table {ter_table}")
            update_existing_ter_table(doc, ter_table, pph21_amount, employee_data)
            
        logger.info(f"PPh TER Table processing completed for salary slip {doc.name}")
        
    except Exception as e:
        logger.error(f"Error in create_pph_ter_table: {str(e)}\n{frappe.get_traceback()}")
        frappe.log_error(
            f"Error processing PPh TER Table for {doc.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "PPh TER Table Error"
        )
        frappe.throw(_("Error processing PPh TER Table: {0}").format(str(e)))

def get_employee_data(doc):
    """Get employee tax data"""
    logger = get_logger()
    logger.debug(f"Retrieving employee tax data for employee {doc.employee}")
    
    try:
        logger.debug(f"Fetching Employee document for {doc.employee}")
        employee = frappe.get_doc("Employee", doc.employee)
        
        # Get status pajak with fallback
        status_pajak = "TK0"  # Default
        if hasattr(employee, 'status_pajak') and employee.status_pajak:
            status_pajak = employee.status_pajak
            logger.debug(f"Found status_pajak: {status_pajak}")
        else:
            logger.debug("status_pajak not found or empty, using default TK0")
            
        # Get NPWP with fallback
        npwp = ""
        if hasattr(employee, 'npwp'):
            npwp = employee.npwp
            logger.debug(f"Found NPWP: {npwp or 'Empty'}")
        else:
            logger.debug("NPWP field not found")
            
        # Get KTP with fallback  
        ktp = ""
        if hasattr(employee, 'ktp'):
            ktp = employee.ktp
            logger.debug(f"Found KTP: {ktp or 'Empty'}")
        else:
            logger.debug("KTP field not found")
            
        employee_data = {
            "status_pajak": status_pajak,
            "npwp": npwp,
            "ktp": ktp
        }
        logger.debug(f"Compiled employee data: {json.dumps(employee_data)}")
        return employee_data
        
    except Exception as e:
        logger.error(f"Error in get_employee_data: {str(e)}\n{frappe.get_traceback()}")
        frappe.log_error(
            f"Error getting employee data for {doc.employee}: {str(e)}",
            "Employee Data Error"
        )
        logger.warning(f"Using fallback values for employee data due to error")
        return {"status_pajak": "TK0", "npwp": "", "ktp": ""}

def find_existing_ter_table(doc, year, month):
    """Find existing TER table for this period"""
    logger = get_logger()
    logger.debug(f"Looking for existing PPh TER Table for {year}-{month}")
    
    try:
        # Check column structure first
        logger.debug("Validating PPh TER Table DocType structure")
        doctype_meta = frappe.get_meta("PPh TER Table")
        if not (doctype_meta.has_field("year") and doctype_meta.has_field("month")):
            logger.error("PPh TER Table DocType missing required fields 'year' and/or 'month'")
            frappe.throw(_("PPh TER Table DocType missing required fields 'year' and/or 'month'"))
        
        logger.debug(f"Querying database for PPh TER Table - company: {doc.company}, year: {year}, month: {month}")
        ter_table = frappe.db.get_value(
            "PPh TER Table",
            {"company": doc.company, "year": year, "month": month, "docstatus": ["!=", 2]},
            "name"
        )
        
        logger.debug(f"PPh TER Table search result: {ter_table or 'Not found'}")
        return ter_table
        
    except Exception as e:
        logger.error(f"Error in find_existing_ter_table: {str(e)}\n{frappe.get_traceback()}")
        if "Unknown column" in str(e):
            frappe.throw(_(
                "Database structure issue: {0} - Please run 'bench migrate' "
                "or fix the PPh TER Table DocType structure."
            ).format(str(e)))
        else:
            frappe.throw(_("Error querying PPh TER Table: {0}").format(str(e)))

def create_new_ter_table(doc, year, month, pph21_amount, employee_data):
    """Create a new PPh TER Table"""
    logger = get_logger()
    logger.info(f"Creating new PPh TER Table for {year}-{month}")
    
    try:
        ter_table_doc = frappe.new_doc("PPh TER Table")
        ter_table_doc.company = doc.company
        ter_table_doc.year = year
        ter_table_doc.month = month
        
        logger.debug(f"Created new PPh TER Table document: company={doc.company}, year={year}, month={month}")
        
        # Set period if field exists
        if hasattr(ter_table_doc, 'period'):
            month_names = ['January', 'February', 'March', 'April', 'May', 'June', 
                         'July', 'August', 'September', 'October', 'November', 'December']
            if month >= 1 and month <= 12:
                ter_table_doc.period = month_names[month-1]
                logger.debug(f"Set period to {ter_table_doc.period}")
    
        # Set title if field exists
        if hasattr(ter_table_doc, 'month_year_title'):
            month_names = ['January', 'February', 'March', 'April', 'May', 'June', 
                         'July', 'August', 'September', 'October', 'November', 'December']
            
            month_year_title = f"{month_names[month-1]} {year}" if month >= 1 and month <= 12 else f"{month}-{year}"
            ter_table_doc.month_year_title = month_year_title
            logger.debug(f"Set month_year_title to {month_year_title}")
    
        # Check if details field exists
        if not hasattr(ter_table_doc, 'details'):
            logger.error("PPh TER Table structure is invalid. Missing details child table.")
            frappe.throw(_("PPh TER Table structure is invalid. Missing details child table."))
    
        # Create first employee detail
        logger.debug(f"Adding employee {doc.employee} to PPh TER Table")
        add_employee_to_ter_table(ter_table_doc, doc, pph21_amount, employee_data)
    
        logger.debug("Inserting PPh TER Table document")
        ter_table_doc.insert(ignore_permissions=True)
        logger.info(f"PPh TER Table document created with name: {ter_table_doc.name}")
        
    except Exception as e:
        logger.error(f"Error in create_new_ter_table: {str(e)}\n{frappe.get_traceback()}")
        frappe.throw(_("Error creating PPh TER Table: {0}").format(str(e)))

def update_existing_ter_table(doc, ter_table_name, pph21_amount, employee_data):
    """Update existing PPh TER Table"""
    logger = get_logger()
    logger.info(f"Updating existing PPh TER Table {ter_table_name}")
    
    try:
        ter_table_doc = frappe.get_doc("PPh TER Table", ter_table_name)
        logger.debug(f"Loaded PPh TER Table document: {ter_table_name}")
    
        # Check if details field exists
        if not hasattr(ter_table_doc, 'details'):
            logger.error("PPh TER Table structure is invalid. Missing details child table.")
            frappe.throw(_("PPh TER Table structure is invalid. Missing details child table."))
    
        # Check if employee already exists
        employee_exists = False
        logger.debug(f"Checking if employee {doc.employee} already exists in PPh TER Table")
        
        for detail in ter_table_doc.details:
            if detail.employee == doc.employee:
                # Update existing employee
                logger.debug(f"Found existing entry for employee {doc.employee}, updating details")
                update_ter_table_detail(detail, doc, pph21_amount, employee_data)
                employee_exists = True
                break
    
        if not employee_exists:
            # Add new employee
            logger.debug(f"Adding new employee {doc.employee} to existing PPh TER Table")
            add_employee_to_ter_table(ter_table_doc, doc, pph21_amount, employee_data)
    
        # Save changes
        logger.debug("Saving updated PPh TER Table document")
        ter_table_doc.save(ignore_permissions=True)
        logger.info(f"PPh TER Table {ter_table_name} updated successfully")
        
    except Exception as e:
        logger.error(f"Error in update_existing_ter_table: {str(e)}\n{frappe.get_traceback()}")
        frappe.throw(_("Error updating PPh TER Table: {0}").format(str(e)))

def add_employee_to_ter_table(ter_doc, salary_slip, pph21_amount, employee_data):
    """Add employee details to TER Table document"""
    logger = get_logger()
    logger.debug(f"Adding employee {salary_slip.employee} to PPh TER Table")
    
    try:
        # Get derived values with fallbacks
        biaya_jabatan = getattr(salary_slip, 'biaya_jabatan', 0)
        netto = getattr(salary_slip, 'netto', salary_slip.gross_pay)
        
        logger.debug(f"Derived values - biaya_jabatan: {biaya_jabatan}, netto: {netto}")
        
        employee_detail = {
            "employee": salary_slip.employee,
            "employee_name": salary_slip.employee_name,
            "npwp": employee_data["npwp"],
            "ktp": employee_data["ktp"],
            "biaya_jabatan": biaya_jabatan,
            "penghasilan_bruto": salary_slip.gross_pay,
            "penghasilan_netto": netto,
            "penghasilan_kena_pajak": netto,
            "amount": pph21_amount
        }
        
        logger.debug(f"Employee detail data: {json.dumps(employee_detail)}")
        ter_doc.append("details", employee_detail)
        logger.debug(f"Successfully added employee {salary_slip.employee} to PPh TER Table details")
        
    except Exception as e:
        logger.error(f"Error in add_employee_to_ter_table: {str(e)}")
        raise

def update_ter_table_detail(detail, salary_slip, pph21_amount, employee_data):
    """Update TER table detail for an existing employee"""
    logger = get_logger()
    logger.debug(f"Updating details for employee {salary_slip.employee} in PPh TER Table")
    
    try:
        # Store old values for debugging
        old_values = {
            "npwp": detail.npwp,
            "ktp": detail.ktp,
            "biaya_jabatan": detail.biaya_jabatan,
            "penghasilan_bruto": detail.penghasilan_bruto,
            "penghasilan_netto": detail.penghasilan_netto,
            "penghasilan_kena_pajak": detail.penghasilan_kena_pajak,
            "amount": detail.amount
        }
        logger.debug(f"Old values: {json.dumps(old_values)}")
        
        # Get derived values with fallbacks
        biaya_jabatan = getattr(salary_slip, 'biaya_jabatan', 0)
        netto = getattr(salary_slip, 'netto', salary_slip.gross_pay)
        
        # Update values
        detail.npwp = employee_data["npwp"]
        detail.ktp = employee_data["ktp"]
        detail.biaya_jabatan = biaya_jabatan
        detail.penghasilan_bruto = salary_slip.gross_pay
        detail.penghasilan_netto = netto
        detail.penghasilan_kena_pajak = netto
        detail.amount = pph21_amount
        
        # Log new values
        new_values = {
            "npwp": detail.npwp,
            "ktp": detail.ktp,
            "biaya_jabatan": detail.biaya_jabatan,
            "penghasilan_bruto": detail.penghasilan_bruto,
            "penghasilan_netto": detail.penghasilan_netto,
            "penghasilan_kena_pajak": detail.penghasilan_kena_pajak,
            "amount": detail.amount
        }
        logger.debug(f"New values: {json.dumps(new_values)}")
        logger.debug(f"Successfully updated employee {salary_slip.employee} details in PPh TER Table")
        
    except Exception as e:
        logger.error(f"Error in update_ter_table_detail: {str(e)}")
        raise

# Add a debug helper function to log the execution context
def log_execution_context():
    """Log the current execution context for debugging purposes"""
    logger = get_logger()
    try:
        # Get current user
        user = frappe.session.user
        
        # Get current timestamp
        timestamp = now()
        
        # Get system info if available
        system_info = {}
        try:
            system_settings = frappe.get_single("System Settings")
            system_info = {
                "time_zone": system_settings.time_zone if hasattr(system_settings, "time_zone") else "Unknown",
                "date_format": system_settings.date_format if hasattr(system_settings, "date_format") else "Unknown",
                "db_name": frappe.conf.get("db_name", "Unknown")
            }
        except:
            pass
            
        logger.debug(f"Execution context - User: {user}, Time: {timestamp}, System: {json.dumps(system_info)}")
        return True
        
    except Exception as e:
        logger.error(f"Error logging execution context: {str(e)}")
        return False