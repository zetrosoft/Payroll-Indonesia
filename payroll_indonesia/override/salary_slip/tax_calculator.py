# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-19 08:05:38 by dannyaudian

"""
Implementation of tax calculation as per Indonesian regulations.

Tax calculation methods:
1. TER (Tarif Efektif Rata-rata) - As per PMK 168/2023
   - Used for monthly calculations (Jan-Nov)
   - Uses a lookup table based on employee's tax status and monthly income
   - Direct application of TER rate to monthly gross income

2. Progressive - Traditional method
   - Used for December calculations (required by PMK 168/2023)
   - Used for employees with irregular income
   - Calculates annual income, applies progressive tax rates, divides by 12
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, cint

# Import base module function for component update
from payroll_indonesia.override.salary_slip.base import update_component_amount

# Import TER calculation function from ter_calculator
from payroll_indonesia.override.salary_slip.ter_calculator import calculate_monthly_pph_with_ter

# Import YTD functions from ter_calculator for backward compatibility
from payroll_indonesia.override.salary_slip.ter_calculator import get_ytd_totals_from_tax_summary

# Import standardized cache utilities
from payroll_indonesia.utilities.cache_utils import get_cached_value, cache_value

# Import constants
from payroll_indonesia.constants import (
    MONTHS_PER_YEAR,
    CACHE_SHORT,
    CACHE_MEDIUM,
    BIAYA_JABATAN_PERCENT,
    BIAYA_JABATAN_MAX,
    DECEMBER_MONTH,
)

# Import centralized tax logic functions
from payroll_indonesia.payroll_indonesia.tax.ter_logic import (
    calculate_progressive_tax,
    get_ptkp_amount,
    should_use_ter_method,
    add_tax_info_to_note,
)

# Import TER functions from pph_ter (single source of truth)
# from payroll_indonesia.payroll_indonesia.tax.pph_ter import map_ptkp_to_ter_category


def log_tax_error(error_type, message, doc=None, employee=None):
    """
    Improved error logging function specifically for tax errors.
    Prevents nesting of error messages and creates more concise logs.

    Args:
        error_type (str): Short type of error (e.g. "TER Calculation", "Progressive Tax")
        message (str): Error message, will be processed to avoid nesting
        doc (object, optional): Salary slip document or other relevant document
        employee (object, optional): Employee document if available

    Returns:
        str: The error log ID if created
    """
    try:
        # Extract key information for the error title
        doc_name = getattr(doc, 'name', 'unknown') if doc else 'unknown'
        emp_name = getattr(employee, 'name', 'unknown') if employee else 'unknown'
        
        # Create a short descriptive title with key information
        title = f"{error_type}: {emp_name}"
        
        # Sanitize message to avoid nesting by removing existing error log IDs
        sanitized_message = message
        if "Error Log " in sanitized_message:
            # Remove nested error log references
            import re
            sanitized_message = re.sub(r"Error Log [a-z0-9]+:", "", sanitized_message)
            sanitized_message = re.sub(r"\([^)]*Error Log [^)]*\)", "", sanitized_message)
        
        # Keep track of basic context
        context = f"Document: {doc_name}, Employee: {emp_name}"
        
        # Create a clean message that includes context but avoids nesting
        clean_message = f"{context}\n\nError details: {sanitized_message}"
        
        # Create log with clean title and message
        return frappe.log_error(message=clean_message, title=title)
    except Exception:
        # Fallback to simplest possible logging if the above fails
        try:
            # Simple non-nested message
            return frappe.log_error(message=str(message), title="Tax Calculation Error")
        except Exception:
            # If all else fails, silently fail
            return None


def calculate_tax_components(doc, employee):
    """
    Central entry point for all tax calculations - decides between TER or progressive methods

    Args:
        doc: Salary slip document
        employee: Employee document
    """
    try:
        # Ensure required fields exist
        _ensure_required_fields(doc)
        
        # Initialize total_bpjs to 0 if None to prevent NoneType subtraction error
        if doc.total_bpjs is None:
            doc.total_bpjs = 0

        # Handle NPWP Gabung Suami case
        if (
            hasattr(employee, "gender")
            and employee.gender == "Female"
            and hasattr(employee, "npwp_gabung_suami")
            and cint(employee.get("npwp_gabung_suami"))
        ):
            doc.is_final_gabung_suami = 1
            add_tax_info_to_note(
                doc, "PROGRESSIVE", {"message": "Pajak final digabung dengan NPWP suami"}
            )
            return

        # Calculate Biaya Jabatan (5% of gross, max 500k)
        doc.biaya_jabatan = min(doc.gross_pay * (BIAYA_JABATAN_PERCENT / 100), BIAYA_JABATAN_MAX)

        # Calculate netto income
        doc.netto = doc.gross_pay - doc.biaya_jabatan - doc.total_bpjs

        # Set basic payroll note
        set_basic_payroll_note(doc, employee)

        # For December, always use progressive method as per PMK 168/2023
        if is_december(doc):
            # Force disable TER for December according to PMK 168/2023
            doc.is_using_ter = 0
            calculate_december_pph(doc, employee)
            return

        # Decision logic for other months: determine which tax method to use
        # Check employee override first
        if hasattr(employee, "override_tax_method"):
            # If employee has explicit override to TER
            if employee.override_tax_method == "TER":
                return calculate_monthly_pph_with_ter(doc, employee)
            # If employee has explicit override to Progressive
            elif employee.override_tax_method == "Progressive":
                return calculate_monthly_pph_progressive(doc, employee)

        # No explicit override, use centralized logic to check if should use TER
        use_ter = should_use_ter_method(employee)
        if use_ter:
            return calculate_monthly_pph_with_ter(doc, employee)

        # Default to progressive method
        return calculate_monthly_pph_progressive(doc, employee)

    except Exception as e:
        # Use new error logging function to avoid nesting
        log_tax_error("Tax Calculation", str(e), doc, employee)
        # Use throw for validation failures with simplified message
        frappe.throw(_("Error calculating tax components. Please check error logs."))


def _ensure_required_fields(doc):
    """
    Ensure all required fields for tax calculations exist in the document
    If they don't exist, initialize them with default values.
    
    Args:
        doc: Salary slip document
    """
    # Fields needed for TER calculation
    required_fields = {
        "monthly_gross_for_ter": 0,
        "annual_taxable_amount": 0,
        "ter_rate": 0,
        "ter_category": "",
        "is_using_ter": 0,
        "biaya_jabatan": 0,
        "netto": 0,
        "total_bpjs": 0,
        "koreksi_pph21": 0,
        "is_final_gabung_suami": 0
    }
    
    # Set defaults for missing fields
    for field, default_value in required_fields.items():
        if not hasattr(doc, field) or getattr(doc, field) is None:
            setattr(doc, field, default_value)
            # Try to persist to database if possible
            try:
                doc.db_set(field, default_value, update_modified=False)
            except Exception:
                # If db_set fails, continue with in-memory value
                pass


def calculate_monthly_pph_progressive(doc, employee):
    """
    Calculate PPh 21 using progressive rates - for regular months

    Args:
        doc: Salary slip document
        employee: Employee document
    """
    try:
        # Get PPh 21 Settings with cache
        cache_key = "pph_21_settings"
        pph_settings = get_cached_value(cache_key)

        if pph_settings is None:
            pph_settings = frappe.get_single("PPh 21 Settings")
            # Cache for 1 hour
            cache_value(cache_key, pph_settings, CACHE_MEDIUM)

        # Get PTKP value
        if not hasattr(employee, "status_pajak") or not employee.status_pajak:
            employee.status_pajak = "TK0"  # Default to TK0 if not set
            frappe.msgprint(
                _("Warning: Employee tax status not set, using TK0 as default"), indicator="orange"
            )

        # Get PTKP using centralized function
        ptkp = get_ptkp_amount(employee.status_pajak, pph_settings)

        # Get annual values
        monthly_netto = doc.netto
        annual_netto = monthly_netto * MONTHS_PER_YEAR
        pkp = max(annual_netto - ptkp, 0)

        # Calculate annual PPh using centralized function
        cache_key = f"progressive_tax:{pkp}"
        tax_result = get_cached_value(cache_key)

        if tax_result is None:
            annual_pph, tax_details = calculate_progressive_tax(pkp, pph_settings)
            tax_result = {"annual_pph": annual_pph, "tax_details": tax_details}
            # Cache for 1 hour
            cache_value(cache_key, tax_result, CACHE_MEDIUM)
        else:
            annual_pph = tax_result["annual_pph"]
            tax_details = tax_result["tax_details"]

        # Calculate monthly PPh
        monthly_pph = annual_pph / MONTHS_PER_YEAR

        # Update PPh 21 component
        update_component_amount(doc, "PPh 21", monthly_pph, "deductions")

        # Add tax info to note using centralized function
        add_tax_info_to_note(
            doc,
            "PROGRESSIVE",
            {
                "status_pajak": employee.status_pajak,
                "monthly_netto": monthly_netto,
                "annual_netto": annual_netto,
                "ptkp": ptkp,
                "pkp": pkp,
                "tax_details": tax_details,
                "annual_pph": annual_pph,
                "monthly_pph": monthly_pph,
            },
        )

    except Exception as e:
        # Use improved error logging to avoid nesting
        log_tax_error("Progressive Tax", str(e), doc, employee)
        frappe.throw(_("Error calculating PPh 21 with progressive method. See error log."))


def calculate_december_pph(doc, employee):
    """
    Calculate year-end tax correction for December as per PMK 168/2023

    Args:
        doc: Salary slip document
        employee: Employee document
    """
    try:
        year = getdate(doc.end_date).year

        # Get PPh 21 Settings with cache
        cache_key = "pph_21_settings"
        pph_settings = get_cached_value(cache_key)

        if pph_settings is None:
            try:
                pph_settings = frappe.get_single("PPh 21 Settings")
                # Cache for 1 hour
                cache_value(cache_key, pph_settings, CACHE_MEDIUM)
            except Exception as e:
                # Log error and throw with simplified message
                log_tax_error("PPh 21 Settings", str(e), doc, employee)
                frappe.throw(
                    _("PPh 21 Settings not found. Please configure PPh 21 Settings properly.")
                )

        # For December, always use progressive method even if TER is enabled (PMK 168/2023)
        # Get year-to-date totals from tax summary with improved caching
        month = getdate(doc.start_date).month
        cache_key = f"ytd_totals:{doc.employee}:{year}:{month}"
        ytd = get_cached_value(cache_key)

        if ytd is None:
            # Make sure we're passing the right parameters
            ytd = get_ytd_totals_from_tax_summary(doc, year, month)
            # Cache for 30 minutes
            cache_value(cache_key, ytd, CACHE_SHORT)

        # Initialize ytd with default values if not found
        ytd = ytd or {"gross": 0, "bpjs": 0, "pph21": 0}

        # Calculate annual totals
        annual_gross = ytd.get("gross", 0) + doc.gross_pay
        annual_bpjs = ytd.get("bpjs", 0) + doc.total_bpjs

        # Biaya Jabatan is 5% of annual gross, max 500k/year according to regulations
        annual_biaya_jabatan = min(annual_gross * (BIAYA_JABATAN_PERCENT / 100), BIAYA_JABATAN_MAX)
        annual_netto = annual_gross - annual_biaya_jabatan - annual_bpjs

        # Get PTKP value using centralized function
        if not hasattr(employee, "status_pajak") or not employee.status_pajak:
            employee.status_pajak = "TK0"  # Default to TK0 if not set
            frappe.msgprint(
                _("Warning: Employee tax status not set, using TK0 as default"), indicator="orange"
            )

        ptkp = get_ptkp_amount(employee.status_pajak, pph_settings)
        pkp = max(annual_netto - ptkp, 0)

        # Calculate annual PPh using centralized function
        tax_cache_key = f"progressive_tax:{pkp}"
        tax_result = get_cached_value(tax_cache_key)

        if tax_result is None:
            annual_pph, tax_details = calculate_progressive_tax(pkp, pph_settings)
            tax_result = {"annual_pph": annual_pph, "tax_details": tax_details}
            # Cache for 1 hour
            cache_value(tax_cache_key, tax_result, CACHE_MEDIUM)
        else:
            annual_pph = tax_result["annual_pph"]
            tax_details = tax_result["tax_details"]

        # Calculate correction
        correction = annual_pph - ytd.get("pph21", 0)
        doc.koreksi_pph21 = correction

        # Update December PPh 21
        update_component_amount(doc, "PPh 21", correction, "deductions")

        # Add tax info to note with special December data using centralized function
        add_tax_info_to_note(
            doc,
            "PROGRESSIVE_DECEMBER",
            {
                "status_pajak": employee.status_pajak,
                "annual_gross": annual_gross,
                "annual_biaya_jabatan": annual_biaya_jabatan,
                "annual_bpjs": annual_bpjs,
                "annual_netto": annual_netto,
                "ptkp": ptkp,
                "pkp": pkp,
                "tax_details": tax_details,
                "annual_pph": annual_pph,
                "ytd_pph": ytd.get("pph21", 0),
                "correction": correction,
            },
        )

    except Exception as e:
        # Use improved error logging
        log_tax_error("December PPh", str(e), doc, employee)
        frappe.throw(_("Error calculating December PPh 21 correction. See error log."))


def set_basic_payroll_note(doc, employee):
    """
    Set basic payroll note with component details

    Args:
        doc: Salary slip document
        employee: Employee document
    """
    try:
        # Check if payroll_note already has content
        if hasattr(doc, "payroll_note") and doc.payroll_note:
            # Don't overwrite existing note, add to it
            return

        # Ensure status_pajak exists
        status_pajak = (
            employee.status_pajak
            if hasattr(employee, "status_pajak") and employee.status_pajak
            else "TK0"
        )

        # Format monetary values for better readability
        gross_pay_formatted = "{:,.0f}".format(doc.gross_pay) if hasattr(doc, "gross_pay") else "0"
        biaya_jabatan_formatted = "{:,.0f}".format(doc.biaya_jabatan) if hasattr(doc, "biaya_jabatan") else "0"
        total_bpjs_formatted = "{:,.0f}".format(doc.total_bpjs) if hasattr(doc, "total_bpjs") else "0"
        netto_formatted = "{:,.0f}".format(doc.netto) if hasattr(doc, "netto") else "0"

        doc.payroll_note = "\n".join(
            [
                "<!-- BASIC_INFO_START -->",
                "=== Informasi Dasar ===",
                f"Status Pajak: {status_pajak}",
                f"Penghasilan Bruto: Rp {gross_pay_formatted}",
                f"Biaya Jabatan: Rp {biaya_jabatan_formatted}",
                f"BPJS (JHT+JP+Kesehatan): Rp {total_bpjs_formatted}",
                f"Penghasilan Neto: Rp {netto_formatted}",
                "<!-- BASIC_INFO_END -->",
            ]
        )
    except Exception as e:
        # This is not a critical error - the note is mostly informational
        # Use simpler error logging to avoid nested errors
        log_tax_error("Payroll Note", str(e), doc, employee)
        
        # Just set a basic note
        doc.payroll_note = f"Penghasilan Bruto: Rp {doc.gross_pay:,.0f}"
        
        # Inform the user but don't block processing
        frappe.msgprint(_("Warning: Could not set detailed payroll note."), indicator="orange")


def is_december(doc):
    """
    Check if salary slip is for December

    Args:
        doc: Salary slip document

    Returns:
        bool: True if the salary slip is for December
    """
    try:
        if hasattr(doc, "end_date") and doc.end_date:
            return getdate(doc.end_date).month == DECEMBER_MONTH
        return False
    except Exception as e:
        # Non-critical error - log with simpler method and default to False
        log_tax_error("Date Check", str(e), doc)
        return False


def get_ytd_totals(doc, year):
    """
    Get year-to-date totals for the employee (legacy method)

    Args:
        doc: Salary slip document
        year: The tax year

    Returns:
        dict: A dictionary with YTD values
    """
    try:
        # Create a default result with zeros
        result = {"gross": 0, "bpjs": 0, "pph21": 0}

        # Validate input parameters
        if not doc or not hasattr(doc, "employee") or not doc.employee:
            return result

        # Validate year
        if not year or not isinstance(year, int):
            if hasattr(doc, "end_date") and doc.end_date:
                year = getdate(doc.end_date).year
            else:
                return result

        # Check cache for this computation
        cache_key = f"ytd_traditional:{doc.employee}:{year}:{getdate(doc.start_date).month if hasattr(doc, 'start_date') else 1}"
        cached_result = get_cached_value(cache_key)

        if cached_result is not None:
            return cached_result

        # Get salary slips for the current employee in the current year
        # but before the current month using efficient query
        try:
            if not hasattr(doc, "start_date") or not doc.start_date:
                return result
                
            salary_slips = frappe.db.sql(
                """
                SELECT
                    name,
                    gross_pay
                FROM
                    `tabSalary Slip`
                WHERE
                    employee = %s
                    AND YEAR(start_date) = %s
                    AND start_date < %s
                    AND docstatus = 1
            """,
                (doc.employee, year, doc.start_date),
                as_dict=1,
            )
            
            # Sum up the values
            for slip in salary_slips:
                try:
                    # Add to gross
                    result["gross"] += flt(slip.gross_pay)

                    # Get BPJS and PPh 21 components in a more efficient way
                    components = frappe.db.sql(
                        """
                        SELECT
                            salary_component,
                            amount
                        FROM
                            `tabSalary Detail`
                        WHERE
                            parent = %s
                            AND parentfield = 'deductions'
                            AND salary_component IN ('BPJS JHT Employee', 'BPJS JP Employee', 'BPJS Kesehatan Employee', 'PPh 21')
                    """,
                        slip.name,
                        as_dict=1,
                    )

                    for comp in components:
                        if comp.salary_component == "PPh 21":
                            result["pph21"] += flt(comp.amount)
                        else:
                            result["bpjs"] += flt(comp.amount)

                except Exception:
                    # Continue with next slip on error
                    continue

            # Cache the result for 30 minutes
            cache_value(cache_key, result, CACHE_SHORT)
            
        except Exception:
            # Return default result on database error
            frappe.msgprint(
                _("Warning: Could not retrieve previous salary slips. YTD calculations may be incorrect."),
                indicator="orange"
            )
            
        return result

    except Exception as e:
        # Non-critical error - use simple log and return zeros
        log_tax_error("YTD Totals", str(e), doc)
        
        # Inform the user but don't block processing
        frappe.msgprint(
            _("Warning: Error calculating YTD totals. Using zero values as fallback."),
            indicator="orange"
        )
        
        # Return empty result on error
        return {"gross": 0, "bpjs": 0, "pph21": 0}
