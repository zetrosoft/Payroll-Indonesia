# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 16:28:44 by dannyaudian

"""
Core TER and tax calculation logic for Indonesian payroll.

This module contains the core business logic for:
1. TER rate determination and calculation
2. Progressive tax calculation
3. Annual tax calculation
4. PTKP mapping and lookup
5. Tax bracket processing

These functions are kept independent of UI/document manipulation
and can be imported by other modules without causing circular dependencies.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

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
    CURRENCY_PRECISION,
    BIAYA_JABATAN_PERCENT,
    BIAYA_JABATAN_MAX,
    TAX_DETECTION_THRESHOLD,
    ANNUAL_DETECTION_FACTOR,
    SALARY_BASIC_FACTOR,
)

# Import TER category mapping from pph_ter (single source of truth)
from payroll_indonesia.payroll_indonesia.tax.pph_ter import map_ptkp_to_ter_category


def calculate_progressive_tax(pkp, pph_settings=None):
    """
    Calculate tax using progressive rates

    Args:
        pkp: Penghasilan Kena Pajak (taxable income)
        pph_settings: PPh 21 Settings document (optional)

    Returns:
        tuple: (total_tax, tax_details)
    """
    try:
        # Validate input
        if pkp < 0:
            frappe.log_error(
                "Negative PKP value {0} provided, using 0 instead".format(pkp),
                "PKP Validation Warning",
            )
            pkp = 0

        # Get settings
        if not pph_settings and frappe.db.exists("DocType", "PPh 21 Settings"):
            try:
                pph_settings = frappe.get_cached_doc("PPh 21 Settings")
            except Exception as settings_error:
                frappe.log_error(
                    "Error retrieving PPh 21 Settings: {0}".format(str(settings_error)),
                    "Settings Retrieval Warning",
                )
                pph_settings = None

        # First check if bracket_table is directly available as attribute
        bracket_table = []
        if pph_settings and hasattr(pph_settings, "bracket_table"):
            bracket_table = pph_settings.bracket_table

        # If not found or empty, query from database
        if not bracket_table and pph_settings:
            bracket_table = frappe.db.sql(
                """
                SELECT income_from, income_to, tax_rate
                FROM `tabPPh 21 Tax Bracket`
                WHERE parent = 'PPh 21 Settings'
                ORDER BY income_from ASC
            """,
                as_dict=1,
            )

        # If still not found, use default values
        if not bracket_table:
            # Log warning about missing brackets
            frappe.log_error(
                "No tax brackets found in settings, using default values", "Tax Bracket Warning"
            )

            # Default bracket values if not found - based on PMK 101/2016 and UU HPP 2021
            bracket_table = [
                {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
                {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
                {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
                {"income_from": 5000000000, "income_to": 0, "tax_rate": 35},
            ]

        # Calculate tax using progressive rates
        total_tax = 0
        tax_details = []
        remaining_pkp = pkp

        for bracket in sorted(bracket_table, key=lambda x: flt(x.get("income_from", 0))):
            if remaining_pkp <= 0:
                break

            income_from = flt(bracket.get("income_from", 0))
            income_to = flt(bracket.get("income_to", 0))
            tax_rate = flt(bracket.get("tax_rate", 0))

            # Handle unlimited upper bracket
            upper_limit = income_to if income_to > 0 else float("inf")
            lower_limit = income_from
            taxable = min(remaining_pkp, upper_limit - lower_limit)

            tax = taxable * (tax_rate / 100)
            total_tax += tax

            if tax > 0:
                tax_details.append({"rate": tax_rate, "taxable": taxable, "tax": tax})

            remaining_pkp -= taxable

        return total_tax, tax_details

    except Exception as e:
        # Non-critical error - log and return default values
        frappe.log_error(
            "Error calculating progressive tax for PKP {0}: {1}".format(pkp, str(e)),
            "Tax Bracket Calculation Error",
        )
        raise


def get_ptkp_amount(status_pajak, pph_settings=None):
    """
    Get PTKP amount based on tax status from PPh 21 Settings or defaults

    Args:
        status_pajak: Tax status code (e.g., 'TK0', 'K1', etc.)
        pph_settings: PPh 21 Settings document (optional)

    Returns:
        float: PTKP amount
    """
    try:
        # Validate input
        if not status_pajak:
            frappe.log_error("Empty tax status provided, using TK0 as default", "PTKP Warning")
            status_pajak = "TK0"

        # Use cache for PTKP amount
        cache_key = f"ptkp_amount:{status_pajak}"
        ptkp_amount = get_cached_value(cache_key)

        if ptkp_amount is not None:
            return ptkp_amount

        # Check if PPh 21 Settings exists
        if not pph_settings and frappe.db.exists("DocType", "PPh 21 Settings"):
            pph_settings = frappe.get_cached_doc("PPh 21 Settings")

        # Get PTKP from settings
        ptkp_table = []
        if pph_settings and hasattr(pph_settings, "ptkp_table"):
            ptkp_table = pph_settings.ptkp_table

        # If not found in cached doc, query from database
        if not ptkp_table and pph_settings:
            ptkp_table = frappe.db.sql(
                """
                SELECT status_pajak as tax_status, ptkp_amount as amount
                FROM `tabPPh 21 PTKP Table`
                WHERE parent = 'PPh 21 Settings'
            """,
                as_dict=1,
            )

        # Find matching status
        for ptkp in ptkp_table:
            if hasattr(ptkp, "tax_status") and ptkp.tax_status == status_pajak:
                ptkp_amount = flt(ptkp.amount)
                cache_value(cache_key, ptkp_amount, CACHE_LONG)
                return ptkp_amount

            # For backward compatibility
            if hasattr(ptkp, "status_pajak") and ptkp.status_pajak == status_pajak:
                ptkp_amount = flt(ptkp.ptkp_amount)
                cache_value(cache_key, ptkp_amount, CACHE_LONG)
                return ptkp_amount

        # If not found, try to match prefix (TK0 -> TK)
        prefix = status_pajak[:2] if len(status_pajak) >= 2 else status_pajak
        for ptkp in ptkp_table:
            ptkp_status = ptkp.tax_status if hasattr(ptkp, "tax_status") else ptkp.status_pajak
            if ptkp_status and ptkp_status.startswith(prefix):
                ptkp_amount = flt(ptkp.amount if hasattr(ptkp, "amount") else ptkp.ptkp_amount)
                cache_value(cache_key, ptkp_amount, CACHE_LONG)
                return ptkp_amount

        # Default values if not found or settings don't exist - based on PMK-101/PMK.010/2016 and updated values
        default_ptkp = {"TK": 54000000, "K": 58500000, "HB": 112500000}  # TK/0  # K/0  # HB/0

        # Return default based on prefix
        for key, value in default_ptkp.items():
            if prefix.startswith(key):
                frappe.log_error(
                    "PTKP not found in settings for {0}, using default value {1}".format(
                        status_pajak, value
                    ),
                    "PTKP Fallback Warning",
                )
                cache_value(cache_key, value, CACHE_LONG)
                return value

        # Last resort - TK0
        default_value = 54000000  # Default for TK0
        frappe.log_error(
            "No PTKP match found for {0}, using TK0 default ({1})".format(
                status_pajak, default_value
            ),
            "PTKP Default Warning",
        )
        cache_value(cache_key, default_value, CACHE_LONG)
        return default_value

    except Exception as e:
        # Non-critical error - log and return default
        frappe.log_error(
            "Error getting PTKP amount for {0}: {1}".format(status_pajak, str(e)),
            "PTKP Calculation Error",
        )
        # Return default PTKP for TK0
        return 54000000


def should_use_ter_method(employee, pph_settings=None):
    """
    Determine if TER method should be used for this employee according to PMK 168/2023

    Args:
        employee: Employee document or dict
        pph_settings: PPh 21 Settings document (optional)

    Returns:
        bool: True if TER should be used, False otherwise
    """
    try:
        # Validate employee parameter
        if not employee:
            return False

        # Employee can be dict or document
        employee_id = (
            employee.name if hasattr(employee, "name") else employee.get("name", "unknown")
        )

        # Check cache first
        cache_key = f"use_ter:{employee_id}"
        cached_result = get_cached_value(cache_key)

        if cached_result is not None:
            return cached_result

        # Get PPh 21 Settings if not provided - use cached value for better performance
        if not pph_settings:
            settings_cache_key = "pph_settings:use_ter"
            pph_settings = get_cached_value(settings_cache_key)

            if pph_settings is None:
                pph_settings = (
                    frappe.get_cached_value(
                        "PPh 21 Settings",
                        "PPh 21 Settings",
                        ["calculation_method", "use_ter"],
                        as_dict=True,
                    )
                    or {}
                )

                # Cache settings for 1 hour
                cache_value(settings_cache_key, pph_settings, CACHE_MEDIUM)

        # Fast path for global TER setting disabled
        if (
            not pph_settings
            or pph_settings.get("calculation_method") != "TER"
            or not pph_settings.get("use_ter")
        ):
            cache_value(cache_key, False, CACHE_MEDIUM)  # Cache for 1 hour
            return False

        # Special cases

        # December always uses Progressive method as per PMK 168/2023
        # Check if current month is December
        current_month = getdate().month
        if current_month == 12:
            cache_value(cache_key, False, CACHE_MEDIUM)  # Cache for 1 hour
            return False

        # Fast path for employee exclusions
        tipe_karyawan = getattr(employee, "tipe_karyawan", None) or employee.get(
            "tipe_karyawan", ""
        )
        override_tax_method = getattr(employee, "override_tax_method", None) or employee.get(
            "override_tax_method", ""
        )

        if tipe_karyawan == "Freelance":
            cache_value(cache_key, False, CACHE_MEDIUM)  # Cache for 1 hour
            return False

        if override_tax_method == "Progressive":
            cache_value(cache_key, False, CACHE_MEDIUM)  # Cache for 1 hour
            return False

        # If we made it here, use TER method
        cache_value(cache_key, True, CACHE_MEDIUM)  # Cache for 1 hour
        return True

    except Exception as e:
        # This is not a validation failure, so log and continue with default behavior
        frappe.log_error(
            "Error determining TER eligibility for {0}: {1}".format(
                (
                    getattr(employee, "name", "unknown")
                    if hasattr(employee, "name")
                    else employee.get("name", "unknown")
                ),
                str(e),
            ),
            "TER Eligibility Error",
        )
        # Default to False on error (use progressive method)
        return False


def hitung_pph_tahunan(employee, year, employee_details=None):
    """
    Calculate annual PPh 21 for an employee with support for both TER and progressive methods.
    This is called by both monthly and yearly tax processes.

    Args:
        employee: Employee ID
        year: Tax year
        employee_details: Pre-fetched employee details (optional)

    Returns:
        dict: Tax calculation data
    """
    try:
        # Get translation function early to avoid F823
        translate = frappe._

        # Validate parameters
        if not employee:
            frappe.throw(
                translate("Employee ID is required for annual PPh calculation"),
                title=translate("Missing Parameter"),
            )

        if not year:
            frappe.throw(
                translate("Tax year is required for annual PPh calculation"),
                title=translate("Missing Parameter"),
            )

        # Get employee document if not provided
        emp_doc = employee_details or None
        if not emp_doc:
            try:
                emp_doc = frappe.get_doc("Employee", employee)
            except Exception as e:
                frappe.throw(
                    translate("Error retrieving employee {0}: {1}").format(employee, str(e)),
                    title=translate("Employee Not Found"),
                )

        # Get all salary slips for the year
        salary_slips = frappe.db.get_all(
            "Salary Slip",
            filters={
                "employee": employee,
                "docstatus": 1,
                "start_date": ["between", [f"{year}-01-01", f"{year}-12-31"]],
            },
            fields=[
                "name",
                "gross_pay",
                "total_bpjs",
                "start_date",
                "is_using_ter",
                "ter_rate",
                "ter_category",
            ],
            order_by="start_date asc",
        )

        if not salary_slips:
            return {
                "annual_income": 0,
                "biaya_jabatan": 0,
                "bpjs_total": 0,
                "annual_net": 0,
                "ptkp": 0,
                "pkp": 0,
                "already_paid": 0,
                "annual_tax": 0,
                "ter_used": False,
            }

        # Calculate annual totals
        annual_income = sum(flt(slip.gross_pay) for slip in salary_slips)
        bpjs_total = sum(flt(slip.total_bpjs) for slip in salary_slips)

        # Calculate biaya jabatan (job allowance)
        # 5% of annual income, max 500k per year
        biaya_jabatan = min(annual_income * (BIAYA_JABATAN_PERCENT / 100), BIAYA_JABATAN_MAX)

        # Calculate annual net income
        annual_net = annual_income - biaya_jabatan - bpjs_total

        # Get PTKP value based on employee's tax status
        status_pajak = (
            getattr(emp_doc, "status_pajak", None) or emp_doc.get("status_pajak", "TK0")
            if emp_doc
            else "TK0"
        )
        ptkp = get_ptkp_amount(status_pajak)

        # Calculate PKP (taxable income)
        pkp = max(annual_net - ptkp, 0)

        # Check if TER was used in any month
        ter_used = any(
            getattr(slip, "is_using_ter", 0) or slip.get("is_using_ter", 0) for slip in salary_slips
        )

        # Calculate tax paid during the year
        already_paid = calculate_tax_already_paid(salary_slips)

        # Calculate annual tax using progressive method (always used for annual calculation)
        annual_tax, _ = calculate_progressive_tax(pkp)

        # Determine most common TER category if TER was used
        ter_categories = []
        for slip in salary_slips:
            ter_category = getattr(slip, "ter_category", None) or slip.get("ter_category", "")
            if (getattr(slip, "is_using_ter", 0) or slip.get("is_using_ter", 0)) and ter_category:
                ter_categories.append(ter_category)

        ter_category = ""
        if ter_categories:
            # Get the most common category
            from collections import Counter

            category_counts = Counter(ter_categories)
            ter_category = category_counts.most_common(1)[0][0]

        # If TER wasn't used but we have status_pajak, determine TER category
        if not ter_category and status_pajak:
            ter_category = map_ptkp_to_ter_category(status_pajak)

        return {
            "annual_income": annual_income,
            "biaya_jabatan": biaya_jabatan,
            "bpjs_total": bpjs_total,
            "annual_net": annual_net,
            "ptkp": ptkp,
            "pkp": pkp,
            "already_paid": already_paid,
            "annual_tax": annual_tax,
            "ter_used": ter_used,
            "ter_category": ter_category,
        }

    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise

        # For other errors, log and re-raise with clear message
        frappe.log_error(
            "Error calculating annual PPh for {0}, year {1}: {2}".format(employee, year, str(e)),
            "Annual PPh Calculation Error",
        )
        raise


def calculate_tax_already_paid(salary_slips):
    """
    Calculate total tax already paid in the given salary slips

    Args:
        salary_slips: List of salary slips

    Returns:
        float: Total tax already paid
    """
    # Initialize total
    total_tax = 0

    try:
        # Get slip names for efficient querying
        slip_names = [slip.name for slip in salary_slips]

        if not slip_names:
            return 0

        # Get PPh 21 component amounts in bulk
        tax_components = frappe.db.sql(
            """
            SELECT parent, amount
            FROM `tabSalary Detail`
            WHERE
                parent IN %s
                AND parentfield = 'deductions'
                AND salary_component = 'PPh 21'
        """,
            [tuple(slip_names)],
            as_dict=1,
        )

        # Sum up tax amounts
        for comp in tax_components:
            total_tax += flt(comp.amount)

    except Exception as e:
        # Non-critical error - log, show warning and return 0
        frappe.log_error(
            "Error calculating already paid tax: {0}".format(str(e)), "Tax Calculation Warning"
        )

    return total_tax


def detect_annual_income(gross_pay, total_earnings=0, basic_salary=0, bypass_detection=False):
    """
    Detect if a gross pay value appears to be annual rather than monthly

    Args:
        gross_pay: The gross pay amount to check
        total_earnings: Sum of all earnings components (optional)
        basic_salary: Basic salary component amount (optional)
        bypass_detection: Flag to bypass detection logic

    Returns:
        tuple: (is_annual, reason, monthly_equivalent)
    """
    if bypass_detection:
        return False, "", gross_pay

    is_annual = False
    reason = ""
    monthly_gross_pay = gross_pay  # Default to original value

    # Deteksi berdasarkan total earnings
    if total_earnings > 0 and flt(gross_pay) > (total_earnings * ANNUAL_DETECTION_FACTOR):
        is_annual = True
        reason = f"Gross pay ({gross_pay}) exceeds {ANNUAL_DETECTION_FACTOR}x total earnings ({total_earnings})"
        monthly_gross_pay = total_earnings

    # Deteksi nilai terlalu besar
    elif flt(gross_pay) > TAX_DETECTION_THRESHOLD:
        is_annual = True
        reason = f"Gross pay exceeds {TAX_DETECTION_THRESHOLD} (likely annual)"
        monthly_gross_pay = flt(gross_pay / MONTHS_PER_YEAR)

    # Deteksi berdasarkan basic salary
    elif basic_salary > 0 and flt(gross_pay) > (basic_salary * SALARY_BASIC_FACTOR):
        is_annual = True
        reason = f"Gross pay exceeds {SALARY_BASIC_FACTOR}x basic salary ({basic_salary})"
        monthly_gross_pay = (
            flt(gross_pay / MONTHS_PER_YEAR)
            if 11 < (gross_pay / basic_salary) < 13
            else total_earnings or (gross_pay / MONTHS_PER_YEAR)
        )

    return is_annual, reason, monthly_gross_pay


# Define common function used for tax information display
def add_tax_info_to_note(doc, tax_method, values):
    """
    Add tax calculation details to payroll note with consistent formatting and
    section management to avoid duplication.

    Args:
        doc: Salary slip document
        tax_method: "PROGRESSIVE", "TER", or "PROGRESSIVE_DECEMBER"
        values: Dictionary with calculation values
    """
    try:
        # Initialize payroll_note if needed
        if not hasattr(doc, "payroll_note"):
            doc.payroll_note = ""
        elif doc.payroll_note is None:
            doc.payroll_note = ""

        # Check if Tax calculation section already exists and remove it if found
        start_marker = "<!-- TAX_CALCULATION_START -->"
        end_marker = "<!-- TAX_CALCULATION_END -->"

        if start_marker in doc.payroll_note and end_marker in doc.payroll_note:
            start_idx = doc.payroll_note.find(start_marker)
            end_idx = doc.payroll_note.find(end_marker) + len(end_marker)

            # Remove the existing section
            doc.payroll_note = doc.payroll_note[:start_idx] + doc.payroll_note[end_idx:]

        # Add new tax calculation with section markers
        note_content = [
            "\n\n<!-- TAX_CALCULATION_START -->",
        ]

        if tax_method == "TER":
            # TER method - Used by ter_calculator.py
            status_pajak = values.get("status_pajak", "TK0")
            ter_category = values.get("ter_category", "")
            mapping_info = f" → {ter_category}" if ter_category else ""

            note_content.extend(
                [
                    "=== Perhitungan PPh 21 dengan TER ===",
                    f"Status Pajak: {status_pajak}{mapping_info}",
                    f"Penghasilan Bruto: Rp {values.get('gross_pay', 0):,.0f}",
                    f"Tarif Efektif Rata-rata: {values.get('ter_rate', 0):.2f}%",
                    f"PPh 21 Sebulan: Rp {values.get('monthly_tax', 0):,.0f}",
                    "",
                    "Sesuai PMK 168/2023 tentang Tarif Efektif Rata-rata",
                ]
            )

        elif tax_method == "PROGRESSIVE_DECEMBER":
            # Progressive method for December with year-end correction
            note_content.extend(
                [
                    "=== Perhitungan PPh 21 Tahunan (Desember) ===",
                    f"Penghasilan Bruto Setahun: Rp {values.get('annual_gross', 0):,.0f}",
                    f"Biaya Jabatan: Rp {values.get('annual_biaya_jabatan', 0):,.0f}",
                    f"Total BPJS: Rp {values.get('annual_bpjs', 0):,.0f}",
                    f"Penghasilan Neto: Rp {values.get('annual_netto', 0):,.0f}",
                    f"PTKP ({values.get('status_pajak', 'TK0')}): Rp {values.get('ptkp', 0):,.0f}",
                    f"PKP: Rp {values.get('pkp', 0):,.0f}",
                    "",
                    "Perhitungan Per Lapisan Pajak:",
                ]
            )

            # Add tax bracket details if available
            tax_details = values.get("tax_details", [])
            if tax_details:
                for d in tax_details:
                    rate = flt(d.get("rate", 0))
                    taxable = flt(d.get("taxable", 0))
                    tax = flt(d.get("tax", 0))
                    note_content.append(
                        f"- Lapisan {rate:.0f}%: "
                        f"Rp {taxable:,.0f} × {rate:.0f}% = "
                        f"Rp {tax:,.0f}"
                    )
            else:
                note_content.append("- (Tidak ada rincian pajak)")

            # Add summary values
            annual_pph = flt(values.get("annual_pph", 0))
            ytd_pph = flt(values.get("ytd_pph", 0))
            correction = flt(values.get("correction", 0))

            note_content.extend(
                [
                    "",
                    f"Total PPh 21 Setahun: Rp {annual_pph:,.0f}",
                    f"PPh 21 Sudah Dibayar: Rp {ytd_pph:,.0f}",
                    f"Koreksi Desember: Rp {correction:,.0f}",
                    f"({'Kurang Bayar' if correction > 0 else 'Lebih Bayar'})",
                    "",
                    "Metode perhitungan Desember menggunakan metode progresif sesuai PMK 168/2023",
                ]
            )

        elif tax_method == "PROGRESSIVE":
            # Regular progressive method for non-December months
            note_content.extend(
                [
                    "=== Perhitungan PPh 21 dengan Metode Progresif ===",
                    f"Status Pajak: {values.get('status_pajak', 'TK0')}",
                    f"Penghasilan Neto Sebulan: Rp {values.get('monthly_netto', 0):,.0f}",
                    f"Penghasilan Neto Setahun: Rp {values.get('annual_netto', 0):,.0f}",
                    f"PTKP: Rp {values.get('ptkp', 0):,.0f}",
                    f"PKP: Rp {values.get('pkp', 0):,.0f}",
                    "",
                    "PPh 21 Tahunan:",
                ]
            )

            # Add tax bracket details if available
            tax_details = values.get("tax_details", [])
            if tax_details:
                for d in tax_details:
                    rate = flt(d.get("rate", 0))
                    taxable = flt(d.get("taxable", 0))
                    tax = flt(d.get("tax", 0))
                    note_content.append(
                        f"- Lapisan {rate:.0f}%: "
                        f"Rp {taxable:,.0f} × {rate:.0f}% = "
                        f"Rp {tax:,.0f}"
                    )
            else:
                note_content.append("- (Tidak ada rincian pajak)")

            # Add monthly PPh
            annual_pph = flt(values.get("annual_pph", 0))
            monthly_pph = flt(values.get("monthly_pph", 0))
            note_content.extend(
                [
                    "",
                    f"Total PPh 21 Setahun: Rp {annual_pph:,.0f}",
                    f"PPh 21 Sebulan: Rp {monthly_pph:,.0f}",
                ]
            )

        else:
            # Simple message (e.g., for NPWP Gabung Suami case)
            if "message" in values:
                note_content.extend(["=== Informasi Pajak ===", values.get("message", "")])
            else:
                note_content.extend(
                    ["=== Informasi Pajak ===", "Tidak ada perhitungan PPh 21 yang dilakukan."]
                )

        # Add end marker
        note_content.append("<!-- TAX_CALCULATION_END -->")

        # Add the formatted note to payroll_note
        doc.payroll_note += "\n" + "\n".join(note_content)

    except Exception as e:
        # This is not a critical error - we can continue without adding notes
        frappe.log_error("Error adding tax info to note: {0}".format(str(e)), "Tax Note Error")
        # Add a simple note to indicate there was an error
        if hasattr(doc, "payroll_note"):
            doc.payroll_note += "\n\nWarning: Could not add detailed tax calculation notes."
