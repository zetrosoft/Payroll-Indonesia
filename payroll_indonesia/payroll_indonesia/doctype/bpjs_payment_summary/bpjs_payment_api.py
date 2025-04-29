# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate
from .bpjs_payment_utils import debug_log
from .bpjs_payment_integration import (
    extract_bpjs_from_salary_slip,
    get_or_create_bpjs_summary,
    add_employee_to_bpjs_summary,
    update_employee_bpjs_details,
    recalculate_bpjs_totals,
    trigger_bpjs_payment_component_creation
)
from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import hitung_bpjs

@frappe.whitelist()
def create_from_salary_slip(doc, method=None):
    """
    Create or update BPJS Payment Summary from a Salary Slip
    Called asynchronously from the Salary Slip's on_submit method
    
    Parameters:
        doc: Salary Slip document or document name
        method: Hook method name (optional, needed for hook compatibility)
    """
    debug_log(f"Starting create_from_salary_slip for {doc}")
    
    try:
        # Handle case when doc is a document name string instead of object
        if isinstance(doc, str):
            salary_slip = doc
            slip = frappe.get_doc("Salary Slip", salary_slip)
        else:
            # When called from hook, doc is the actual document
            salary_slip = doc.name
            slip = doc
            
        if not slip or slip.docstatus != 1:
            debug_log(f"Salary slip {salary_slip} not found or not submitted")
            return None
            
        # Extract BPJS components from salary slip
        bpjs_components = extract_bpjs_from_salary_slip(slip)
        
        # If no BPJS components found, no need to continue
        if not any(bpjs_components["employee"].values()) and not any(bpjs_components["employer"].values()):
            debug_log(f"No BPJS components found in salary slip {salary_slip}")
            return None
        
        # Get the period
        month = getdate(slip.end_date).month
        year = getdate(slip.end_date).year
        
        debug_log(f"Processing BPJS for company={slip.company}, year={year}, month={month}")
        
        # Get or create BPJS Payment Summary for the period
        bpjs_summary = get_or_create_bpjs_summary(slip, month, year)
        
        # Check if employee is already in the summary
        employee_exists = False
        for employee_detail in bpjs_summary.employee_details:
            if employee_detail.employee == slip.employee and employee_detail.salary_slip == salary_slip:
                debug_log(f"Employee {slip.employee} already exists in BPJS Payment Summary {bpjs_summary.name}, updating")
                update_employee_bpjs_details(employee_detail, slip, bpjs_components)
                employee_exists = True
                break
        
        # If employee doesn't exist, add them
        if not employee_exists:
            debug_log(f"Adding employee {slip.employee} to BPJS Payment Summary {bpjs_summary.name}")
            add_employee_to_bpjs_summary(bpjs_summary, slip, bpjs_components)
        
        # Calculate totals
        recalculate_bpjs_totals(bpjs_summary)
        
        # Save the document
        bpjs_summary.flags.ignore_permissions = True
        bpjs_summary.flags.ignore_mandatory = True  # Add this flag to bypass mandatory field validation
        bpjs_summary.save()
        debug_log(f"Successfully saved BPJS Payment Summary: {bpjs_summary.name}")
        
        # Create BPJS Payment Component if setting is enabled
        trigger_bpjs_payment_component_creation(salary_slip, bpjs_summary.name)
        
        return bpjs_summary.name
        
    except Exception as e:
        debug_log(f"Error in create_from_salary_slip: {str(e)}\nTraceback: {frappe.get_traceback()}")
        frappe.log_error(
            f"Error creating BPJS Payment Summary from {doc if isinstance(doc, str) else doc.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Payment Summary Error"
        )
        return None

@frappe.whitelist()
def update_on_salary_slip_cancel(doc, method=None):
    """
    Update BPJS Payment Summary when a Salary Slip is cancelled
    Called asynchronously from the Salary Slip's on_cancel method
    
    Parameters:
        doc: Salary Slip document or document name
        method: Hook method name (optional, needed for hook compatibility)
    """
    debug_log(f"Starting update_on_salary_slip_cancel for {doc}")
    
    try:
        # Handle case when doc is a document name string instead of object
        if isinstance(doc, str):
            salary_slip = doc
            slip = frappe.get_doc("Salary Slip", salary_slip)
        else:
            # When called from hook, doc is the actual document
            salary_slip = doc.name
            slip = doc
            
        if not slip:
            debug_log(f"Salary slip {salary_slip} not found")
            return False
            
        # Get month and year from slip
        month = getdate(slip.end_date).month
        year = getdate(slip.end_date).year
            
        # Find the BPJS Payment Summary
        bpjs_summary_name = get_summary_for_period(slip.company, month, year)
        
        if not bpjs_summary_name:
            debug_log(f"No BPJS Payment Summary found for company={slip.company}, month={month}, year={year}")
            return False
            
        # Get the document
        bpjs_doc = frappe.get_doc("BPJS Payment Summary", bpjs_summary_name)
        
        # Check if already submitted
        if bpjs_doc.docstatus > 0:
            debug_log(f"BPJS Payment Summary {bpjs_summary_name} already submitted, cannot update")
            frappe.msgprint(_("BPJS Payment Summary {0} sudah disubmit dan tidak dapat diperbarui.").format(bpjs_summary_name))
            return False
            
        # Find and remove the employee entry
        to_remove = []
        for i, d in enumerate(bpjs_doc.employee_details):
            if getattr(d, "salary_slip") == salary_slip:
                debug_log(f"Found entry to remove: employee_details[{i}] with salary_slip={salary_slip}")
                to_remove.append(d)
                
        # If entries found, remove them and save
        if to_remove:
            debug_log(f"Found {len(to_remove)} entries to remove from BPJS Payment Summary {bpjs_summary_name}")
            
            for d in to_remove:
                bpjs_doc.employee_details.remove(d)
                
            # Recalculate totals
            recalculate_bpjs_totals(bpjs_doc)
            
            # Save the document
            bpjs_doc.flags.ignore_permissions = True
            bpjs_doc.flags.ignore_mandatory = True  # Add this flag to bypass mandatory field validation
            bpjs_doc.save()
            debug_log(f"Successfully updated BPJS Payment Summary: {bpjs_summary_name}")
            
            return True
        else:
            debug_log(f"No entries found for salary_slip={salary_slip} in BPJS Payment Summary {bpjs_summary_name}")
            return False
            
    except Exception as e:
        debug_log(f"Error in update_on_salary_slip_cancel: {str(e)}\nTraceback: {frappe.get_traceback()}")
        frappe.log_error(
            f"Error updating BPJS Payment Summary on cancel for {doc if isinstance(doc, str) else doc.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Payment Summary Cancel Error"
        )
        return False
    
@frappe.whitelist()
def get_summary_for_period(company, month, year):
    """
    Get BPJS Payment Summary for a specific period
    Returns the name of an existing BPJS Payment Summary or None if not found
    """
    try:
        bpjs_summary_name = frappe.db.get_value(
            "BPJS Payment Summary",
            {"company": company, "year": year, "month": month, "docstatus": ["!=", 2]},
            "name"
        )
        
        return bpjs_summary_name
    except Exception as e:
        frappe.log_error(
            f"Error in get_summary_for_period: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Summary Period Error"
        )
        return None

@frappe.whitelist()
def get_employee_bpjs_details(employee, company=None):
    """
    Get BPJS details for a specific employee
    Returns a dict with the employee's BPJS information
    """
    try:
        # Get the employee document
        employee_doc = frappe.get_doc("Employee", employee)
        if not employee_doc:
            return None
            
        # Initialize result dict with employee info
        result = {
            "employee": employee,
            "employee_name": employee_doc.employee_name,
            "department": getattr(employee_doc, "department", ""),
            "designation": getattr(employee_doc, "designation", ""),
            "bpjs_number": getattr(employee_doc, "bpjs_number", ""),
            "nik": getattr(employee_doc, "ktp", ""),
            "jht_employee": 0,
            "jp_employee": 0,
            "kesehatan_employee": 0,
            "jht_employer": 0,
            "jp_employer": 0,
            "jkk": 0,
            "jkm": 0,
            "kesehatan_employer": 0
        }
        
        # If company is provided, calculate BPJS using centralized function
        if company:
            # Try to get salary structure assignment
            salary_structure = frappe.db.get_value(
                "Salary Structure Assignment",
                {"employee": employee, "docstatus": 1},
                ["salary_structure", "base"],
                order_by="from_date desc"
            )
            
            if salary_structure:
                _, base_salary = salary_structure
                
                # Use the centralized BPJS calculation function
                bpjs_amounts = hitung_bpjs(employee, base_salary)
                
                # Map the calculated values to our result
                result["jht_employee"] = bpjs_amounts["jht_employee"]
                result["jp_employee"] = bpjs_amounts["jp_employee"]
                result["kesehatan_employee"] = bpjs_amounts["kesehatan_employee"]
                result["jht_employer"] = bpjs_amounts["jht_employer"]
                result["jp_employer"] = bpjs_amounts["jp_employer"]
                result["jkk"] = bpjs_amounts["jkk_employer"]
                result["jkm"] = bpjs_amounts["jkm_employer"]
                result["kesehatan_employer"] = bpjs_amounts["kesehatan_employer"]
        
        # Try to get the latest values from existing BPJS Payment Summary records
        latest_bpjs_record = frappe.db.sql("""
            SELECT 
                ed.jht_employee, ed.jp_employee, ed.kesehatan_employee,
                ed.jht_employer, ed.jp_employer, ed.kesehatan_employer,
                ed.jkk, ed.jkm
            FROM 
                `tabBPJS Payment Summary Employee` ed
            JOIN 
                `tabBPJS Payment Summary` bps ON ed.parent = bps.name
            WHERE 
                ed.employee = %s
                AND bps.docstatus != 2
            ORDER BY 
                bps.year DESC, bps.month DESC
            LIMIT 1
        """, employee, as_dict=1)
        
        if latest_bpjs_record and len(latest_bpjs_record) > 0:
            # Update with latest values if they exist and are > 0
            record = latest_bpjs_record[0]
            for key in ["jht_employee", "jp_employee", "kesehatan_employee",
                       "jht_employer", "jp_employer", "kesehatan_employer",
                       "jkk", "jkm"]:
                if key in record and record[key] is not None and record[key] > 0:
                    result[key] = record[key]
        
        return result
        
    except Exception as e:
        frappe.log_error(
            f"Error in get_employee_bpjs_details: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Employee Details Error"
        )
        return None

@frappe.whitelist()
def create_payment_entry(bpjs_summary):
    """
    Create a Payment Entry for a BPJS Payment Summary
    Returns the name of the created Payment Entry or None if it fails
    """
    try:
        # Get the BPJS Payment Summary document
        bpjs_doc = frappe.get_doc("BPJS Payment Summary", bpjs_summary)
        if not bpjs_doc:
            frappe.throw(_("BPJS Payment Summary not found"))
            
        # Use the document's generate_payment_entry method
        payment_entry_name = bpjs_doc.generate_payment_entry()
        
        # Return the payment entry name
        return payment_entry_name
    except Exception as e:
        frappe.log_error(
            f"Error in create_payment_entry for {bpjs_summary}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Payment Entry Creation Error"
        )
        # Re-throw the error to show to the user
        frappe.msgprint(_("Error creating payment entry: {0}").format(str(e)), indicator="red")
        return None