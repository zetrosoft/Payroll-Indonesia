# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 10:11:30 by dannyaudianlanjutkan

import frappe
from frappe import _
from frappe.utils import flt, getdate, cint, now_datetime
import hashlib

from .base import update_component_amount

# Import the newly created add_tax_info_to_note function from tax_calculator
from .tax_calculator import add_tax_info_to_note

# Import mapping function from pph_ter.py
from payroll_indonesia.payroll_indonesia.tax.pph_ter import map_ptkp_to_ter_category

# Import cache utilities
from payroll_indonesia.payroll_indonesia.utilities.cache_utils import get_cached_value, cache_value, clear_cache

# Import constants
from payroll_indonesia.constants import (
    MONTHS_PER_YEAR, CACHE_SHORT, CACHE_LONG, ANNUAL_DETECTION_FACTOR,
    SALARY_BASIC_FACTOR, TAX_DETECTION_THRESHOLD, CACHE_MEDIUM,
    TER_CATEGORY_A, TER_CATEGORY_B, TER_CATEGORY_C, TER_CATEGORIES,
    TER_MAX_RATE, CURRENCY_PRECISION
)

def calculate_monthly_pph_with_ter(doc, employee):
    """Calculate PPh 21 using TER method based on PMK 168/2023"""
    try:
        # Simpan nilai awal untuk verifikasi
        original_values = {
            'gross_pay': flt(doc.gross_pay),
            'monthly_gross_for_ter': flt(getattr(doc, 'monthly_gross_for_ter', 0)),
            'annual_taxable_amount': flt(getattr(doc, 'annual_taxable_amount', 0)),
            'ter_rate': flt(getattr(doc, 'ter_rate', 0)),
            'ter_category': getattr(doc, 'ter_category', '')
        }

        # Use consistent logging format
        frappe.log_error("[TER] Starting calculation for {0}".format(doc.name), "TER Debug")
        frappe.log_error("[TER] Original values: {0}".format(original_values), "TER Debug")

        # Validate employee status_pajak
        if not hasattr(employee, 'status_pajak') or not employee.status_pajak:
            employee.status_pajak = "TK0"
            frappe.msgprint(_("Warning: Employee tax status not set, using TK0 as default"))

        # PENTING: Gunakan monthly_gross_for_ter untuk perhitungan
        monthly_gross_pay = flt(doc.gross_pay)  # Start with gross_pay
        is_annual = False
        reason = ""

        # Deteksi nilai tahunan jika tidak di-bypass
        if not getattr(doc, 'bypass_annual_detection', 0):
            # Hitung total earnings jika tersedia
            total_earnings = flt(sum(flt(e.amount) for e in doc.earnings)) if hasattr(doc, 'earnings') and doc.earnings else 0
            
            # Deteksi berdasarkan total earnings
            if total_earnings > 0 and flt(doc.gross_pay) > (total_earnings * ANNUAL_DETECTION_FACTOR):
                is_annual = True
                reason = f"Gross pay ({doc.gross_pay}) exceeds {ANNUAL_DETECTION_FACTOR}x total earnings ({total_earnings})"
                monthly_gross_pay = total_earnings
            
            # Deteksi nilai terlalu besar
            elif flt(doc.gross_pay) > TAX_DETECTION_THRESHOLD:
                is_annual = True
                reason = f"Gross pay exceeds {TAX_DETECTION_THRESHOLD} (likely annual)"
                monthly_gross_pay = flt(doc.gross_pay / MONTHS_PER_YEAR)

            # Deteksi berdasarkan basic salary
            elif hasattr(doc, 'earnings'):
                basic_salary = next(
                    (flt(e.amount) for e in doc.earnings 
                     if e.salary_component in ["Gaji Pokok", "Basic Salary", "Basic Pay"]), 
                    0
                )
                if basic_salary > 0 and flt(doc.gross_pay) > (basic_salary * SALARY_BASIC_FACTOR):
                    is_annual = True
                    reason = f"Gross pay exceeds {SALARY_BASIC_FACTOR}x basic salary ({basic_salary})"
                    monthly_gross_pay = (
                        flt(doc.gross_pay / MONTHS_PER_YEAR) 
                        if 11 < (doc.gross_pay / basic_salary) < 13
                        else total_earnings
                    )

        # Log deteksi nilai tahunan
        if is_annual:
            # Replace logger with standard log_error
            frappe.log_error(
                "[TER] {0}: Detected annual value - {1}. Adjusted from {2} to monthly {3}".format(
                    doc.name, reason, doc.gross_pay, monthly_gross_pay
                ),
                "TER Annual Value Detection"
            )
            
            if hasattr(doc, 'payroll_note'):
                doc.payroll_note += f"\n[TER] {reason}. Using monthly value: {monthly_gross_pay}"

        # Set dan simpan nilai bulanan dan tahunan
        annual_taxable_amount = flt(monthly_gross_pay * MONTHS_PER_YEAR)
        
        # Simpan monthly_gross_for_ter
        if hasattr(doc, 'monthly_gross_for_ter'):
            doc.monthly_gross_for_ter = monthly_gross_pay
            doc.db_set('monthly_gross_for_ter', monthly_gross_pay, update_modified=False)
            
        # Simpan annual_taxable_amount
        if hasattr(doc, 'annual_taxable_amount'):
            doc.annual_taxable_amount = annual_taxable_amount
            doc.db_set('annual_taxable_amount', annual_taxable_amount, update_modified=False)

        # Tentukan TER category dan rate
        # Use cache for ter_category
        cache_key = f"ter_category:{employee.status_pajak}"
        ter_category = get_cached_value(cache_key)
        
        if ter_category is None:
            ter_category = map_ptkp_to_ter_category(employee.status_pajak)
            cache_value(cache_key, ter_category, CACHE_LONG)  # Cache for 24 hours
            
        # Use cache for ter_rate
        cache_key = f"ter_rate:{ter_category}:{round(monthly_gross_pay, -3)}"
        ter_rate = get_cached_value(cache_key)
        
        if ter_rate is None:
            ter_rate = flt(get_ter_rate(ter_category, monthly_gross_pay))
            cache_value(cache_key, ter_rate, CACHE_SHORT)  # Cache for 30 minutes
        
        # Hitung PPh 21 bulanan
        monthly_tax = flt(monthly_gross_pay * ter_rate)
        
        # Set dan simpan info TER
        doc.is_using_ter = 1
        doc.ter_rate = flt(ter_rate * 100)
        doc.ter_category = ter_category
        
        # Simpan langsung ke database
        doc.db_set('is_using_ter', 1, update_modified=False)
        doc.db_set('ter_rate', flt(ter_rate * 100), update_modified=False)
        doc.db_set('ter_category', ter_category, update_modified=False)

        # Update komponen PPh 21
        update_component_amount(doc, "PPh 21", monthly_tax, "deductions")

        # Tambahkan catatan ke payroll_note
        if hasattr(doc, 'payroll_note'):
            note = (
                f"\n[TER] Category: {ter_category}, Rate: {ter_rate*100}%, "
                f"Monthly Tax: {monthly_tax}"
            )
            if is_annual:
                note += f"\nAdjusted from annual value: {doc.gross_pay} → monthly: {monthly_gross_pay}"
            doc.payroll_note += note

        # Verifikasi hasil perhitungan
        verify_calculation_integrity(
            doc=doc,
            original_values=original_values,
            monthly_gross_pay=monthly_gross_pay,
            annual_taxable_amount=annual_taxable_amount,
            ter_rate=ter_rate,
            ter_category=ter_category,
            monthly_tax=monthly_tax
        )

        frappe.log_error("[TER] Calculation completed for {0}".format(doc.name), "TER Debug")
        return True

    except Exception as e:
        # Standard error handling pattern: log + throw
        frappe.log_error(
            "Error calculating PPh 21 for {0}: {1}".format(doc.name, str(e)),
            "TER Calculation Error"
        )
        frappe.throw(_("Failed to calculate PPh 21 using TER method: {0}").format(str(e)))

def verify_calculation_integrity(doc, original_values, monthly_gross_pay, 
                               annual_taxable_amount, ter_rate, ter_category, monthly_tax):
    """Verifikasi integritas hasil perhitungan TER"""
    try:
        errors = []
        
        # Verifikasi gross_pay tidak berubah
        if abs(flt(doc.gross_pay) - original_values['gross_pay']) > 0.01:
            errors.append(
                f"gross_pay changed: {original_values['gross_pay']} → {doc.gross_pay}"
            )
            doc.gross_pay = original_values['gross_pay']
            doc.db_set('gross_pay', original_values['gross_pay'], update_modified=False)

        # Verifikasi monthly_gross_for_ter
        if hasattr(doc, 'monthly_gross_for_ter'):
            if abs(flt(doc.monthly_gross_for_ter) - monthly_gross_pay) > 0.01:
                errors.append(
                    f"monthly_gross_for_ter mismatch: expected {monthly_gross_pay}, "
                    f"got {doc.monthly_gross_for_ter}"
                )
                doc.monthly_gross_for_ter = monthly_gross_pay
                doc.db_set('monthly_gross_for_ter', monthly_gross_pay, update_modified=False)

        # Verifikasi annual_taxable_amount
        if hasattr(doc, 'annual_taxable_amount'):
            expected_annual = flt(monthly_gross_pay * MONTHS_PER_YEAR)
            if abs(flt(doc.annual_taxable_amount) - expected_annual) > 0.01:
                errors.append(
                    f"annual_taxable_amount mismatch: expected {expected_annual}, "
                    f"got {doc.annual_taxable_amount}"
                )
                doc.annual_taxable_amount = expected_annual
                doc.db_set('annual_taxable_amount', expected_annual, update_modified=False)

        # Verifikasi nilai TER
        if not doc.is_using_ter:
            errors.append("is_using_ter not set to 1")
            doc.is_using_ter = 1
            doc.db_set('is_using_ter', 1, update_modified=False)

        if abs(flt(doc.ter_rate) - flt(ter_rate * 100)) > 0.01:
            errors.append(
                f"ter_rate mismatch: expected {ter_rate * 100}, got {doc.ter_rate}"
            )
            doc.ter_rate = flt(ter_rate * 100)
            doc.db_set('ter_rate', flt(ter_rate * 100), update_modified=False)

        # Log semua error yang ditemukan
        if errors:
            # This is a non-critical error (we've already fixed the issues), so use log_error + msgprint
            frappe.log_error(
                "Integrity check found issues for {0}:\n{1}".format(
                    doc.name, "\n".join("- {0}".format(err) for err in errors)
                ),
                "TER Calculation Integrity"
            )
            
            frappe.msgprint(
                _("Some TER calculation values were automatically corrected. See the log for details."),
                indicator="orange"
            )
            
            # Tambahkan ke payroll_note jika tersedia
            if hasattr(doc, 'payroll_note'):
                doc.payroll_note += (
                    "\n[TER] Warning: Calculation integrity issues detected and fixed:\n" +
                    "\n".join(f"- {err}" for err in errors)
                )

        return len(errors) == 0

    except Exception as e:
        # Error log only, as this is not fatal to the process
        frappe.log_error(
            "Error during TER calculation verification for {0}: {1}".format(doc.name, str(e)),
            "TER Verification Error"
        )
        # Don't throw as this is a non-critical function
        frappe.msgprint(_("Warning: Could not verify TER calculation integrity"), indicator="orange")
        return False

def get_ter_rate(ter_category, income):
    """
    Get TER rate based on TER category and income - with caching for efficiency
    
    Args:
        ter_category: TER category ('TER A', 'TER B', 'TER C')
        income: Monthly income amount
        
    Returns:
        float: TER rate as decimal (e.g., 0.05 for 5%)
    """
    try:
        # Validate inputs
        if not ter_category:
            ter_category = TER_CATEGORY_C  # Default to highest category if not specified
            
        if not income or income <= 0:
            return 0
            
        # Create a unique cache key
        income_bracket = round(income, -3)  # Round to nearest thousand for better cache hits
        cache_key = f"ter_rate:{ter_category}:{income_bracket}"
        
        # Check cache first
        rate_value = get_cached_value(cache_key)
        if rate_value is not None:
            return rate_value
        
        # Get TER rate from database - use efficient SQL query
        ter = frappe.db.sql("""
            SELECT rate
            FROM `tabPPh 21 TER Table`
            WHERE status_pajak = %s
              AND %s >= income_from
              AND (%s <= income_to OR income_to = 0)
            ORDER BY income_from DESC
            LIMIT 1
        """, (ter_category, income, income), as_dict=1)

        if ter:
            # Cache the result before returning
            rate_value = float(ter[0].rate) / 100.0
            cache_value(cache_key, rate_value, CACHE_SHORT)  # 30 minutes
            return rate_value
        else:
            # Try to find using highest available bracket
            ter = frappe.db.sql("""
                SELECT rate
                FROM `tabPPh 21 TER Table`
                WHERE status_pajak = %s
                  AND is_highest_bracket = 1
                LIMIT 1
            """, (ter_category,), as_dict=1)
            
            if ter:
                # Cache the highest bracket result
                rate_value = float(ter[0].rate) / 100.0
                cache_value(cache_key, rate_value, CACHE_SHORT)  # 30 minutes
                return rate_value
            else:
                # As a last resort, use default rate from settings or hardcoded value
                try:
                    # Fall back to defaults.json values
                    from payroll_indonesia.payroll_indonesia.utils import get_default_config
                    config = get_default_config()
                    if config and "ter_rates" in config and ter_category in config["ter_rates"]:
                        # Get the highest rate from the category
                        highest_rate = 0
                        for rate_data in config["ter_rates"][ter_category]:
                            if "is_highest_bracket" in rate_data and rate_data["is_highest_bracket"]:
                                highest_rate = flt(rate_data["rate"])
                                break
                        
                        if highest_rate > 0:
                            rate_value = highest_rate / 100.0
                            cache_value(cache_key, rate_value, CACHE_SHORT)  # 30 minutes
                            return rate_value
                    
                    # PMK 168/2023 highest rate is 34% for all categories
                    cache_value(cache_key, TER_MAX_RATE / 100.0, CACHE_SHORT)  # 30 minutes
                    return TER_MAX_RATE / 100.0
                        
                except Exception as e:
                    # This is a validation failure - TER rate is critical to tax calculation
                    frappe.log_error(
                        "Failed to determine TER rate for category {0}: {1}".format(
                            ter_category, str(e)
                        ),
                        "TER Rate Error"
                    )
                    # Last resort - use PMK 168/2023 highest rate
                    frappe.msgprint(_("Warning: Using default TER rate (34%) due to lookup failure"), indicator="red")
                    cache_value(cache_key, TER_MAX_RATE / 100.0, CACHE_SHORT)  # 30 minutes
                    return TER_MAX_RATE / 100.0
        
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # This is a critical error - log and throw
        frappe.log_error(
            "Error getting TER rate for category {0} and income {1}: {2}".format(
                ter_category, income, str(e)
            ),
            "TER Rate Error"
        )
        frappe.throw(_("Failed to determine TER rate: {0}").format(str(e)))

def should_use_ter_method(employee, pph_settings=None):
    """
    Determine if TER method should be used for this employee according to PMK 168/2023
    
    Args:
        employee: Employee document
        pph_settings: PPh 21 Settings document (optional)
        
    Returns:
        bool: True if TER should be used, False otherwise
    """
    try:
        # Check cache first
        cache_key = f"use_ter:{employee.name if hasattr(employee, 'name') else 'unknown'}"
        cached_result = get_cached_value(cache_key)
        
        if cached_result is not None:
            return cached_result
            
        # Get PPh 21 Settings if not provided - use cached value for better performance
        if not pph_settings:
            settings_cache_key = "pph_settings:use_ter"
            pph_settings = get_cached_value(settings_cache_key)
            
            if pph_settings is None:
                pph_settings = frappe.get_cached_value(
                    "PPh 21 Settings", 
                    "PPh 21 Settings",
                    ["calculation_method", "use_ter"],
                    as_dict=True
                ) or {}
                
                # Cache settings for 1 hour
                cache_value(settings_cache_key, pph_settings, CACHE_MEDIUM)
        
        # Fast path for global TER setting disabled
        if (pph_settings.get('calculation_method') != "TER" or 
            not pph_settings.get('use_ter')):
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
        if hasattr(employee, 'tipe_karyawan') and employee.tipe_karyawan == "Freelance":
            cache_value(cache_key, False, CACHE_MEDIUM)  # Cache for 1 hour
            return False
            
        if hasattr(employee, 'override_tax_method') and employee.override_tax_method == "Progressive":
            cache_value(cache_key, False, CACHE_MEDIUM)  # Cache for 1 hour
            return False
            
        # If we made it here, use TER method
        cache_value(cache_key, True, CACHE_MEDIUM)  # Cache for 1 hour
        return True
            
    except Exception as e:
        # This is not a validation failure, so log and continue with default behavior
        frappe.log_error(
            "Error determining TER eligibility for {0}: {1}".format(
                getattr(employee, 'name', 'unknown'), str(e)
            ),
            "TER Eligibility Error"
        )
        frappe.msgprint(
            _("Warning: Could not determine TER eligibility. Using progressive method as fallback."),
            indicator="orange"
        )
        # Default to False on error (use progressive method)
        return False

# Enhanced functions for better YTD tax calculations
def get_ytd_totals_from_tax_summary(employee, year, month):
    """
    Get YTD tax totals from Employee Tax Summary with caching
    Args:
        employee: Employee ID
        year: Current year
        month: Current month (1-12)
    Returns:
        dict: Dictionary with ytd_gross, ytd_tax, ytd_bpjs
    """
    # Create cache key
    cache_key = f"ytd:{employee}:{year}:{month}"
    
    # Check cache first
    cached_result = get_cached_value(cache_key)
    
    if cached_result is not None:
        return cached_result
    
    try:
        # Use a parameterized query to get all needed data
        ytd_data = frappe.db.sql("""
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
        """, (employee, year, month), as_dict=1)
        
        if ytd_data and ytd_data[0]:
            result = {
                'ytd_gross': flt(ytd_data[0].ytd_gross),
                'ytd_tax': flt(ytd_data[0].ytd_tax),
                'ytd_bpjs': flt(ytd_data[0].ytd_bpjs)
            }
            
            # Cache the result (for 1 hour)
            cache_value(cache_key, result, CACHE_MEDIUM)
            
            return result
        else:
            # No data found, return zeros
            result = {'ytd_gross': 0, 'ytd_tax': 0, 'ytd_bpjs': 0}
            cache_value(cache_key, result, CACHE_MEDIUM)
            return result
    
    except Exception as e:
        # This is not a validation failure - we can fall back to legacy method
        frappe.log_error(
            "Error getting YTD tax data for {0}, {1}, {2}: {3}".format(
                employee, year, month, str(e)
            ),
            "YTD Tax Data Error"
        )
        frappe.msgprint(
            _("Warning: Using fallback method to calculate YTD tax data"),
            indicator="orange"
        )
        
        # Fallback to the older method if SQL fails
        return get_ytd_totals_from_tax_summary_legacy(employee, year, month)

def get_ytd_totals_from_tax_summary_legacy(employee, year, month):
    """
    Legacy fallback method to get YTD tax totals from Employee Tax Summary
    """
    try:
        # Find Employee Tax Summary for this employee and year
        tax_summary = frappe.get_all(
            "Employee Tax Summary",
            filters={"employee": employee, "year": year, "docstatus": ["!=", 2]},
            fields=["name", "ytd_tax"],
            limit=1
        )
        
        if not tax_summary:
            return {'ytd_gross': 0, 'ytd_tax': 0, 'ytd_bpjs': 0}
            
        # Get monthly details for YTD calculations
        monthly_details = frappe.get_all(
            "Employee Tax Summary Detail",
            filters={"parent": tax_summary[0].name, "month": ["<", month]},
            fields=["gross_pay", "bpjs_deductions"],
            order_by="month asc"
        )
        
        # Calculate YTD totals
        ytd_gross = sum(flt(d.gross_pay) for d in monthly_details)
        ytd_bpjs = sum(flt(d.bpjs_deductions) for d in monthly_details)
        ytd_tax = flt(tax_summary[0].ytd_tax)
        
        result = {
            'ytd_gross': ytd_gross,
            'ytd_tax': ytd_tax,
            'ytd_bpjs': ytd_bpjs
        }
        
        # Cache the result
        cache_key = f"ytd:{employee}:{year}:{month}"
        cache_value(cache_key, result, CACHE_MEDIUM)
        
        return result
        
    except Exception as e:
        # Non-critical error - we can return zeros as a last resort
        frappe.log_error(
            "Error getting YTD tax data (legacy method) for {0}, {1}, {2}: {3}".format(
                employee, year, month, str(e)
            ),
            "YTD Tax Legacy Error"
        )
        frappe.msgprint(
            _("Warning: Could not calculate YTD tax data. Using zeros as fallback."),
            indicator="red"
        )
        return {'ytd_gross': 0, 'ytd_tax': 0, 'ytd_bpjs': 0}