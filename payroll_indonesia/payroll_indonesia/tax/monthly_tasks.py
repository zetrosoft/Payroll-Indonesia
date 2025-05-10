# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-10 14:30:00 by dannyaudian

import frappe
from frappe import _
from frappe.utils import getdate, get_first_day, get_last_day, add_months, add_days, flt, today
from datetime import datetime

# Import TER functions for consistency
from payroll_indonesia.override.salary_slip.ter_calculator import map_ptkp_to_ter_category

def update_tax_summaries(month=None, year=None, company=None):
    """
    Update employee tax summaries at the end of each month with improved implementation
    
    This function is meant to be called by a scheduled job,
    or can be manually triggered to update all employee tax
    summaries for the current or previous month
    
    Args:
        month (int, optional): Month to process (1-12). Defaults to previous month.
        year (int, optional): Year to process. Defaults to current year.
        company (str, optional): Company to process. If not provided, all companies are processed.
        
    Returns:
        dict: Summary of updated summaries
    """
    try:
        # Validate parameters
        current_date = getdate(today())
        
        if not month:
            # Default to previous month
            if current_date.month == 1:
                month = 12
                year = current_date.year - 1 if not year else year
            else:
                month = current_date.month - 1
                year = current_date.year if not year else year
        
        if not year:
            year = current_date.year
            
        # Validate month and year
        if not isinstance(month, int) or month < 1 or month > 12:
            frappe.throw(_("Invalid month: {0}. Must be between 1 and 12").format(month))
            
        if not isinstance(year, int) or year < 2000 or year > current_date.year + 1:
            frappe.throw(_("Invalid year: {0}. Must be between 2000 and {1}").format(
                year, current_date.year + 1
            ))
            
        # Check if company exists if provided
        if company and not frappe.db.exists("Company", company):
            frappe.throw(_("Company {0} not found").format(company))
            
        # Calculate date range for the month
        start_date = get_first_day(datetime(year, month, 1))
        end_date = get_last_day(datetime(year, month, 1))
        
        # Log the update
        frappe.logger().info(
            f"Tax summary update started for {month:02d}-{year}, "
            f"range: {start_date} to {end_date}, "
            f"company: {company or 'All'}"
        )
        
        # Statistics
        summary = {
            "period": f"{month:02d}-{year}",
            "company": company or "All Companies",
            "total_employees": 0,
            "updated": 0,
            "created": 0,
            "errors": 0,
            "details": []
        }
        
        # Get all submitted salary slips in the specified month
        salary_slips_filters = {
            "start_date": [">=", start_date],
            "end_date": ["<=", end_date],
            "docstatus": 1
        }
        
        if company:
            salary_slips_filters["company"] = company
            
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters=salary_slips_filters,
            fields=["name", "employee", "employee_name", "company", "gross_pay", "start_date"]
        )
        
        if not salary_slips:
            frappe.msgprint(_("No approved salary slips found for {0}-{1}").format(month, year))
            return summary
            
        # Get unique employees
        employees = {}
        for slip in salary_slips:
            if slip.employee not in employees:
                employees[slip.employee] = {
                    "name": slip.employee,
                    "employee_name": slip.employee_name,
                    "company": slip.company,
                    "slips": []
                }
            employees[slip.employee]["slips"].append(slip.name)
            
        summary["total_employees"] = len(employees)
        
        # Process each employee
        for emp_id, emp_data in employees.items():
            try:
                # Check if Employee Tax Summary DocType exists
                if not frappe.db.exists("DocType", "Employee Tax Summary"):
                    frappe.throw(_("Employee Tax Summary DocType not found. Cannot update tax information."))
                
                # Check if employee tax summary already exists for this year
                existing_summary = frappe.db.get_value(
                    "Employee Tax Summary",
                    {"employee": emp_id, "year": year},
                    "name"
                )
                
                if existing_summary:
                    # Update existing summary
                    result = update_existing_summary(existing_summary, emp_id, month, year, emp_data["slips"])
                    
                    if result:
                        summary["updated"] += 1
                        summary["details"].append({
                            "employee": emp_id,
                            "employee_name": emp_data["employee_name"],
                            "status": "Updated",
                            "message": f"Updated with {len(emp_data['slips'])} slips"
                        })
                else:
                    # Create new summary
                    result = create_new_summary(emp_id, emp_data["employee_name"], year, month, emp_data["slips"])
                    
                    if result:
                        summary["created"] += 1
                        summary["details"].append({
                            "employee": emp_id,
                            "employee_name": emp_data["employee_name"],
                            "status": "Created",
                            "message": f"Created with {len(emp_data['slips'])} slips"
                        })
                        
            except Exception as e:
                frappe.log_error(
                    f"Error updating tax summary for employee {emp_id}: {str(e)}",
                    "Monthly Tax Update Error"
                )
                summary["errors"] += 1
                summary["details"].append({
                    "employee": emp_id,
                    "employee_name": emp_data["employee_name"],
                    "status": "Error",
                    "message": str(e)[:100]
                })
                continue
        
        # Log summary
        log_message = (
            f"Tax summary update completed for {month:02d}-{year}. "
            f"Updated: {summary['updated']}, Created: {summary['created']}, "
            f"Errors: {summary['errors']}, Total: {summary['total_employees']}"
        )
        
        if summary["errors"] > 0:
            frappe.log_error(log_message, "Monthly Tax Update Summary")
        else:
            frappe.logger().info(log_message)
            
        frappe.msgprint(log_message)
        return summary
        
    except Exception as e:
        frappe.log_error(
            f"Error updating tax summaries: {str(e)}",
            "Monthly Tax Update Error"
        )
        frappe.throw(_("Error updating tax summaries: {0}").format(str(e)))

def update_existing_summary(summary_name, employee, month, year, slip_names):
    """
    Update an existing tax summary for an employee
    
    Args:
        summary_name (str): Name of the existing tax summary document
        employee (str): Employee ID
        month (int): Month to update (1-12)
        year (int): Year to update
        slip_names (list): List of salary slip names to include
        
    Returns:
        bool: True if update was successful
    """
    try:
        # Get the summary document
        summary = frappe.get_doc("Employee Tax Summary", summary_name)
        
        # Validate fields exist
        if not hasattr(summary, 'monthly_details'):
            frappe.throw(_("Employee Tax Summary structure is invalid: missing monthly_details child table"))
        
        # Check if month already exists in monthly_details
        month_exists = False
        for detail in summary.monthly_details:
            if hasattr(detail, 'month') and detail.month == month:
                month_exists = True
                break
                
        # If month exists, we need to remove it first to avoid duplicates
        if month_exists:
            summary.monthly_details = [d for d in summary.monthly_details if d.month != month]
                
        # Calculate monthly totals from salary slips
        monthly_data = calculate_monthly_totals(slip_names)
        
        # Add new monthly detail
        if monthly_data:
            monthly_detail = {
                "month": month,
                "gross_pay": monthly_data["gross_pay"],
                "bpjs_deductions": monthly_data["bpjs_deductions"],
                "tax_amount": monthly_data["tax_amount"],
                "salary_slip": monthly_data["latest_slip"],
                "is_using_ter": 1 if monthly_data["is_using_ter"] else 0,
                "ter_rate": monthly_data["ter_rate"]
            }
            
            # Add TER category if available
            if monthly_data["ter_category"] and hasattr(summary, 'ter_category'):
                monthly_detail["ter_category"] = monthly_data["ter_category"]
                
            summary.append("monthly_details", monthly_detail)
            
            # Add TER information if applicable
            if monthly_data["is_using_ter"]:
                if hasattr(summary, 'is_using_ter'):
                    summary.is_using_ter = 1
                    
                # Only set ter_rate if it exists and we have a valid rate
                if hasattr(summary, 'ter_rate') and monthly_data["ter_rate"] > 0:
                    summary.ter_rate = monthly_data["ter_rate"]
                    
                # Set TER category if available
                if hasattr(summary, 'ter_category') and monthly_data["ter_category"]:
                    summary.ter_category = monthly_data["ter_category"]
            
        # Recalculate YTD tax
        total_tax = 0
        for detail in summary.monthly_details:
            if hasattr(detail, 'tax_amount'):
                total_tax += flt(detail.tax_amount)
                
        if hasattr(summary, 'ytd_tax'):
            summary.ytd_tax = total_tax
            
        # Save the summary
        summary.flags.ignore_validate_update_after_submit = True
        summary.save(ignore_permissions=True)
        
        return True
        
    except Exception as e:
        frappe.log_error(
            f"Error updating tax summary {summary_name} for employee {employee}: {str(e)}",
            "Summary Update Error"
        )
        raise
        
def create_new_summary(employee, employee_name, year, month, slip_names):
    """
    Create a new tax summary for an employee
    
    Args:
        employee (str): Employee ID
        employee_name (str): Employee name
        year (int): Year for the summary
        month (int): Current month being processed (1-12)
        slip_names (list): List of salary slip names to include
        
    Returns:
        str: Name of the created summary document
    """
    try:
        # Calculate monthly totals from salary slips
        monthly_data = calculate_monthly_totals(slip_names)
        
        if not monthly_data:
            frappe.msgprint(_("No valid salary data found for employee {0} in {1}-{2}").format(
                employee, month, year
            ))
            return None
            
        # Create new summary
        summary = frappe.new_doc("Employee Tax Summary")
        summary.employee = employee
        summary.employee_name = employee_name
        summary.year = year
        
        # Set title
        if hasattr(summary, 'title'):
            summary.title = f"{employee_name} - {year}"
            
        # Set initial tax amount
        if hasattr(summary, 'ytd_tax'):
            summary.ytd_tax = monthly_data["tax_amount"]
            
        # Set TER information
        if monthly_data["is_using_ter"]:
            if hasattr(summary, 'is_using_ter'):
                summary.is_using_ter = 1
                
            if hasattr(summary, 'ter_rate') and monthly_data["ter_rate"] > 0:
                summary.ter_rate = monthly_data["ter_rate"]
                
            # Set TER category if available
            if hasattr(summary, 'ter_category') and monthly_data["ter_category"]:
                summary.ter_category = monthly_data["ter_category"]
                
        # Add first monthly detail
        if hasattr(summary, 'monthly_details'):
            monthly_detail = {
                "month": month,
                "salary_slip": monthly_data["latest_slip"],
                "gross_pay": monthly_data["gross_pay"],
                "bpjs_deductions": monthly_data["bpjs_deductions"],
                "tax_amount": monthly_data["tax_amount"],
                "is_using_ter": 1 if monthly_data["is_using_ter"] else 0,
                "ter_rate": monthly_data["ter_rate"]
            }
            
            # Add TER category if available
            if monthly_data["ter_category"]:
                monthly_detail["ter_category"] = monthly_data["ter_category"]
                
            summary.append("monthly_details", monthly_detail)
        else:
            frappe.throw(_("Employee Tax Summary structure is invalid: missing monthly_details child table"))
            
        # Insert the document
        summary.insert(ignore_permissions=True)
        
        return summary.name
        
    except Exception as e:
        frappe.log_error(
            f"Error creating tax summary for {employee} ({employee_name}): {str(e)}",
            "Summary Creation Error"
        )
        raise

def calculate_monthly_totals(slip_names):
    """
    Calculate monthly totals from a list of salary slips with PMK 168/2023 support
    
    Args:
        slip_names (list): List of salary slip names
        
    Returns:
        dict: Monthly totals
    """
    try:
        if not slip_names:
            return None
            
        result = {
            "gross_pay": 0,
            "bpjs_deductions": 0,
            "tax_amount": 0,
            "is_using_ter": False,
            "ter_rate": 0,
            "ter_category": "",
            "latest_slip": slip_names[0]  # Default to first slip
        }
        
        # Track which TER category to use (preferring explicit ones)
        ter_categories_found = []
        
        for slip_name in slip_names:
            try:
                slip = frappe.get_doc("Salary Slip", slip_name)
                
                # Add gross pay
                if hasattr(slip, 'gross_pay'):
                    result["gross_pay"] += flt(slip.gross_pay)
                    
                # Check for TER usage
                if hasattr(slip, 'is_using_ter') and slip.is_using_ter:
                    result["is_using_ter"] = True
                    
                    if hasattr(slip, 'ter_rate') and slip.ter_rate > result["ter_rate"]:
                        result["ter_rate"] = slip.ter_rate
                        
                    # Get TER category if available - PMK 168/2023
                    if hasattr(slip, 'ter_category') and slip.ter_category:
                        ter_categories_found.append(slip.ter_category)
                    
                # Get BPJS components
                if hasattr(slip, 'deductions'):
                    for deduction in slip.deductions:
                        if deduction.salary_component in [
                            "BPJS JHT Employee", 
                            "BPJS JP Employee", 
                            "BPJS Kesehatan Employee"
                        ]:
                            result["bpjs_deductions"] += flt(deduction.amount)
                            
                        # Get PPh 21
                        if deduction.salary_component == "PPh 21":
                            result["tax_amount"] += flt(deduction.amount)
                
                # Update latest slip based on posting date
                if hasattr(slip, 'posting_date'):
                    current_latest = frappe.get_doc("Salary Slip", result["latest_slip"])
                    if not hasattr(current_latest, 'posting_date') or getdate(slip.posting_date) > getdate(current_latest.posting_date):
                        result["latest_slip"] = slip_name
                
            except Exception as e:
                frappe.log_error(
                    f"Error processing salary slip {slip_name}: {str(e)}",
                    "Slip Processing Error"
                )
                continue
        
        # If TER is being used but no category was found, try to determine it from employee status
        if result["is_using_ter"] and not ter_categories_found:
            try:
                # Get latest slip doc
                latest_slip = frappe.get_doc("Salary Slip", result["latest_slip"])
                if hasattr(latest_slip, 'employee') and latest_slip.employee:
                    emp_doc = frappe.get_doc("Employee", latest_slip.employee)
                    if hasattr(emp_doc, 'status_pajak') and emp_doc.status_pajak:
                        result["ter_category"] = map_ptkp_to_ter_category(emp_doc.status_pajak)
            except Exception:
                pass
        elif ter_categories_found:
            # Use the most common category (or first if tied)
            from collections import Counter
            category_counts = Counter(ter_categories_found)
            result["ter_category"] = category_counts.most_common(1)[0][0]
        
        return result
        
    except Exception as e:
        frappe.log_error(
            f"Error calculating monthly totals: {str(e)}",
            "Monthly Totals Error"
        )
        raise

def validate_monthly_entries():
    """
    Validate monthly entries in tax summaries and fix any inconsistencies
    
    This function is meant to be run periodically to ensure that all
    employee tax summaries are accurate and complete
    
    Returns:
        dict: Summary of validation results
    """
    try:
        # Get current year
        current_year = datetime.now().year
        
        # Statistics
        summary = {
            "year": current_year,
            "total_summaries": 0,
            "validated": 0,
            "fixed": 0,
            "errors": 0,
            "details": []
        }
        
        # Get all tax summaries for the current year
        tax_summaries = frappe.get_all(
            "Employee Tax Summary",
            filters={"year": current_year},
            fields=["name", "employee", "employee_name", "ytd_tax"]
        )
        
        if not tax_summaries:
            frappe.msgprint(_("No tax summaries found for {0}").format(current_year))
            return summary
            
        summary["total_summaries"] = len(tax_summaries)
        
        # Process each summary
        for tax_summary in tax_summaries:
            try:
                # Get the document
                summary_doc = frappe.get_doc("Employee Tax Summary", tax_summary.name)
                
                # Check monthly details
                if not hasattr(summary_doc, 'monthly_details') or not summary_doc.monthly_details:
                    summary["errors"] += 1
                    summary["details"].append({
                        "employee": tax_summary.employee,
                        "employee_name": tax_summary.employee_name,
                        "status": "Error",
                        "message": "Missing monthly details"
                    })
                    continue
                    
                # Calculate YTD tax from monthly details
                calculated_ytd = 0
                for detail in summary_doc.monthly_details:
                    if hasattr(detail, 'tax_amount'):
                        calculated_ytd += flt(detail.tax_amount)
                
                # Compare with stored value
                current_ytd = flt(tax_summary.ytd_tax)
                if abs(calculated_ytd - current_ytd) > 0.01:  # Allow for small rounding differences
                    # Fix YTD tax
                    summary_doc.ytd_tax = calculated_ytd
                    summary_doc.flags.ignore_validate_update_after_submit = True
                    summary_doc.save(ignore_permissions=True)
                    
                    summary["fixed"] += 1
                    summary["details"].append({
                        "employee": tax_summary.employee,
                        "employee_name": tax_summary.employee_name,
                        "status": "Fixed",
                        "message": f"YTD tax updated from {current_ytd} to {calculated_ytd}"
                    })
                else:
                    summary["validated"] += 1
                    summary["details"].append({
                        "employee": tax_summary.employee,
                        "employee_name": tax_summary.employee_name,
                        "status": "Valid",
                        "message": "All values are consistent"
                    })
                    
            except Exception as e:
                frappe.log_error(
                    f"Error validating tax summary {tax_summary.name}: {str(e)}",
                    "Tax Summary Validation Error"
                )
                summary["errors"] += 1
                summary["details"].append({
                    "employee": tax_summary.employee,
                    "employee_name": tax_summary.employee_name,
                    "status": "Error",
                    "message": str(e)[:100]
                })
                continue
                
        # Log summary
        log_message = (
            f"Tax summary validation completed for {current_year}. "
            f"Validated: {summary['validated']}, Fixed: {summary['fixed']}, "
            f"Errors: {summary['errors']}, Total: {summary['total_summaries']}"
        )
        
        if summary["errors"] > 0 or summary["fixed"] > 0:
            frappe.log_error(log_message, "Tax Summary Validation Summary")
        else:
            frappe.logger().info(log_message)
            
        frappe.msgprint(log_message)
        return summary
        
    except Exception as e:
        frappe.log_error(
            f"Error validating monthly entries: {str(e)}",
            "Monthly Validation Error"
        )
        frappe.throw(_("Error validating monthly entries: {0}").format(str(e)))