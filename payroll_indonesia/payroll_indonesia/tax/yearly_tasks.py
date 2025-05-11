# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 09:01:48 by dannyaudian

import frappe
from frappe import _
from frappe.utils import getdate, nowdate, flt, add_days
from datetime import datetime
from typing import Dict, Optional, Union, List, Any

# Import from pph_ter directly rather than ter_calculator
from payroll_indonesia.payroll_indonesia.tax.pph_ter import map_ptkp_to_ter_category
# Import tax calculation logic from the centralized ter_logic module
from payroll_indonesia.payroll_indonesia.tax.ter_logic import hitung_pph_tahunan
# Import cache utilities
from payroll_indonesia.utilities.cache_utils import get_cached_value, cache_value, clear_cache


def prepare_tax_report(year: Optional[int] = None, company: Optional[str] = None) -> Dict[str, Any]:
    """
    Prepare annual tax reports for employees with PMK 168/2023 compliance
    
    This function should be called at the end of the tax year
    to prepare tax reports (form 1721-A1) for each employee
    
    Args:
        year: Tax year to process. Defaults to current year.
        company: Company to process. If not provided, all companies are processed.
        
    Returns:
        Summary of processed reports
    """
    try:
        # Validate parameters
        if not year:
            year = datetime.now().year
            frappe.msgprint(
                _("Tax year not specified, using current year: {0}").format(year),
                indicator="blue"
            )
            
        # Validate year is valid
        current_year = datetime.now().year
        if not isinstance(year, int) or year < 2000 or year > current_year + 1:
            frappe.throw(
                _("Invalid tax year: {0}. Must be between 2000 and {1}").format(year, current_year + 1),
                title=_("Invalid Year")
            )
            
        # Check if company exists if provided
        if company and not frappe.db.exists("Company", company):
            frappe.throw(
                _("Company {0} not found").format(company),
                title=_("Invalid Company")
            )
            
        # Prepare start and end dates for the year
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"
        
        # Statistics
        summary = {
            "year": year,
            "company": company or "All Companies",
            "total_employees": 0,
            "processed": 0,
            "errors": 0,
            "details": []
        }
            
        # Get list of employees with salary slips in the specified period
        employees_filter = {
            "posting_date": ["between", [start_date, end_date]],
            "docstatus": 1
        }
        
        if company:
            employees_filter["company"] = company
            
        # Get unique employees from salary slips
        employee_list = frappe.db.sql("""
            SELECT DISTINCT employee, employee_name
            FROM `tabSalary Slip`
            WHERE posting_date BETWEEN %s AND %s
            AND docstatus = 1
            {company_clause}
        """.format(
            company_clause=f"AND company = '{company}'" if company else ""
        ), (start_date, end_date), as_dict=1)
        
        if not employee_list:
            frappe.msgprint(
                _("No employees found with salary slips in {0}").format(year),
                indicator="orange"
            )
            return summary
            
        summary["total_employees"] = len(employee_list)
        
        # Process each employee
        for emp in employee_list:
            try:
                # Check if employee still exists
                if not frappe.db.exists("Employee", emp.employee):
                    # Non-critical error - can continue with other employees
                    frappe.log_error(
                        "Employee {0} ({1}) no longer exists in the system".format(
                            emp.employee, emp.employee_name
                        ),
                        "Annual Tax Report Warning"
                    )
                    summary["errors"] += 1
                    summary["details"].append({
                        "employee": emp.employee,
                        "employee_name": emp.employee_name,
                        "status": "Error",
                        "message": "Employee no longer exists"
                    })
                    continue
                
                # Check if employee tax summary exists
                tax_summary = frappe.db.get_value(
                    "Employee Tax Summary",
                    {"employee": emp.employee, "year": year},
                    "name"
                )
                
                if not tax_summary:
                    # Try to create tax summary if it doesn't exist
                    try:
                        # Calculate tax summary using ter_logic instead of annual_calculation
                        tax_data = hitung_pph_tahunan(emp.employee, year)
                        
                        # Create tax report document
                        create_annual_tax_report(emp.employee, year, tax_data)
                        
                        summary["processed"] += 1
                        summary["details"].append({
                            "employee": emp.employee,
                            "employee_name": emp.employee_name,
                            "status": "Success",
                            "message": "Tax report created"
                        })
                    except Exception as e:
                        # Non-critical error - can continue with other employees
                        frappe.log_error(
                            "Failed to create tax summary for {0} ({1}): {2}".format(
                                emp.employee, emp.employee_name, str(e)
                            ),
                            "Annual Tax Report Warning"
                        )
                        summary["errors"] += 1
                        summary["details"].append({
                            "employee": emp.employee,
                            "employee_name": emp.employee_name,
                            "status": "Error",
                            "message": str(e)[:100]
                        })
                        continue
                else:
                    # Update existing tax summary
                    try:
                        update_existing_tax_report(tax_summary, year)
                        
                        summary["processed"] += 1
                        summary["details"].append({
                            "employee": emp.employee,
                            "employee_name": emp.employee_name,
                            "status": "Success",
                            "message": "Tax report updated"
                        })
                    except Exception as e:
                        # Non-critical error - can continue with other employees
                        frappe.log_error(
                            "Failed to update tax summary for {0} ({1}): {2}".format(
                                emp.employee, emp.employee_name, str(e)
                            ),
                            "Annual Tax Report Warning"
                        )
                        summary["errors"] += 1
                        summary["details"].append({
                            "employee": emp.employee,
                            "employee_name": emp.employee_name,
                            "status": "Error",
                            "message": str(e)[:100]
                        })
                        continue
                    
            except Exception as e:
                # Non-critical error - can continue with other employees
                frappe.log_error(
                    "Error processing employee {0} ({1}): {2}".format(
                        emp.employee, emp.employee_name, str(e)
                    ),
                    "Annual Tax Report Warning"
                )
                summary["errors"] += 1
                summary["details"].append({
                    "employee": emp.employee,
                    "employee_name": emp.employee_name,
                    "status": "Error",
                    "message": str(e)[:100]
                })
                continue
        
        # Log summary
        log_message = (
            "Tax report preparation completed for {0} (PMK 168/2023). "
            "Processed: {1}/{2}, "
            "Errors: {3}".format(
                year, summary['processed'], summary['total_employees'], summary['errors']
            )
        )
        
        if summary["errors"] > 0:
            frappe.log_error(log_message, "Annual Tax Report Summary")
            frappe.msgprint(log_message, indicator="orange")
        else:
            frappe.log_error(log_message, "Annual Tax Report Success")
            frappe.msgprint(log_message, indicator="green")
            
        return summary
        
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # Critical error - log and re-raise
        frappe.log_error(
            "Error preparing tax reports: {0}".format(str(e)),
            "Annual Tax Report Error"
        )
        frappe.throw(
            _("Error preparing tax reports: {0}").format(str(e)),
            title=_("Tax Report Preparation Failed")
        )


def create_annual_tax_report(employee: str, year: int, tax_data: Dict[str, Any]) -> Optional[str]:
    """
    Create annual tax report document for an employee
    
    Args:
        employee: Employee ID
        year: Tax year
        tax_data: Tax calculation data
        
    Returns:
        Generated report document name
    """
    try:
        # Validate parameters
        if not employee:
            frappe.throw(
                _("Employee ID is required"),
                title=_("Missing Parameter")
            )
            
        if not year:
            frappe.throw(
                _("Tax year is required"),
                title=_("Missing Parameter")
            )
            
        # Use cache for employee details
        cache_key = f"employee_details:{employee}"
        emp_doc = get_cached_value(cache_key)
        
        if emp_doc is None:
            # Check if Annual Tax Report DocType exists
            if not frappe.db.exists("DocType", "Annual Tax Report"):
                frappe.throw(
                    _("Annual Tax Report DocType does not exist. Cannot create report."),
                    title=_("Missing DocType")
                )
                
            # Get employee details and cache them
            try:
                emp_doc = frappe.get_doc("Employee", employee)
                cache_value(cache_key, emp_doc, 3600)  # Cache for 1 hour
            except Exception as e:
                frappe.throw(
                    _("Error retrieving employee {0}: {1}").format(employee, str(e)),
                    title=_("Employee Not Found")
                )
        
        # Create report
        report_doc = frappe.new_doc("Annual Tax Report")
        report_doc.employee = employee
        report_doc.employee_name = emp_doc.employee_name
        report_doc.year = year
        report_doc.company = emp_doc.company
        
        # Add tax information from tax_data
        if tax_data:
            report_doc.gross_income = flt(tax_data.get('annual_income', 0))
            report_doc.net_income = flt(tax_data.get('annual_net', 0))
            report_doc.job_expense = flt(tax_data.get('biaya_jabatan', 0))
            report_doc.bpjs_deductions = flt(tax_data.get('bpjs_total', 0))
            report_doc.ptkp = flt(tax_data.get('ptkp', 0))
            report_doc.pkp = flt(tax_data.get('pkp', 0))
            report_doc.tax_paid = flt(tax_data.get('already_paid', 0))
            report_doc.annual_tax = flt(tax_data.get('annual_tax', 0))
            
            # Set tax status if field exists
            if hasattr(report_doc, 'tax_status'):
                report_doc.tax_status = emp_doc.get("status_pajak", "TK0")
            
            # Add TER information if field exists and TER is used
            if hasattr(report_doc, 'ter_category') and tax_data.get('ter_used'):
                try:
                    # Map PTKP status to TER category using cached value if available
                    cache_key = f"ter_category:{emp_doc.get('status_pajak', 'TK0')}"
                    ter_category = get_cached_value(cache_key)
                    
                    if ter_category is None:
                        ter_category = map_ptkp_to_ter_category(emp_doc.get("status_pajak", "TK0"))
                        cache_value(cache_key, ter_category, 86400)  # Cache for 24 hours
                        
                    report_doc.ter_category = ter_category
                except Exception as e:
                    # Non-critical error - log and continue with fallback
                    frappe.log_error(
                        "Error mapping TER category for {0} with status {1}: {2}".format(
                            employee, emp_doc.get("status_pajak", "TK0"), str(e)
                        ),
                        "TER Mapping Warning"
                    )
                    # Fallback to simpler mapping if function not available
                    if emp_doc.get("status_pajak") == "TK0":
                        report_doc.ter_category = "TER A"
                    else:
                        report_doc.ter_category = "TER B"
            
        # Insert document
        report_doc.insert(ignore_permissions=True)
        
        # Log success
        frappe.log_error(
            "Annual Tax Report created for {0} ({1}) - {2}".format(
                employee, emp_doc.employee_name, year
            ),
            "Tax Report Creation Success"
        )
        
        return report_doc.name
        
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # Critical error - log and re-raise
        frappe.log_error(
            "Error creating annual tax report for {0}, year {1}: {2}".format(
                employee, year, str(e)
            ),
            "Annual Tax Report Creation Error"
        )
        raise


def update_existing_tax_report(report_name: str, year: int) -> bool:
    """
    Update an existing tax report with latest data
    
    Args:
        report_name: The name of the tax report document
        year: Tax year
        
    Returns:
        True if updated successfully
    """
    try:
        # Validate parameters
        if not report_name:
            frappe.throw(
                _("Report name is required"),
                title=_("Missing Parameter")
            )
            
        if not year:
            frappe.throw(
                _("Tax year is required"),
                title=_("Missing Parameter")
            )
            
        # Get the report document
        try:
            report_doc = frappe.get_doc("Annual Tax Report", report_name)
        except Exception as e:
            frappe.throw(
                _("Error retrieving tax report {0}: {1}").format(report_name, str(e)),
                title=_("Report Not Found")
            )
        
        # Recalculate tax data using ter_logic
        tax_data = hitung_pph_tahunan(report_doc.employee, year)
        
        # Update report with latest values
        if tax_data:
            report_doc.gross_income = flt(tax_data.get('annual_income', 0))
            report_doc.net_income = flt(tax_data.get('annual_net', 0))
            report_doc.job_expense = flt(tax_data.get('biaya_jabatan', 0))
            report_doc.bpjs_deductions = flt(tax_data.get('bpjs_total', 0))
            report_doc.ptkp = flt(tax_data.get('ptkp', 0))
            report_doc.pkp = flt(tax_data.get('pkp', 0))
            report_doc.tax_paid = flt(tax_data.get('already_paid', 0))
            report_doc.annual_tax = flt(tax_data.get('annual_tax', 0))
            
            # Update TER information if field exists and TER is used
            if hasattr(report_doc, 'ter_category') and tax_data.get('ter_used'):
                try:
                    # Get employee document using cache
                    cache_key = f"employee_details:{report_doc.employee}"
                    emp_doc = get_cached_value(cache_key)
                    
                    if emp_doc is None:
                        emp_doc = frappe.get_doc("Employee", report_doc.employee)
                        cache_value(cache_key, emp_doc, 3600)  # Cache for 1 hour
                    
                    # Map PTKP status to TER category using cached value if available
                    cache_key = f"ter_category:{emp_doc.get('status_pajak', 'TK0')}"
                    ter_category = get_cached_value(cache_key)
                    
                    if ter_category is None:
                        ter_category = map_ptkp_to_ter_category(emp_doc.get("status_pajak", "TK0"))
                        cache_value(cache_key, ter_category, 86400)  # Cache for 24 hours
                        
                    report_doc.ter_category = ter_category
                except Exception as e:
                    # Non-critical error - log and continue
                    frappe.log_error(
                        "Error updating TER category for {0}: {1}".format(
                            report_doc.employee, str(e)
                        ),
                        "TER Update Warning"
                    )
                    # Silently ignore TER category update if it fails
                    pass
            
            # Update modification timestamps
            report_doc.modified = nowdate()
            
        # Save document
        report_doc.save(ignore_permissions=True)
        
        # Log success
        frappe.log_error(
            "Annual Tax Report updated for {0} ({1}) - {2}".format(
                report_doc.employee, report_doc.employee_name, year
            ),
            "Tax Report Update Success"
        )
        
        return True
        
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # Critical error - log and re-raise
        frappe.log_error(
            "Error updating tax report {0}: {1}".format(report_name, str(e)),
            "Annual Tax Report Update Error"
        )
        raise


def generate_form_1721_a1(employee: Optional[str] = None, year: Optional[int] = None) -> Dict[str, Any]:
    """
    Generate Form 1721-A1 (Annual Tax Form) for an employee or all employees
    according to PMK 168/2023 requirements
    
    Args:
        employee: Specific employee to generate form for
        year: Tax year to generate form for
        
    Returns:
        Summary of generated forms
    """
    try:
        # Validate parameters
        if not year:
            year = datetime.now().year - 1  # Default to previous year
            frappe.msgprint(
                _("Tax year not specified, using previous year: {0}").format(year),
                indicator="blue"
            )
        
        # Process single employee if specified
        if employee:
            if not frappe.db.exists("Employee", employee):
                frappe.throw(
                    _("Employee {0} not found").format(employee),
                    title=_("Invalid Employee")
                )
                
            # Generate form for one employee
            return create_1721_a1_form(employee, year)
        
        # Process all active employees
        employees = frappe.get_all(
            "Employee",
            filters={"status": "Active"},
            fields=["name", "employee_name", "status_pajak"]
        )
        
        summary = {
            "year": year,
            "total": len(employees),
            "success": 0,
            "failed": 0,
            "details": []
        }
        
        for emp in employees:
            try:
                # Map PTKP status to TER category for reference using cache
                cache_key = f"ter_category:{emp.get('status_pajak', 'TK0')}"
                ter_category = get_cached_value(cache_key)
                
                if ter_category is None:
                    ter_category = map_ptkp_to_ter_category(emp.get("status_pajak", "TK0"))
                    cache_value(cache_key, ter_category, 86400)  # Cache for 24 hours
                    
                result = create_1721_a1_form(emp.name, year)
                summary["success"] += 1
                summary["details"].append({
                    "employee": emp.name,
                    "employee_name": emp.employee_name,
                    "status_pajak": emp.get("status_pajak", "TK0"),
                    "ter_category": ter_category,
                    "status": "Success",
                    "message": "Form generated successfully"
                })
            except Exception as e:
                # Non-critical error - can continue with other employees
                frappe.log_error(
                    "Error generating form for {0} ({1}): {2}".format(
                        emp.name, emp.employee_name, str(e)
                    ),
                    "Form Generation Warning"
                )
                summary["failed"] += 1
                summary["details"].append({
                    "employee": emp.name,
                    "employee_name": emp.employee_name,
                    "status_pajak": emp.get("status_pajak", "TK0"),
                    "ter_category": ter_category if 'ter_category' in locals() else "",
                    "status": "Failed",
                    "message": str(e)[:100]
                })
                continue
                
        # Log summary
        log_message = (
            "Form 1721-A1 generation completed for {0} (PMK 168/2023). "
            "Success: {1}/{2}, "
            "Failed: {3}".format(
                year, summary['success'], summary['total'], summary['failed']
            )
        )
        
        if summary["failed"] > 0:
            frappe.log_error(log_message, "Form 1721-A1 Generation Summary")
            frappe.msgprint(log_message, indicator="orange")
        else:
            frappe.log_error(log_message, "Form 1721-A1 Generation Success")
            frappe.msgprint(log_message, indicator="green")
            
        return summary
        
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # Critical error - log and throw
        frappe.log_error(
            "Error generating Form 1721-A1: {0}".format(str(e)),
            "Form 1721-A1 Generation Error"
        )
        frappe.throw(
            _("Error generating Form 1721-A1: {0}").format(str(e)),
            title=_("Form Generation Failed")
        )
        

def create_1721_a1_form(employee: str, year: int) -> Optional[str]:
    """
    Create Form 1721-A1 for a specific employee
    
    Args:
        employee: Employee ID
        year: Tax year
        
    Returns:
        Generated form document name or None if not implemented yet
    """
    # This is a stub for future implementation
    frappe.msgprint(
        _("Form 1721-A1 generation not fully implemented yet - PMK 168/2023 compliance pending"),
        indicator="blue"
    )
    
    # Log the action for audit purposes
    frappe.log_error(
        "Form 1721-A1 generation requested for employee {0}, year {1}".format(employee, year),
        "Form Generation Request"
    )
    
    return None