# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 08:32:34 by dannyaudian

import frappe
import json
import re
from frappe import _
from frappe.utils import getdate, nowdate, cint, flt, strip_html

#
# EMPLOYEE API ENDPOINTS
#


@frappe.whitelist(allow_guest=False)
def get_employee(name=None, filters=None):
    """API to get employee data"""
    if not frappe.has_permission("Employee", "read"):
        frappe.throw(_("Not permitted to read Employee data"), frappe.PermissionError)

    try:
        if name:
            # Get specific employee
            doc = frappe.get_doc("Employee", name)

            # Add tax and BPJS info
            doc.custom_data = {
                "tax_info": {
                    "npwp": doc.npwp if hasattr(doc, "npwp") else "",
                    "ktp": doc.ktp if hasattr(doc, "ktp") else "",
                    "status_pajak": doc.status_pajak if hasattr(doc, "status_pajak") else "TK0",
                }
            }

            # Get bank account info for salary payments
            doc.custom_data["bank_accounts"] = frappe.get_all(
                "Bank Account",
                filters={"party_type": "Employee", "party": name},
                fields=["name", "bank", "bank_account_no", "account_name", "is_default"],
            )

            return doc

        # Handle filters
        filters = json.loads(filters) if isinstance(filters, str) else (filters or {})

        # Get all employees matching filters
        employees = frappe.get_all(
            "Employee",
            filters=filters,
            fields=[
                "name",
                "employee_name",
                "company",
                "status",
                "date_of_joining",
                "department",
                "designation",
                "npwp",
                "ktp",
                "status_pajak",
            ],
        )

        # Return the employee list
        return {"data": employees, "count": len(employees)}
    except Exception as e:
        frappe.log_error(f"Error in get_employee: {str(e)}\n{frappe.get_traceback()}", "API Error")
        frappe.throw(_("Error retrieving Employee data: {0}").format(str(e)))


#
# SALARY SLIP API ENDPOINTS
#


@frappe.whitelist(allow_guest=False)
def get_salary_slips_by_employee(employee, year=None):
    """API to get all salary slips for a specific employee"""
    if not frappe.has_permission("Salary Slip", "read"):
        frappe.throw(_("Not permitted to read Salary Slip data"), frappe.PermissionError)

    try:
        # Build filters
        filters = {"employee": employee, "docstatus": 1}  # Only get submitted salary slips

        # Add year filter if provided
        if year:
            year = cint(year)
            filters.update(
                {"start_date": [">=", f"{year}-01-01"], "end_date": ["<=", f"{year}-12-31"]}
            )

        # Get all salary slips for this employee
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters=filters,
            fields=[
                "name",
                "employee",
                "employee_name",
                "start_date",
                "end_date",
                "gross_pay",
                "net_pay",
                "total_deduction",
                "posting_date",
                "company",
                "month",
                "is_using_ter",
                "ter_rate",
                "total_working_days",
                "total_bpjs",
                "npwp",
                "ktp",
            ],
            order_by="posting_date DESC",
        )

        # Group salary slips by year and month
        results = {}

        for slip in salary_slips:
            # Add formatted currency values
            slip["formatted_gross_pay"] = frappe.format(
                slip["gross_pay"], {"fieldtype": "Currency"}
            )
            slip["formatted_net_pay"] = frappe.format(slip["net_pay"], {"fieldtype": "Currency"})
            slip["formatted_total_deduction"] = frappe.format(
                slip["total_deduction"], {"fieldtype": "Currency"}
            )

            # Get period info
            slip_year = getdate(slip["end_date"]).year
            slip_month = getdate(slip["end_date"]).month

            # Add month name
            month_names = [
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            ]
            slip["month_name"] = (
                month_names[slip_month - 1] if 1 <= slip_month <= 12 else f"Month {slip_month}"
            )

            # Initialize year in results if not exists
            if slip_year not in results:
                results[slip_year] = {
                    "year": slip_year,
                    "slips_count": 0,
                    "total_gross": 0,
                    "total_net": 0,
                    "months": {},
                }

            # Initialize month in year if not exists
            if slip_month not in results[slip_year]["months"]:
                results[slip_year]["months"][slip_month] = {
                    "month": slip_month,
                    "month_name": slip["month_name"],
                    "slips": [],
                }

            # Add slip to month
            results[slip_year]["months"][slip_month]["slips"].append(slip)

            # Update year totals
            results[slip_year]["slips_count"] += 1
            results[slip_year]["total_gross"] += flt(slip["gross_pay"])
            results[slip_year]["total_net"] += flt(slip["net_pay"])

        # Add formatted totals to years
        for y in results:
            results[y]["formatted_total_gross"] = frappe.format(
                results[y]["total_gross"], {"fieldtype": "Currency"}
            )
            results[y]["formatted_total_net"] = frappe.format(
                results[y]["total_net"], {"fieldtype": "Currency"}
            )

            # Convert months dict to sorted list
            months_list = []
            for m in sorted(results[y]["months"].keys()):
                months_list.append(results[y]["months"][m])
            results[y]["months"] = months_list

        # Convert years dict to list and sort by year descending
        years_list = []
        for y in sorted(results.keys(), reverse=True):
            years_list.append(results[y])

        return {
            "status": "success",
            "employee": employee,
            "employee_name": frappe.db.get_value("Employee", employee, "employee_name"),
            "total_slips": sum(y["slips_count"] for y in years_list),
            "data": years_list,
        }
    except Exception as e:
        frappe.log_error(
            f"Error getting salary slips for {employee}: {str(e)}\n{frappe.get_traceback()}",
            "API Error",
        )
        frappe.throw(_("Error retrieving salary slips: {0}").format(str(e)))


@frappe.whitelist(allow_guest=False)
def get_salary_slip(name):
    """API to get a specific salary slip with details"""
    if not frappe.has_permission("Salary Slip", "read"):
        frappe.throw(_("Not permitted to read Salary Slip data"), frappe.PermissionError)

    try:
        # Get the salary slip document
        doc = frappe.get_doc("Salary Slip", name)

        # Format currency values
        result = {
            "salary_slip": name,
            "employee": doc.employee,
            "employee_name": doc.employee_name,
            "start_date": doc.start_date,
            "end_date": doc.end_date,
            "posting_date": doc.posting_date,
            "gross_pay": doc.gross_pay,
            "net_pay": doc.net_pay,
            "total_deduction": doc.total_deduction,
            "formatted_gross_pay": frappe.format(doc.gross_pay, {"fieldtype": "Currency"}),
            "formatted_net_pay": frappe.format(doc.net_pay, {"fieldtype": "Currency"}),
            "formatted_total_deduction": frappe.format(
                doc.total_deduction, {"fieldtype": "Currency"}
            ),
            "company": doc.company,
            "docstatus": doc.docstatus,
            "period": f"{frappe.format(doc.start_date, {'fieldtype': 'Date'})} to {frappe.format(doc.end_date, {'fieldtype': 'Date'})}",
        }

        # Add tax information
        result["tax_info"] = {
            "npwp": doc.npwp if hasattr(doc, "npwp") else "",
            "ktp": doc.ktp if hasattr(doc, "ktp") else "",
            "is_using_ter": doc.is_using_ter if hasattr(doc, "is_using_ter") else 0,
            "ter_rate": doc.ter_rate if hasattr(doc, "ter_rate") else 0,
        }

        # Add earnings details
        earnings = []
        for earning in doc.earnings:
            earnings.append(
                {
                    "salary_component": earning.salary_component,
                    "amount": earning.amount,
                    "formatted_amount": frappe.format(earning.amount, {"fieldtype": "Currency"}),
                }
            )
        result["earnings"] = earnings

        # Add deductions details
        deductions = []
        for deduction in doc.deductions:
            deductions.append(
                {
                    "salary_component": deduction.salary_component,
                    "amount": deduction.amount,
                    "formatted_amount": frappe.format(deduction.amount, {"fieldtype": "Currency"}),
                }
            )
        result["deductions"] = deductions

        # Get employee additional info
        result["employee_details"] = {
            "department": frappe.db.get_value("Employee", doc.employee, "department"),
            "designation": frappe.db.get_value("Employee", doc.employee, "designation"),
            "employment_type": frappe.db.get_value("Employee", doc.employee, "employment_type"),
            "bank_account": get_employee_bank_account(doc.employee),
        }

        return result
    except Exception as e:
        frappe.log_error(
            f"Error getting salary slip {name}: {str(e)}\n{frappe.get_traceback()}", "API Error"
        )
        frappe.throw(_("Error retrieving salary slip: {0}").format(str(e)))


def get_employee_bank_account(employee):
    """Get employee default bank account"""
    bank_account = None

    try:
        # First try to get default bank account
        bank_accounts = frappe.get_all(
            "Bank Account",
            filters={"party_type": "Employee", "party": employee, "is_default": 1},
            fields=["name", "bank", "bank_account_no", "account_name"],
        )

        if bank_accounts:
            bank_account = bank_accounts[0]
        else:
            # If no default found, get any bank account
            bank_accounts = frappe.get_all(
                "Bank Account",
                filters={"party_type": "Employee", "party": employee},
                fields=["name", "bank", "bank_account_no", "account_name"],
            )

            if bank_accounts:
                bank_account = bank_accounts[0]
    except Exception:
        pass

    return bank_account


@frappe.whitelist(allow_guest=False)
def get_recent_salary_slips(limit=10, company=None):
    """API to get recent salary slips across the company"""
    if not frappe.has_permission("Salary Slip", "read"):
        frappe.throw(_("Not permitted to read Salary Slip data"), frappe.PermissionError)

    try:
        # Build filters
        filters = {"docstatus": 1}  # Only get submitted salary slips

        # Add company filter if provided
        if company:
            filters["company"] = company

        # Get recent salary slips
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters=filters,
            fields=[
                "name",
                "employee",
                "employee_name",
                "start_date",
                "end_date",
                "posting_date",
                "gross_pay",
                "net_pay",
                "company",
            ],
            order_by="posting_date DESC, creation DESC",
            limit_page_length=cint(limit),
        )

        # Enhance each slip with formatted data
        for slip in salary_slips:
            slip["formatted_gross_pay"] = frappe.format(
                slip["gross_pay"], {"fieldtype": "Currency"}
            )
            slip["formatted_net_pay"] = frappe.format(slip["net_pay"], {"fieldtype": "Currency"})
            slip["period"] = (
                f"{frappe.format(slip['start_date'], {'fieldtype': 'Date'})} to {frappe.format(slip['end_date'], {'fieldtype': 'Date'})}"
            )

            # Add department and designation
            slip["department"] = frappe.db.get_value("Employee", slip["employee"], "department")
            slip["designation"] = frappe.db.get_value("Employee", slip["employee"], "designation")

        return {"status": "success", "count": len(salary_slips), "data": salary_slips}
    except Exception as e:
        frappe.log_error(
            f"Error getting recent salary slips: {str(e)}\n{frappe.get_traceback()}", "API Error"
        )
        frappe.throw(_("Error retrieving recent salary slips: {0}").format(str(e)))


@frappe.whitelist()
def diagnose_salary_slip(slip_name):
    """
    Diagnose issues with salary slip calculation
    Args:
        slip_name: Name of the salary slip
    Returns:
        dict: Detailed diagnostic information
    """
    try:
        # Get the document
        doc = frappe.get_doc("Salary Slip", slip_name)

        # Collect key information for debugging
        result = {
            "name": doc.name,
            "employee": doc.employee,
            "employee_name": doc.employee_name,
            "start_date": doc.start_date,
            "end_date": doc.end_date,
            "posting_date": doc.posting_date,
            "gross_pay": doc.gross_pay,
            "total_deduction": doc.total_deduction,
            "net_pay": doc.net_pay,
            "earnings": [],
            "deductions": [],
            "tax_details": {},
        }

        # Get earnings details
        for earning in doc.earnings:
            result["earnings"].append(
                {"component": earning.salary_component, "amount": earning.amount}
            )

        # Get deductions details
        for deduction in doc.deductions:
            result["deductions"].append(
                {"component": deduction.salary_component, "amount": deduction.amount}
            )

        # Check for tax calculation method and TER info
        result["tax_details"]["is_using_ter"] = getattr(doc, "is_using_ter", 0)
        result["tax_details"]["ter_rate"] = getattr(doc, "ter_rate", 0)

        # Check for tax amounts
        pph21_amount = 0
        for deduction in doc.deductions:
            if deduction.salary_component == "PPh 21" or "PPh 21" in deduction.salary_component:
                pph21_amount = deduction.amount
                break

        result["tax_details"]["pph21_amount"] = pph21_amount

        # Extract tax calculation details from payroll_note
        if hasattr(doc, "payroll_note") and doc.payroll_note:
            result["payroll_note"] = doc.payroll_note

            # Try to extract key information from payroll_note
            note = strip_html(doc.payroll_note)

            # Extract tax method
            if "Method: TER" in note:
                result["tax_details"]["method"] = "TER"
            elif "Method: PROGRESSIVE" in note:
                result["tax_details"]["method"] = "PROGRESSIVE"

            # Extract gross pay from note
            gross_pattern = r"Penghasilan Bruto: Rp ([\d,]+)"
            gross_match = re.search(gross_pattern, note)
            if gross_match:
                result["tax_details"]["note_gross_pay"] = gross_match.group(1)

            # Extract TER rate if present
            ter_pattern = r"Tarif Efektif Rata-rata: ([\d.]+)%"
            ter_match = re.search(ter_pattern, note)
            if ter_match:
                result["tax_details"]["note_ter_rate"] = ter_match.group(1)

        # Check if any TER adjustment was made
        if "gross_pay adjusted" in str(result.get("payroll_note", "")):
            result["tax_details"]["gross_pay_adjusted"] = True

            # Try to extract before and after values
            adjustment_pattern = r"gross_pay adjusted from ([\d,]+) to ([\d,]+)"
            adjustment_match = re.search(
                adjustment_pattern, str(result.get("payroll_note", "")), re.IGNORECASE
            )
            if adjustment_match:
                result["tax_details"]["adjusted_from"] = adjustment_match.group(1)
                result["tax_details"]["adjusted_to"] = adjustment_match.group(2)

        # Check additional tax-related fields if they exist
        for field in ["biaya_jabatan", "netto", "total_bpjs", "ptkp"]:
            if hasattr(doc, field):
                result["tax_details"][field] = getattr(doc, field)

        return result
    except Exception as e:
        return {"error": str(e), "traceback": frappe.get_traceback()}
