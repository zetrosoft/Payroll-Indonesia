# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 15:01:13 by dannyaudianlanjutkan

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
from frappe.utils import flt, getdate, cint, now_datetime

from .base import update_component_amount, get_component_amount

# Import TER calculation function from ter_calculator
from payroll_indonesia.override.salary_slip.ter_calculator import calculate_monthly_pph_with_ter

# Import YTD functions from ter_calculator for backward compatibility
from payroll_indonesia.override.salary_slip.ter_calculator import get_ytd_totals_from_tax_summary

# Import standardized cache utilities
from payroll_indonesia.utilities.cache_utils import get_cached_value, cache_value, clear_cache

# Import constants
from payroll_indonesia.constants import (
    MONTHS_PER_YEAR,
    CACHE_SHORT,
    CACHE_LONG,
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
from payroll_indonesia.payroll_indonesia.tax.pph_ter import map_ptkp_to_ter_category


def calculate_tax_components(doc, employee):
    """
    Central entry point for all tax calculations - decides between TER or progressive methods

    Args:
        doc: Salary slip document
        employee: Employee document
    """
    try:
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
        # This is a critical error in the main tax calculation function
        frappe.log_error(
            "Tax Calculation Error for Employee {0}: {1}".format(
                employee.name if hasattr(employee, "name") else "unknown", str(e)
            ),
            "Tax Calculation Error",
        )
        # Use throw for validation failures
        frappe.throw(_("Error calculating tax components: {0}").format(str(e)))


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
        # This is a critical error in a tax calculation function
        frappe.log_error(
            "Progressive Tax Calculation Error for Employee {0}: {1}".format(
                employee.name if hasattr(employee, "name") else "unknown", str(e)
            ),
            "Progressive Tax Calculation Error",
        )
        frappe.throw(_("Error calculating PPh 21 with progressive method: {0}").format(str(e)))


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
                # This is a critical validation error - can't proceed without settings
                frappe.log_error(
                    "Error retrieving PPh 21 Settings: {0}".format(str(e)),
                    "December PPh Settings Error",
                )
                frappe.throw(
                    _(
                        "Error retrieving PPh 21 Settings: {0}. Please configure PPh 21 Settings properly."
                    ).format(str(e))
                )

        # For December, always use progressive method even if TER is enabled (PMK 168/2023)
        # Get year-to-date totals from tax summary with improved caching
        month = getdate(doc.start_date).month
        cache_key = f"ytd_totals:{doc.employee}:{year}:{month}"
        ytd = get_cached_value(cache_key)

        if ytd is None:
            ytd = get_ytd_totals_from_tax_summary(doc, year)
            # Cache for 30 minutes
            cache_value(cache_key, ytd, CACHE_SHORT)

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
        # This is a critical error in a tax calculation function
        frappe.log_error(
            "December PPh Calculation Error for Employee {0}: {1}".format(
                employee.name if hasattr(employee, "name") else "unknown", str(e)
            ),
            "December PPh Error",
        )
        frappe.throw(_("Error calculating December PPh 21 correction: {0}").format(str(e)))


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

        status_pajak = (
            employee.status_pajak
            if hasattr(employee, "status_pajak") and employee.status_pajak
            else "TK0"
        )

        doc.payroll_note = "\n".join(
            [
                "<!-- BASIC_INFO_START -->",
                "=== Informasi Dasar ===",
                f"Status Pajak: {status_pajak}",
                f"Penghasilan Bruto: Rp {doc.gross_pay:,.0f}",
                f"Biaya Jabatan: Rp {doc.biaya_jabatan:,.0f}",
                f"BPJS (JHT+JP+Kesehatan): Rp {doc.total_bpjs:,.0f}",
                f"Penghasilan Neto: Rp {doc.netto:,.0f}",
                "<!-- BASIC_INFO_END -->",
            ]
        )
    except Exception as e:
        # This is not a critical error - the note is mostly informational
        frappe.log_error(
            "Error setting basic payroll note for {0}: {1}".format(doc.employee, str(e)),
            "Payroll Note Error",
        )
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
        return getdate(doc.end_date).month == DECEMBER_MONTH
    except Exception as e:
        # Non-critical error - log and default to False
        frappe.log_error(
            "Error checking if salary slip {0} is for December: {1}".format(
                doc.name if hasattr(doc, "name") else "unknown", str(e)
            ),
            "Date Check Error",
        )
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

        # Validate year
        if not year or not isinstance(year, int):
            year = getdate(doc.end_date).year

        # Validate employee
        if not doc.employee:
            return result

        # Check cache for this computation
        cache_key = f"ytd_traditional:{doc.employee}:{year}:{getdate(doc.start_date).month}"
        cached_result = get_cached_value(cache_key)

        if cached_result is not None:
            return cached_result

        # Get salary slips for the current employee in the current year
        # but before the current month using efficient query
        try:
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
        except Exception as e:
            # Non-critical database error - we can return zeros
            frappe.log_error(
                "Error querying salary slips for {0}: {1}".format(doc.employee, str(e)),
                "Salary Slip Query Error",
            )
            frappe.msgprint(
                _(
                    "Warning: Could not retrieve previous salary slips. YTD calculations may be incorrect."
                ),
                indicator="red",
            )
            return result

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

            except Exception as e:
                # Non-critical error processing a salary slip - continue with next one
                frappe.log_error(
                    "Error processing Salary Slip {0}: {1}".format(slip.name, str(e)),
                    "Salary Slip Processing Error",
                )
                continue

        # Cache the result for 30 minutes
        cache_value(cache_key, result, CACHE_SHORT)
        return result

    except Exception as e:
        # Non-critical error - we can return zeros
        frappe.log_error(
            "Error calculating YTD totals for {0}: {1}".format(doc.employee, str(e)),
            "YTD Totals Error",
        )
        frappe.msgprint(
            _("Error calculating YTD totals: {0}. Using zero values as fallback.").format(str(e)),
            indicator="red",
        )
        # Return empty result on error
        return {"gross": 0, "bpjs": 0, "pph21": 0}
