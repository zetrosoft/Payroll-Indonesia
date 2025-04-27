# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 02:25:18 by dannyaudian

import frappe
from frappe import _
from frappe.utils import getdate, nowdate, flt, add_days
from datetime import datetime

def prepare_tax_report(year=None, company=None):
    """
    Prepare annual tax reports for employees with improved implementation
    
    This function should be called at the end of the tax year
    to prepare tax reports (form 1721-A1) for each employee
    
    Args:
        year (int, optional): Tax year to process. Defaults to current year.
        company (str, optional): Company to process. If not provided, all companies are processed.
        
    Returns:
        dict: Summary of processed reports
    """
    try:
        # Validate parameters
        if not year:
            year = datetime.now().year
            frappe.msgprint(_("Tax year not specified, using current year: {0}").format(year))
            
        # Validate year is valid
        current_year = datetime.now().year
        if not isinstance(year, int) or year < 2000 or year > current_year + 1:
            frappe.throw(_("Invalid tax year: {0}. Must be between 2000 and {1}").format(year, current_year + 1))
            
        # Check if company exists if provided
        if company and not frappe.db.exists("Company", company):
            frappe.throw(_("Company {0} not found").format(company))
            
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
            frappe.msgprint(_("No employees found with salary slips in {0}").format(year))
            return summary
            
        summary["total_employees"] = len(employee_list)
        
        # Process each employee
        for emp in employee_list:
            try:
                # Check if employee still exists
                if not frappe.db.exists("Employee", emp.employee):
                    frappe.log_error(
                        f"Employee {emp.employee} ({emp.employee_name}) no longer exists in the system",
                        "Annual Tax Report Error"
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
                        from payroll_indonesia.payroll_indonesia.tax.annual_calculation import hitung_pph_tahunan
                        
                        # Calculate tax summary
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
                        frappe.log_error(
                            f"Failed to create tax summary for {emp.employee} ({emp.employee_name}): {str(e)}",
                            "Annual Tax Report Error"
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
                        frappe.log_error(
                            f"Failed to update tax summary for {emp.employee} ({emp.employee_name}): {str(e)}",
                            "Annual Tax Report Error"
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
                frappe.log_error(
                    f"Error processing employee {emp.employee} ({emp.employee_name}): {str(e)}",
                    "Annual Tax Report Error"
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
            f"Tax report preparation completed for {year}. "
            f"Processed: {summary['processed']}/{summary['total_employees']}, "
            f"Errors: {summary['errors']}"
        )
        
        if summary["errors"] > 0:
            frappe.log_error(log_message, "Annual Tax Report Summary")
        else:
            frappe.logger().info(log_message)
            
        frappe.msgprint(log_message)
        return summary
        
    except Exception as e:
        frappe.log_error(
            f"Error preparing tax reports: {str(e)}",
            "Annual Tax Report Error"
        )
        frappe.throw(_("Error preparing tax reports: {0}").format(str(e)))

def create_annual_tax_report(employee, year, tax_data):
    """
    Create annual tax report document for an employee
    
    Args:
        employee (str): Employee ID
        year (int): Tax year
        tax_data (dict): Tax calculation data
        
    Returns:
        str: Generated report document name
    """
    try:
        # Check if Annual Tax Report DocType exists
        if not frappe.db.exists("DocType", "Annual Tax Report"):
            frappe.log_error(
                f"Annual Tax Report DocType does not exist. Cannot create report for {employee}",
                "Annual Tax Report Error"
            )
            return None
            
        # Get employee details
        emp_doc = frappe.get_doc("Employee", employee)
        
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
        
        # Insert document
        report_doc.insert(ignore_permissions=True)
        
        # Log success
        frappe.logger().info(f"Annual Tax Report created for {employee} ({emp_doc.employee_name}) - {year}")
        
        return report_doc.name
        
    except Exception as e:
        frappe.log_error(
            f"Error creating annual tax report for {employee}, year {year}: {str(e)}",
            "Annual Tax Report Creation Error"
        )
        raise

def update_existing_tax_report(report_name, year):
    """
    Update an existing tax report with latest data
    
    Args:
        report_name (str): The name of the tax report document
        year (int): Tax year
        
    Returns:
        bool: True if updated successfully
    """
    try:
        # Get the report document
        report_doc = frappe.get_doc("Annual Tax Report", report_name)
        
        # Recalculate tax data
        from payroll_indonesia.payroll_indonesia.tax.annual_calculation import hitung_pph_tahunan
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
            
            # Update modification timestamps
            report_doc.modified = nowdate()
            
        # Save document
        report_doc.save(ignore_permissions=True)
        
        # Log success
        frappe.logger().info(f"Annual Tax Report updated for {report_doc.employee} ({report_doc.employee_name}) - {year}")
        
        return True
        
    except Exception as e:
        frappe.log_error(
            f"Error updating tax report {report_name}: {str(e)}",
            "Annual Tax Report Update Error"
        )
        raise

def generate_form_1721_a1(employee=None, year=None):
    """
    Generate Form 1721-A1 (Annual Tax Form) for an employee or all employees
    
    Args:
        employee (str, optional): Specific employee to generate form for
        year (int, optional): Tax year to generate form for
        
    Returns:
        dict: Summary of generated forms
    """
    try:
        # Validate parameters
        if not year:
            year = datetime.now().year - 1  # Default to previous year
            frappe.msgprint(_("Tax year not specified, using previous year: {0}").format(year))
        
        # Process single employee if specified
        if employee:
            if not frappe.db.exists("Employee", employee):
                frappe.throw(_("Employee {0} not found").format(employee))
                
            # Generate form for one employee
            return create_1721_a1_form(employee, year)
        
        # Process all active employees
        employees = frappe.get_all(
            "Employee",
            filters={"status": "Active"},
            fields=["name", "employee_name"]
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
                result = create_1721_a1_form(emp.name, year)
                summary["success"] += 1
                summary["details"].append({
                    "employee": emp.name,
                    "employee_name": emp.employee_name,
                    "status": "Success",
                    "message": "Form generated successfully"
                })
            except Exception as e:
                summary["failed"] += 1
                summary["details"].append({
                    "employee": emp.name,
                    "employee_name": emp.employee_name,
                    "status": "Failed",
                    "message": str(e)[:100]
                })
                continue
                
        # Log summary
        log_message = (
            f"Form 1721-A1 generation completed for {year}. "
            f"Success: {summary['success']}/{summary['total']}, "
            f"Failed: {summary['failed']}"
        )
        
        if summary["failed"] > 0:
            frappe.log_error(log_message, "Form 1721-A1 Generation Summary")
        else:
            frappe.logger().info(log_message)
            
        frappe.msgprint(log_message)
        return summary
        
    except Exception as e:
        frappe.log_error(
            f"Error generating Form 1721-A1: {str(e)}",
            "Form 1721-A1 Generation Error"
        )
        frappe.throw(_("Error generating Form 1721-A1: {0}").format(str(e)))
        
def create_1721_a1_form(employee, year):
    """
    Create Form 1721-A1 for a specific employee
    
    Args:
        employee (str): Employee ID
        year (int): Tax year
        
    Returns:
        str: Generated form document name or None if not implemented yet
    """
    # This is a stub for future implementation
    frappe.msgprint(_("Form 1721-A1 generation not fully implemented yet"))
    
    # Log the action for audit purposes
    frappe.logger().info(f"Form 1721-A1 generation requested for employee {employee}, year {year}")
    
    return None