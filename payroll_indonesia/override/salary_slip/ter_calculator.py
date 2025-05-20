# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-20 04:53:47 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate

from .base import update_component_amount

# Import cache utilities
from payroll_indonesia.utilities.cache_utils import get_cached_value, cache_value

# Import constants
from payroll_indonesia.constants import (
    MONTHS_PER_YEAR,
    CACHE_SHORT,
    CACHE_LONG,
    CACHE_MEDIUM,
    TER_CATEGORY_A,
    TER_CATEGORY_B,
    TER_CATEGORY_C,
    TER_CATEGORIES,
)

# Import centralized logic functions
from payroll_indonesia.payroll_indonesia.tax.ter_logic import (
    detect_annual_income,
    add_tax_info_to_note,
)

# Import TER functions from pph_ter (single source of truth)
from payroll_indonesia.pph_ter import (
    map_ptkp_to_ter_category,
    get_ter_rate,
    calculate_monthly_tax_with_ter,
)

# Default values for required fields
TER_REQUIRED_FIELDS = {
    "monthly_gross_for_ter": 0,
    "annual_taxable_income": 0,
    "ter_rate": 0,
    "ter_category": "",
    "is_using_ter": 0,
    "payroll_note": "",
}


def log_ter_error(error_type, message, doc=None, employee=None):
    """
    Improved error logging function specifically for TER calculation errors.
    Prevents nesting of error messages and creates more concise logs.
    
    Args:
        error_type (str): Short type of TER-related error
        message (str): Error message
        doc (object, optional): Salary slip document
        employee (object, optional): Employee document
    """
    try:
        # Extract key information
        doc_name = getattr(doc, 'name', 'unknown') if doc else 'unknown'
        emp_name = getattr(employee, 'name', 'unknown') if employee else 'unknown'
        
        # Create concise title
        title = f"TER {error_type}: {emp_name}"
        
        # Sanitize message to avoid nesting
        import re
        sanitized_message = message
        if "Error Log" in sanitized_message:
            sanitized_message = re.sub(r"Error Log [a-z0-9]+:", "", sanitized_message)
            sanitized_message = re.sub(r"\([^)]*Error Log [^)]*\)", "", sanitized_message)
        
        # Create clean message with context
        clean_message = f"Document: {doc_name}, Employee: {emp_name}\n\nDetails: {sanitized_message}"
        
        return frappe.log_error(message=clean_message, title=title)
    except Exception:
        # Fallback to basic logging
        try:
            return frappe.log_error(message=str(message), title="TER Error")
        except Exception:
            # Last resort - fail silently
            pass


def ensure_ter_fields(doc):
    """
    Ensure all required fields for TER calculation exist in the document.
    Initialize them with default values if missing.
    
    Args:
        doc: Salary slip document
        
    Returns:
        bool: True if all fields were initialized successfully
    """
    if not doc:
        return False
        
    try:
        for field, default_value in TER_REQUIRED_FIELDS.items():
            if not hasattr(doc, field) or getattr(doc, field) is None:
                setattr(doc, field, default_value)
                try:
                    # Persist to database if possible
                    doc.db_set(field, default_value, update_modified=False)
                except Exception:
                    # Continue if db_set fails - we already set in-memory value
                    pass
        return True
    except Exception as e:
        log_ter_error("Field Initialization", str(e), doc)
        return False


def calculate_monthly_pph_with_ter(doc, employee):
    """Calculate PPh 21 using TER method based on PMK 168/2023"""
    try:
        # Ensure all required fields exist and are initialized
        ensure_ter_fields(doc)
        
        # Store original values for verification, with safe getattr access
        original_values = {
            "gross_pay": flt(getattr(doc, "gross_pay", 0)),
            "monthly_gross_for_ter": flt(getattr(doc, "monthly_gross_for_ter", 0)),
            "annual_taxable_income": flt(getattr(doc, "annual_taxable_income", 0)),
            "ter_rate": flt(getattr(doc, "ter_rate", 0)),
            "ter_category": getattr(doc, "ter_category", "") or "",
        }

        # Add concise log entry for debugging
        doc_name = getattr(doc, 'name', 'unknown')
        log_ter_error("Calculation Start", f"Beginning calculation for {doc_name}", doc, employee)
        
        # Validate employee status_pajak with safe access
        employee_status_pajak = getattr(employee, "status_pajak", "") if employee else ""
        if not employee_status_pajak:
            employee_status_pajak = "TK0"  # Default to TK0
            if hasattr(employee, "status_pajak"):
                employee.status_pajak = employee_status_pajak
            frappe.msgprint(_("Warning: Employee tax status not set, using TK0 as default"), indicator="orange")

        # Start with gross pay as monthly income with safe access
        monthly_gross_pay = flt(getattr(doc, "gross_pay", 0))

        # Calculate total earnings safely
        total_earnings = 0
        if hasattr(doc, "earnings") and doc.earnings:
            try:
                total_earnings = sum(flt(getattr(e, "amount", 0)) for e in doc.earnings)
            except Exception:
                # If earnings calculation fails, use 0
                pass

        # Get basic salary safely
        basic_salary = 0
        if hasattr(doc, "earnings") and doc.earnings:
            try:
                basic_salary_list = [
                    flt(getattr(e, "amount", 0)) 
                    for e in doc.earnings 
                    if getattr(e, "salary_component", "") in ["Gaji Pokok", "Basic Salary", "Basic Pay"]
                ]
                basic_salary = basic_salary_list[0] if basic_salary_list else 0
            except Exception:
                # If basic salary calculation fails, use 0
                pass

        # Use centralized logic to detect annual income
        bypass_detection = bool(getattr(doc, "bypass_annual_detection", False))
        is_annual, reason, monthly_gross_pay = detect_annual_income(
            monthly_gross_pay, total_earnings, basic_salary, bypass_detection
        )

        # Log annual value detection
        if is_annual:
            log_message = f"Detected annual value: {reason}. Adjusted from {getattr(doc, 'gross_pay', 0)} to {monthly_gross_pay}"
            log_ter_error("Annual Value", log_message, doc)

            # Add to payroll note if the field exists
            if hasattr(doc, "payroll_note") and doc.payroll_note is not None:
                doc.payroll_note += f"\n[TER] {reason}. Using monthly value: {monthly_gross_pay}"

        # Set and save monthly and annual values safely
        annual_taxable_income = flt(monthly_gross_pay * MONTHS_PER_YEAR)

        # Save monthly_gross_for_ter with safety checks
        doc.monthly_gross_for_ter = monthly_gross_pay
        try:
            doc.db_set("monthly_gross_for_ter", monthly_gross_pay, update_modified=False)
        except Exception as e:
            log_ter_error("Field Update", f"Could not save monthly_gross_for_ter: {str(e)}", doc)

        # Save annual_taxable_income with safety checks
        doc.annual_taxable_income = annual_taxable_income
        try:
            doc.db_set("annual_taxable_income", annual_taxable_income, update_modified=False)
        except Exception as e:
            log_ter_error("Field Update", f"Could not save annual_taxable_income: {str(e)}", doc)

        # Determine TER category from employee status with error handling
        ter_category = ""
        try:
            cache_key = f"ter_category:{employee_status_pajak}"
            ter_category = get_cached_value(cache_key)

            if ter_category is None:
                # Use centralized mapping function
                ter_category = map_ptkp_to_ter_category(employee_status_pajak)
                if ter_category:
                    cache_value(cache_key, ter_category, CACHE_LONG)
                else:
                    # Fallback if mapping returns empty
                    ter_category = TER_CATEGORY_C  # Default to highest category
        except Exception as e:
            log_ter_error("Category Mapping", str(e), doc, employee)
            ter_category = TER_CATEGORY_C  # Default to highest category on error
            frappe.msgprint(_("Warning: Error mapping TER category, using TER C as default"), indicator="orange")

        # Normalize the TER category with improved validation
        ter_category = normalize_ter_category(ter_category)

        # Calculate monthly tax with TER with improved error handling
        monthly_tax = 0
        ter_rate = 0
        
        try:
            # First attempt using the centralized function that handles validation
            monthly_tax, ter_rate = calculate_monthly_tax_with_ter(monthly_gross_pay, ter_category)
        except Exception as e:
            log_ter_error("Tax Calculation", f"Primary calculation failed: {str(e)}", doc)
            
            # Fallback calculation
            try:
                # Use the simplified approach with validation
                ter_rate = get_ter_rate(ter_category, employee_status_pajak)
                monthly_tax = flt(monthly_gross_pay * ter_rate)
            except Exception as e2:
                # Last resort fallback
                log_ter_error("Tax Calculation", f"Fallback calculation failed: {str(e2)}", doc)
                ter_rate = 0.05  # Default to 5% as absolute fallback
                monthly_tax = flt(monthly_gross_pay * ter_rate)
                frappe.msgprint(
                    _("Warning: TER calculation failed, using default 5% tax rate"), 
                    indicator="red"
                )

        # Set and save TER info safely
        doc.is_using_ter = 1
        doc.ter_rate = flt(ter_rate * 100)
        doc.ter_category = ter_category

        # Save TER info to database with error handling
        try:
            doc.db_set("is_using_ter", 1, update_modified=False)
            doc.db_set("ter_rate", flt(ter_rate * 100), update_modified=False)
            doc.db_set("ter_category", ter_category, update_modified=False)
        except Exception as e:
            log_ter_error("Database Update", f"Could not save TER fields: {str(e)}", doc)

        # Update PPh 21 component with error handling
        try:
            update_component_amount(doc, "PPh 21", monthly_tax, "deductions")
        except Exception as e:
            log_ter_error("Component Update", f"Could not update PPh 21 component: {str(e)}", doc)
            frappe.msgprint(_("Warning: Could not update PPh 21 salary component"), indicator="red")

        # Add tax info to note with error handling
        try:
            add_tax_info_to_note(
                doc,
                "TER",
                {
                    "status_pajak": employee_status_pajak,
                    "ter_category": ter_category,
                    "gross_pay": monthly_gross_pay,
                    "ter_rate": ter_rate * 100,
                    "monthly_tax": monthly_tax,
                },
            )
        except Exception as e:
            log_ter_error("Tax Note", f"Could not add tax info to note: {str(e)}", doc)
            # Create minimal note if add_tax_info_to_note fails
            if hasattr(doc, "payroll_note"):
                doc.payroll_note += f"\nTER calculation: Rate {ter_rate * 100}%, Tax: {monthly_tax}"

        # Verify calculation integrity with safe access
        verify_calculation_integrity(
            doc=doc,
            original_values=original_values,
            monthly_gross_pay=monthly_gross_pay,
            annual_taxable_income=annual_taxable_income,
            ter_rate=ter_rate,
            ter_category=ter_category,
            monthly_tax=monthly_tax,
        )

        log_ter_error("Calculation Complete", f"Successfully calculated TER for {doc_name}", doc)
        return True

    except Exception as e:
        # Improved error logging that avoids nested errors
        log_ter_error("Calculation Failure", str(e), doc, employee)
        # Simplified error message to avoid nested errors
        frappe.throw(_("Failed to calculate PPh 21 using TER method. See error log for details."))


def normalize_ter_category(category):
    """
    Normalize TER category to ensure it uses the correct format.
    
    Args:
        category (str): TER category input (could be 'A', 'B', 'C', or 'TER A', etc.)
        
    Returns:
        str: Normalized TER category ('TER A', 'TER B', or 'TER C')
    """
    category = (category or "").strip().upper()
    
    # Convert single letter format to TER format
    if category in ["A", "B", "C"]:
        category = f"TER {category}"
    # Ensure category starts with "TER " prefix
    elif not category.startswith("TER "):
        category = TER_CATEGORY_C  # Default to highest category
        
    # Validate against allowed categories
    if category not in TER_CATEGORIES:
        category = TER_CATEGORY_C  # Default to highest category if invalid
        
    return category


def calculate_simple_pph_with_ter(employee, taxable_income, ter_category=None, status_pajak=None):
    """
    Simplified version of PPh 21 calculation with TER for external usage.
    Includes proper category validation.
    
    Args:
        employee: Employee document or ID
        taxable_income: Monthly taxable income
        ter_category: TER category ('A', 'B', 'C', 'TER A', 'TER B', 'TER C')
        status_pajak: Tax status code (e.g., 'TK0', 'K1')
        
    Returns:
        float: Calculated monthly PPh 21 amount
    """
    # Normalize and validate the category
    category = normalize_ter_category(ter_category)
    
    # Get the TER rate
    rate = get_ter_rate(category, status_pajak)
    
    # Calculate and return tax amount
    return flt(taxable_income) * rate


def verify_calculation_integrity(
    doc,
    original_values,
    monthly_gross_pay,
    annual_taxable_income,
    ter_rate,
    ter_category,
    monthly_tax,
):
    """
    Verify integrity of TER calculation results with improved safety checks
    
    Args:
        doc: Salary slip document
        original_values: Dict of original values
        monthly_gross_pay: Calculated monthly gross pay
        annual_taxable_income: Calculated annual taxable amount
        ter_rate: Calculated TER rate (decimal)
        ter_category: Determined TER category
        monthly_tax: Calculated monthly tax amount
    
    Returns:
        bool: True if integrity is verified or issues were fixed
    """
    if not doc:
        return False
        
    try:
        errors = []
        
        # Ensure critical fields exist before checking them
        ensure_ter_fields(doc)

        # Only verify gross_pay if it exists in both doc and original_values
        if hasattr(doc, "gross_pay") and "gross_pay" in original_values:
            if abs(flt(doc.gross_pay) - flt(original_values.get("gross_pay", 0))) > 0.01:
                errors.append(f"gross_pay changed: {original_values.get('gross_pay', 0)} → {doc.gross_pay}")
                doc.gross_pay = flt(original_values.get("gross_pay", 0))
                try:
                    doc.db_set("gross_pay", flt(original_values.get("gross_pay", 0)), update_modified=False)
                except Exception:
                    # Continue if db_set fails
                    pass

        # Verify monthly_gross_for_ter
        if hasattr(doc, "monthly_gross_for_ter"):
            # Only do comparison if values actually differ significantly
            if abs(flt(doc.monthly_gross_for_ter) - flt(monthly_gross_pay)) > 0.01:
                errors.append(
                    f"monthly_gross_for_ter mismatch: expected {monthly_gross_pay}, "
                    f"got {doc.monthly_gross_for_ter}"
                )
                doc.monthly_gross_for_ter = flt(monthly_gross_pay)
                try:
                    doc.db_set("monthly_gross_for_ter", flt(monthly_gross_pay), update_modified=False)
                except Exception:
                    # Continue if db_set fails
                    pass

        # Verify annual_taxable_income
        if hasattr(doc, "annual_taxable_income"):
            expected_annual = flt(monthly_gross_pay * MONTHS_PER_YEAR)
            if abs(flt(doc.annual_taxable_income) - expected_annual) > 0.01:
                errors.append(
                    f"annual_taxable_income mismatch: expected {expected_annual}, "
                    f"got {doc.annual_taxable_income}"
                )
                doc.annual_taxable_income = expected_annual
                try:
                    doc.db_set("annual_taxable_income", expected_annual, update_modified=False)
                except Exception:
                    # Continue if db_set fails
                    pass

        # Verify TER values
        if hasattr(doc, "is_using_ter") and not doc.is_using_ter:
            errors.append("is_using_ter not set to 1")
            doc.is_using_ter = 1
            try:
                doc.db_set("is_using_ter", 1, update_modified=False)
            except Exception:
                # Continue if db_set fails
                pass

        if hasattr(doc, "ter_rate"):
            if abs(flt(doc.ter_rate) - flt(ter_rate * 100)) > 0.01:
                errors.append(f"ter_rate mismatch: expected {ter_rate * 100}, got {doc.ter_rate}")
                doc.ter_rate = flt(ter_rate * 100)
                try:
                    doc.db_set("ter_rate", flt(ter_rate * 100), update_modified=False)
                except Exception:
                    # Continue if db_set fails
                    pass

        if hasattr(doc, "ter_category") and doc.ter_category != ter_category:
            errors.append(f"ter_category mismatch: expected {ter_category}, got {doc.ter_category}")
            doc.ter_category = ter_category
            try:
                doc.db_set("ter_category", ter_category, update_modified=False)
            except Exception:
                # Continue if db_set fails
                pass

        # Log all errors found in a clean format
        if errors:
            error_list = "\n".join(f"- {err}" for err in errors)
            log_ter_error("Integrity Check", f"Issues found and fixed:\n{error_list}", doc)

            # Add minimal message to user
            frappe.msgprint(
                _("Some TER calculation values were automatically corrected."),
                indicator="orange",
            )

            # Add to payroll_note if available
            if hasattr(doc, "payroll_note") and doc.payroll_note is not None:
                doc.payroll_note += (
                    "\n[TER] Fixed calculation issues:\n"
                    + "\n".join(f"- {err}" for err in errors)
                )

        return True  # Return true even with errors since we fixed them

    except Exception as e:
        # Non-critical error - log but continue
        log_ter_error("Integrity Check", f"Verification failed: {str(e)}", doc)
        # Don't throw as this is a non-critical function
        return False


# YTD functions - to be moved to utils.py in a future refactoring
def get_ytd_totals_from_tax_summary(doc, year, month=None):
    """
    Get YTD tax totals from Employee Tax Summary with caching and improved parameter handling
    
    Args:
        doc: Salary slip document or employee ID string
        year: Tax year
        month: Month number (1-12), defaults to current month if not provided
    
    Returns:
        dict: YTD values (gross, tax, bpjs)
    """
    # Extract employee ID safely
    employee = None
    if isinstance(doc, str):
        employee = doc  # Already an employee ID
    elif hasattr(doc, "employee"):
        employee = doc.employee
    else:
        # Return empty result if no employee identified
        return {"gross": 0, "bpjs": 0, "pph21": 0}
        
    # Validate year
    if not year:
        # Try to get year from document
        if hasattr(doc, "start_date"):
            try:
                year = getdate(doc.start_date).year
            except Exception:
                # If parsing fails, use current year
                year = getdate().year
        else:
            year = getdate().year
            
    # Validate month
    if not month:
        # Try to get month from document
        if hasattr(doc, "start_date"):
            try:
                month = getdate(doc.start_date).month
            except Exception:
                # If parsing fails, use current month
                month = getdate().month
        else:
            month = getdate().month

    # Create cache key
    cache_key = f"ytd:{employee}:{year}:{month}"

    # Check cache first
    cached_result = get_cached_value(cache_key)
    if cached_result is not None:
        return cached_result

    try:
        # Use a parameterized query to get all needed data
        ytd_data = frappe.db.sql(
            """
            SELECT
                ETS.ytd_tax,
                SUM(ETSD.gross_pay) as ytd_gross,
                SUM(ETSD.bpjs_deductions) as ytd_bpjs
            FROM 
                `tabEmployee Tax Summary` ETS
            LEFT JOIN
                `tabEmployee Tax Summary Detail` ETSD ON ETS.name = ETSD.parent
            WHERE
                ETS.employee = %s
                AND ETS.year = %s
                AND ETSD.month < %s
            GROUP BY
                ETS.name
            """,
            (employee, year, month),
            as_dict=1,
        )

        if ytd_data and len(ytd_data) > 0:
            result = {
                "gross": flt(ytd_data[0].ytd_gross),
                "pph21": flt(ytd_data[0].ytd_tax),
                "bpjs": flt(ytd_data[0].ytd_bpjs),
            }

            # Cache the result (for 1 hour)
            cache_value(cache_key, result, CACHE_MEDIUM)
            return result
        else:
            # No data found, return zeros
            result = {"gross": 0, "pph21": 0, "bpjs": 0}
            cache_value(cache_key, result, CACHE_MEDIUM)
            return result

    except Exception as e:
        # Log error and fall back to legacy method
        log_ter_error("YTD Data", f"Error getting YTD data: {str(e)}", doc)
        
        # Only show message to user if this is being called directly from UI
        if frappe.local.form_dict.cmd == "payroll_indonesia.override.salary_slip.ter_calculator.get_ytd_totals_from_tax_summary":
            frappe.msgprint(
                _("Warning: Using fallback method to calculate YTD tax data"), 
                indicator="orange"
            )

        # Fallback to the older method
        return get_ytd_totals_from_tax_summary_legacy(employee, year, month)


def get_ytd_totals_from_tax_summary_legacy(employee, year, month=None):
    """
    Legacy fallback method to get YTD tax totals from Employee Tax Summary
    with improved parameter validation
    
    Args:
        employee: Employee ID or document
        year: Tax year
        month: Month number (1-12)
    """
    # Standard default result
    default_result = {"gross": 0, "pph21": 0, "bpjs": 0}
    
    try:
        # Extract employee ID if needed
        if not isinstance(employee, str) and hasattr(employee, "name"):
            employee = employee.name
            
        # Validate parameters
        if not employee or not year:
            return default_result
            
        # Default month to current if not provided
        if not month:
            month = getdate().month

        # Find Employee Tax Summary for this employee and year
        tax_summary = frappe.get_all(
            "Employee Tax Summary",
            filters={"employee": employee, "year": year, "docstatus": ["!=", 2]},
            fields=["name", "ytd_tax"],
            limit=1,
        )

        if not tax_summary:
            return default_result

        # Get monthly details for YTD calculations
        monthly_details = frappe.get_all(
            "Employee Tax Summary Detail",
            filters={"parent": tax_summary[0].name, "month": ["<", month]},
            fields=["gross_pay", "bpjs_deductions"],
            order_by="month asc",
        )

        # Calculate YTD totals safely
        ytd_gross = sum(flt(getattr(d, "gross_pay", 0)) for d in monthly_details)
        ytd_bpjs = sum(flt(getattr(d, "bpjs_deductions", 0)) for d in monthly_details)
        ytd_tax = flt(tax_summary[0].ytd_tax)

        result = {"gross": ytd_gross, "pph21": ytd_tax, "bpjs": ytd_bpjs}

        # Cache the result
        cache_key = f"ytd:{employee}:{year}:{month}"
        cache_value(cache_key, result, CACHE_MEDIUM)

        return result

    except Exception as e:
        # Log error but return empty result
        log_ter_error(
            "YTD Legacy", 
            f"Failed to calculate YTD values: {str(e)}", 
            None
        )
        return default_result
