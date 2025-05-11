# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 15:01:13 by dannyaudianlanjutkan

import frappe
from frappe import _
from frappe.utils import flt, getdate, cint, now_datetime
import hashlib

from .base import update_component_amount

# Import cache utilities
from payroll_indonesia.payroll_indonesia.utilities.cache_utils import get_cached_value, cache_value, clear_cache

# Import constants
from payroll_indonesia.constants import (
    MONTHS_PER_YEAR, CACHE_SHORT, CACHE_LONG, ANNUAL_DETECTION_FACTOR,
    SALARY_BASIC_FACTOR, TAX_DETECTION_THRESHOLD, CACHE_MEDIUM,
    TER_CATEGORY_A, TER_CATEGORY_B, TER_CATEGORY_C, TER_CATEGORIES
)

# Import centralized logic functions
from payroll_indonesia.payroll_indonesia.tax.ter_logic import (
    detect_annual_income,
    add_tax_info_to_note
)

# Import TER functions from pph_ter (single source of truth)
from payroll_indonesia.payroll_indonesia.tax.pph_ter import (
    map_ptkp_to_ter_category,
    get_ter_rate,
    calculate_monthly_tax_with_ter
)

def calculate_monthly_pph_with_ter(doc, employee):
    """Calculate PPh 21 using TER method based on PMK 168/2023"""
    try:
        # Store original values for verification
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

        # Start with gross pay as monthly income
        monthly_gross_pay = flt(doc.gross_pay)

        # Calculate total earnings if available for annual detection
        total_earnings = flt(sum(flt(e.amount) for e in doc.earnings)) if hasattr(doc, 'earnings') and doc.earnings else 0
        
        # Get basic salary if available for annual detection
        basic_salary = next(
            (flt(e.amount) for e in doc.earnings 
              if e.salary_component in ["Gaji Pokok", "Basic Salary", "Basic Pay"]), 
            0
        ) if hasattr(doc, 'earnings') and doc.earnings else 0
        
        # Use centralized logic to detect annual income
        bypass_detection = bool(getattr(doc, 'bypass_annual_detection', 0))
        is_annual, reason, monthly_gross_pay = detect_annual_income(
            doc.gross_pay, 
            total_earnings, 
            basic_salary,
            bypass_detection
        )

        # Log annual value detection
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

        # Set and save monthly and annual values 
        annual_taxable_amount = flt(monthly_gross_pay * MONTHS_PER_YEAR)
        
        # Save monthly_gross_for_ter
        if hasattr(doc, 'monthly_gross_for_ter'):
            doc.monthly_gross_for_ter = monthly_gross_pay
            doc.db_set('monthly_gross_for_ter', monthly_gross_pay, update_modified=False)
            
        # Save annual_taxable_amount
        if hasattr(doc, 'annual_taxable_amount'):
            doc.annual_taxable_amount = annual_taxable_amount
            doc.db_set('annual_taxable_amount', annual_taxable_amount, update_modified=False)

        # Determine TER category from employee status
        cache_key = f"ter_category:{employee.status_pajak}"
        ter_category = get_cached_value(cache_key)
        
        if ter_category is None:
            # Use centralized mapping function
            ter_category = map_ptkp_to_ter_category(employee.status_pajak)
            cache_value(cache_key, ter_category, CACHE_LONG)
            
        # Calculate monthly tax with TER
        try:
            monthly_tax, ter_rate = calculate_monthly_tax_with_ter(monthly_gross_pay, ter_category)
        except Exception as e:
            # Fallback to direct calculation if centralized function fails
            # This adds a layer of resilience
            cache_key = f"ter_rate:{ter_category}:{round(monthly_gross_pay, -3)}"
            ter_rate = get_cached_value(cache_key)
            
            if ter_rate is None:
                ter_rate = get_ter_rate(ter_category, monthly_gross_pay)
                cache_value(cache_key, ter_rate, CACHE_SHORT)
                
            monthly_tax = flt(monthly_gross_pay * ter_rate)
        
        # Set and save TER info
        doc.is_using_ter = 1
        doc.ter_rate = flt(ter_rate * 100)
        doc.ter_category = ter_category
        
        # Save directly to database
        doc.db_set('is_using_ter', 1, update_modified=False)
        doc.db_set('ter_rate', flt(ter_rate * 100), update_modified=False)
        doc.db_set('ter_category', ter_category, update_modified=False)

        # Update PPh 21 component
        update_component_amount(doc, "PPh 21", monthly_tax, "deductions")

        # Add tax info to note using shared function
        add_tax_info_to_note(doc, "TER", {
            "status_pajak": employee.status_pajak,
            "ter_category": ter_category,
            "gross_pay": monthly_gross_pay,
            "ter_rate": ter_rate * 100,
            "monthly_tax": monthly_tax
        })

        # Verify calculation integrity
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
    """Verify integrity of TER calculation results"""
    try:
        errors = []
        
        # Verify gross_pay hasn't changed
        if abs(flt(doc.gross_pay) - original_values['gross_pay']) > 0.01:
            errors.append(
                f"gross_pay changed: {original_values['gross_pay']} → {doc.gross_pay}"
            )
            doc.gross_pay = original_values['gross_pay']
            doc.db_set('gross_pay', original_values['gross_pay'], update_modified=False)

        # Verify monthly_gross_for_ter
        if hasattr(doc, 'monthly_gross_for_ter'):
            if abs(flt(doc.monthly_gross_for_ter) - monthly_gross_pay) > 0.01:
                errors.append(
                    f"monthly_gross_for_ter mismatch: expected {monthly_gross_pay}, "
                    f"got {doc.monthly_gross_for_ter}"
                )
                doc.monthly_gross_for_ter = monthly_gross_pay
                doc.db_set('monthly_gross_for_ter', monthly_gross_pay, update_modified=False)

        # Verify annual_taxable_amount
        if hasattr(doc, 'annual_taxable_amount'):
            expected_annual = flt(monthly_gross_pay * MONTHS_PER_YEAR)
            if abs(flt(doc.annual_taxable_amount) - expected_annual) > 0.01:
                errors.append(
                    f"annual_taxable_amount mismatch: expected {expected_annual}, "
                    f"got {doc.annual_taxable_amount}"
                )
                doc.annual_taxable_amount = expected_annual
                doc.db_set('annual_taxable_amount', expected_annual, update_modified=False)

        # Verify TER values
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

        # Log all errors found
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
            
            # Add to payroll_note if available
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

# YTD functions - to be moved to utils.py in a future refactoring
def get_ytd_totals_from_tax_summary(employee, year, month):
    """
    Get YTD tax totals from Employee Tax Summary with caching
    
    This function will be moved to utils.py in a future refactoring.
    For now, we keep it here for backward compatibility.
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
    
    This function will be moved to utils.py in a future refactoring.
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