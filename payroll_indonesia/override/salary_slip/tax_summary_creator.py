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
    """Get a logger instance for Tax Summary module"""
    return frappe.logger("tax_summary_module", with_more_info=True)

def create_tax_summary(doc):
    """Create or update Employee Tax Summary entry"""
    logger = get_logger()
    logger.info(f"Starting Tax Summary creation for salary slip {doc.name} | Employee: {doc.employee} ({doc.employee_name})")
    
    try:
        year = getdate(doc.end_date).year
        month = getdate(doc.end_date).month
        logger.debug(f"Processing for period: Year={year}, Month={month}")
    
        # Get the PPh 21 amount
        logger.debug(f"Getting PPh 21 amount from salary slip {doc.name}")
        pph21_amount = get_component_amount(doc, "PPh 21", "deductions")
        logger.debug(f"PPh 21 amount found: {pph21_amount}")
    
        # Get BPJS components from salary slip
        logger.debug("Calculating BPJS deductions")
        bpjs_deductions = 0
        bpjs_components = ["BPJS JHT Employee", "BPJS JP Employee", "BPJS Kesehatan Employee"]
        bpjs_breakdown = {}
        
        for deduction in doc.deductions:
            if deduction.salary_component in bpjs_components:
                bpjs_deductions += flt(deduction.amount)
                bpjs_breakdown[deduction.salary_component] = flt(deduction.amount)
        
        logger.debug(f"Total BPJS deductions: {bpjs_deductions}")
        logger.debug(f"BPJS breakdown: {json.dumps(bpjs_breakdown)}")
    
        # Check if Employee Tax Summary DocType exists
        logger.debug("Checking if Employee Tax Summary DocType exists")
        if not frappe.db.exists("DocType", "Employee Tax Summary"):
            logger.error("Employee Tax Summary DocType not found")
            frappe.msgprint(_("Employee Tax Summary DocType not found. Cannot create tax summary."))
            return
    
        # Check if we already have a record for this employee/year combination
        logger.debug(f"Looking for existing Tax Summary for employee {doc.employee} and year {year}")
        existing_tax_summary = frappe.db.get_value("Employee Tax Summary", 
            {"employee": doc.employee, "year": year}, "name")
        logger.debug(f"Existing Tax Summary found: {existing_tax_summary or 'None'}")
    
        if existing_tax_summary:
            logger.info(f"Updating existing Tax Summary {existing_tax_summary}")
            update_tax_summary(doc, existing_tax_summary, month, pph21_amount, bpjs_deductions)
        else:
            logger.info(f"Creating new Tax Summary for {doc.employee} - {year}")
            create_new_tax_summary(doc, year, month, pph21_amount, bpjs_deductions)
        
        logger.info(f"Tax Summary processing completed for salary slip {doc.name}")
        
    except Exception as e:
        logger.error(f"Error in create_tax_summary: {str(e)}\n{frappe.get_traceback()}")
        frappe.log_error(
            f"Error processing Tax Summary for {doc.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Tax Summary Error"
        )
        frappe.throw(_("Error processing Tax Summary: {0}").format(str(e)))

def update_tax_summary(doc, existing_tax_summary, month, pph21_amount, bpjs_deductions):
    """Update existing tax summary record"""
    logger = get_logger()
    logger.info(f"Updating existing Tax Summary {existing_tax_summary} for month {month}")
    
    try:
        tax_record = frappe.get_doc("Employee Tax Summary", existing_tax_summary)
        logger.debug(f"Loaded Tax Summary document: {existing_tax_summary}, year={tax_record.year}")
    
        # Check if monthly_details field exists
        if not hasattr(tax_record, 'monthly_details'):
            logger.error("Employee Tax Summary structure is invalid. Missing monthly_details child table.")
            frappe.throw(_("Employee Tax Summary structure is invalid. Missing monthly_details child table."))
    
        # Check for TER (Tax Equalization Rate) attributes
        has_ter_fields = hasattr(tax_record, 'is_using_ter') and hasattr(tax_record, 'ter_rate')
        logger.debug(f"Document has TER fields: {has_ter_fields}")
        
        # Document has TER fields and salary slip has TER info
        ter_enabled = getattr(doc, 'is_using_ter', 0)
        ter_rate = getattr(doc, 'ter_rate', 0)
        logger.debug(f"Salary slip TER info - enabled: {ter_enabled}, rate: {ter_rate}")
    
        # Append monthly detail
        has_month = False
        logger.debug(f"Checking for existing entry for month {month}")
        
        for m in tax_record.monthly_details:
            if hasattr(m, 'month') and m.month == month:
                logger.debug(f"Found existing entry for month {month}, updating values")
                
                old_values = {
                    "gross_pay": m.gross_pay,
                    "bpjs_deductions": m.bpjs_deductions,
                    "tax_amount": m.tax_amount,
                    "is_using_ter": getattr(m, 'is_using_ter', 0),
                    "ter_rate": getattr(m, 'ter_rate', 0)
                }
                logger.debug(f"Old values: {json.dumps(old_values)}")
                
                m.gross_pay = doc.gross_pay
                m.bpjs_deductions = bpjs_deductions
                m.tax_amount = pph21_amount
                m.salary_slip = doc.name
                
                if hasattr(m, 'is_using_ter'):
                    m.is_using_ter = 1 if ter_enabled else 0
                
                if hasattr(m, 'ter_rate'):
                    m.ter_rate = ter_rate
                
                new_values = {
                    "gross_pay": m.gross_pay,
                    "bpjs_deductions": m.bpjs_deductions,
                    "tax_amount": m.tax_amount,
                    "is_using_ter": getattr(m, 'is_using_ter', 0),
                    "ter_rate": getattr(m, 'ter_rate', 0)
                }
                logger.debug(f"New values: {json.dumps(new_values)}")
                
                has_month = True
                break
    
        if not has_month:
            # Create new monthly entry
            logger.debug(f"No existing entry for month {month}, creating new entry")
            
            monthly_data = {
                "month": month,
                "salary_slip": doc.name,
                "gross_pay": doc.gross_pay,
                "bpjs_deductions": bpjs_deductions,
                "tax_amount": pph21_amount
            }
            
            # Add TER info if applicable
            if hasattr(tax_record, 'monthly_details') and tax_record.monthly_details and hasattr(tax_record.monthly_details[0], 'is_using_ter'):
                monthly_data["is_using_ter"] = 1 if ter_enabled else 0
                
            if hasattr(tax_record, 'monthly_details') and tax_record.monthly_details and hasattr(tax_record.monthly_details[0], 'ter_rate'):
                monthly_data["ter_rate"] = ter_rate
            
            logger.debug(f"New monthly data: {json.dumps(monthly_data)}")
        
            # Add to monthly_details
            tax_record.append("monthly_details", monthly_data)
            logger.debug(f"Added new month entry {month} to monthly_details")
    
        # Recalculate YTD tax
        old_ytd_tax = tax_record.ytd_tax
        total_tax = 0
        
        if tax_record.monthly_details:
            logger.debug(f"Recalculating YTD tax from {len(tax_record.monthly_details)} monthly entries")
            for m in tax_record.monthly_details:
                if hasattr(m, 'tax_amount'):
                    total_tax += flt(m.tax_amount)
    
        tax_record.ytd_tax = total_tax
        logger.debug(f"Updated YTD tax: {old_ytd_tax} -> {tax_record.ytd_tax}")
    
        # Set title if empty
        if not tax_record.title:
            tax_record.title = f"{doc.employee_name} - {tax_record.year}"
            logger.debug(f"Set title to: {tax_record.title}")
        
        # Set TER information at year level if applicable
        if has_ter_fields and ter_enabled:
            old_ter_rate = tax_record.ter_rate
            tax_record.is_using_ter = 1
            tax_record.ter_rate = ter_rate
            logger.debug(f"Updated TER rate: {old_ter_rate} -> {tax_record.ter_rate}")
        
        logger.debug("Saving tax record")
        tax_record.save(ignore_permissions=True)
        logger.info(f"Tax Summary {existing_tax_summary} updated successfully")
        
    except Exception as e:
        logger.error(f"Error in update_tax_summary: {str(e)}\n{frappe.get_traceback()}")
        frappe.throw(_("Error updating Tax Summary: {0}").format(str(e)))

def create_new_tax_summary(doc, year, month, pph21_amount, bpjs_deductions):
    """Create a new tax summary record"""
    logger = get_logger()
    logger.info(f"Creating new Tax Summary for employee {doc.employee}, year {year}")
    
    try:
        tax_record = frappe.new_doc("Employee Tax Summary")
        logger.debug(f"Created new Employee Tax Summary document")
    
        # Set basic fields
        tax_record.employee = doc.employee
        tax_record.employee_name = doc.employee_name
        tax_record.year = year
        tax_record.ytd_tax = pph21_amount
        tax_record.title = f"{doc.employee_name} - {year}"
        
        logger.debug(f"Set basic fields - employee: {doc.employee}, year: {year}, ytd_tax: {pph21_amount}")
    
        # Check for TER (Tax Equalization Rate) attributes
        has_ter_fields = hasattr(tax_record, 'is_using_ter') and hasattr(tax_record, 'ter_rate')
        logger.debug(f"Document has TER fields: {has_ter_fields}")
        
        # Document has TER fields and salary slip has TER info
        ter_enabled = getattr(doc, 'is_using_ter', 0)
        ter_rate = getattr(doc, 'ter_rate', 0)
        logger.debug(f"Salary slip TER info - enabled: {ter_enabled}, rate: {ter_rate}")
    
        # Set TER information if applicable and fields exist
        if has_ter_fields and ter_enabled:
            tax_record.is_using_ter = 1
            tax_record.ter_rate = ter_rate
            logger.debug(f"Set document level TER - enabled: 1, rate: {ter_rate}")
    
        # Add monthly detail
        monthly_data = {
            "month": month,
            "salary_slip": doc.name,
            "gross_pay": doc.gross_pay,
            "bpjs_deductions": bpjs_deductions,
            "tax_amount": pph21_amount
        }
        
        # Add TER info to monthly data if applicable
        if hasattr(tax_record, 'monthly_details') and hasattr(tax_record, 'is_using_ter'):
            monthly_data["is_using_ter"] = 1 if ter_enabled else 0
            
        if hasattr(tax_record, 'monthly_details') and hasattr(tax_record, 'ter_rate'):
            monthly_data["ter_rate"] = ter_rate
            
        logger.debug(f"Monthly data for month {month}: {json.dumps(monthly_data)}")
    
        # Add to monthly_details if field exists
        if hasattr(tax_record, 'monthly_details'):
            tax_record.append("monthly_details", monthly_data)
            logger.debug(f"Added month {month} data to monthly_details")
        else:
            logger.error("Employee Tax Summary structure is invalid. Missing monthly_details child table.")
            frappe.throw(_("Employee Tax Summary structure is invalid. Missing monthly_details child table."))
    
        logger.debug("Inserting new tax record")
        tax_record.insert(ignore_permissions=True)
        logger.info(f"New Tax Summary created with name: {tax_record.name}")
        
    except Exception as e:
        logger.error(f"Error in create_new_tax_summary: {str(e)}\n{frappe.get_traceback()}")
        frappe.throw(_("Error creating new Tax Summary: {0}").format(str(e)))