# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 10:47:38 by dannyaudian

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
from frappe.utils import flt, getdate, cint

# Import cache utilities
from payroll_indonesia.utilities.cache_utils import get_cached_value, cache_value

# Import constants
from payroll_indonesia.constants import (
    MONTHS_PER_YEAR, CACHE_SHORT, CACHE_LONG, CACHE_MEDIUM, 
    TER_CATEGORY_A, TER_CATEGORY_B, TER_CATEGORY_C, 
    TER_MAX_RATE, CURRENCY_PRECISION,
    BIAYA_JABATAN_PERCENT, BIAYA_JABATAN_MAX
)

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
                    cache_value(cache_key, TER_MAX_RATE / 100.0, CACHE_SHORT)  # 30 minutes
                    return TER_MAX_RATE / 100.0
        
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # Log error details
        frappe.log_error(
            "Error getting TER rate for category {0} and income {1}: {2}".format(
                ter_category, income, str(e)
            ),
            "TER Rate Error"
        )
        raise

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
                "PKP Validation Warning"
            )
            pkp = 0

        # Get settings
        if not pph_settings and frappe.db.exists("DocType", "PPh 21 Settings"):
            try:
                pph_settings = frappe.get_cached_doc("PPh 21 Settings")
            except Exception as settings_error:
                frappe.log_error(
                    "Error retrieving PPh 21 Settings: {0}".format(str(settings_error)),
                    "Settings Retrieval Warning"
                )
                pph_settings = None

        # First check if bracket_table is directly available as attribute
        bracket_table = []
        if pph_settings and hasattr(pph_settings, 'bracket_table'):
            bracket_table = pph_settings.bracket_table
            
        # If not found or empty, query from database
        if not bracket_table and pph_settings:
            bracket_table = frappe.db.sql("""
                SELECT income_from, income_to, tax_rate
                FROM `tabPPh 21 Tax Bracket`
                WHERE parent = 'PPh 21 Settings'
                ORDER BY income_from ASC
            """, as_dict=1)

        # If still not found, use default values
        if not bracket_table:
            # Log warning about missing brackets
            frappe.log_error(
                "No tax brackets found in settings, using default values",
                "Tax Bracket Warning"
            )
            
            # Default bracket values if not found - based on PMK 101/2016 and UU HPP 2021
            bracket_table = [
                {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
                {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
                {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
                {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
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
            upper_limit = income_to if income_to > 0 else float('inf')
            lower_limit = income_from
            taxable = min(remaining_pkp, upper_limit - lower_limit)

            tax = taxable * (tax_rate / 100)
            total_tax += tax

            if tax > 0:
                tax_details.append({
                    'rate': tax_rate,
                    'taxable': taxable,
                    'tax': tax
                })

            remaining_pkp -= taxable

        return total_tax, tax_details
        
    except Exception as e:
        # Non-critical error - log and return default values
        frappe.log_error(
            "Error calculating progressive tax for PKP {0}: {1}".format(pkp, str(e)),
            "Tax Bracket Calculation Error"
        )
        raise

def map_ptkp_to_ter_category(status_pajak):
    """
    Map PTKP status to TER category based on PMK 168/2023
    
    Args:
        status_pajak: Tax status (e.g., 'TK0', 'K1', etc.)
        
    Returns:
        str: TER category ('TER A', 'TER B', or 'TER C')
    """
    try:
        # Use ptkp_to_ter_mapping from settings if available
        mapping = {}
        
        # Try to get the mapping from settings
        try:
            # Use cache for ptkp_to_ter_mapping
            cache_key = "ptkp_to_ter_mapping"
            mapping = get_cached_value(cache_key)
            
            if mapping is None:
                # Try to get from PPh 21 Settings
                if frappe.db.exists("DocType", "PPh 21 Settings"):
                    pph_settings = frappe.get_cached_doc("PPh 21 Settings")
                    if hasattr(pph_settings, 'ptkp_to_ter_mapping'):
                        mapping = {}
                        for row in pph_settings.ptkp_to_ter_mapping:
                            mapping[row.ptkp_status] = row.ter_category
                        
                # If not found, try to get from defaults.json
                if not mapping:
                    from payroll_indonesia.payroll_indonesia.utils import get_default_config
                    config = get_default_config()
                    if config and "ptkp_to_ter_mapping" in config:
                        mapping = config["ptkp_to_ter_mapping"]
                        
                # Cache the mapping
                cache_value(cache_key, mapping or {}, CACHE_LONG)  # 24 hours
        except Exception as e:
            frappe.log_error(
                "Error retrieving PTKP to TER mapping: {0}".format(str(e)),
                "PTKP Mapping Error"
            )
            mapping = {}
            
        # If status_pajak is in mapping, return the mapped category
        if mapping and status_pajak in mapping:
            return mapping[status_pajak]
            
        # Default mapping based on PMK 168/2023 logic
        prefix = status_pajak[:2] if len(status_pajak) >= 2 else status_pajak
        suffix = status_pajak[2:] if len(status_pajak) >= 3 else "0"
        
        # TK/0 uses TER A
        if status_pajak == "TK0":
            return TER_CATEGORY_A
        
        # TK/1 and TK/2 use TER B
        elif prefix == "TK" and suffix in ["1", "2"]:
            return TER_CATEGORY_B
        
        # TK/3 uses TER C
        elif prefix == "TK" and suffix == "3":
            return TER_CATEGORY_C
        
        # K/0 and K/1 use TER B
        elif prefix == "K" and suffix in ["0", "1"]:
            return TER_CATEGORY_B
        
        # K/2 and K/3 use TER C
        elif prefix == "K" and suffix in ["2", "3"]:
            return TER_CATEGORY_C
        
        # HB (any) uses TER C
        elif prefix == "HB":
            return TER_CATEGORY_C
        
        # Default to TER C (most conservative)
        return TER_CATEGORY_C
        
    except Exception as e:
        # Non-critical error - return TER C as fallback
        frappe.log_error(
            "Error mapping PTKP {0} to TER category: {1}".format(status_pajak, str(e)),
            "PTKP Mapping Error"
        )
        return TER_CATEGORY_C

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
            frappe.log_error(
                "Empty tax status provided, using TK0 as default",
                "PTKP Warning"
            )
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
        if pph_settings and hasattr(pph_settings, 'ptkp_table'):
            ptkp_table = pph_settings.ptkp_table
            
        # If not found in cached doc, query from database
        if not ptkp_table and pph_settings:
            ptkp_table = frappe.db.sql("""
                SELECT status_pajak as tax_status, ptkp_amount as amount
                FROM `tabPPh 21 PTKP Table`
                WHERE parent = 'PPh 21 Settings'
            """, as_dict=1)
        
        # Find matching status
        for ptkp in ptkp_table:
            if hasattr(ptkp, 'tax_status') and ptkp.tax_status == status_pajak:
                ptkp_amount = flt(ptkp.amount)
                cache_value(cache_key, ptkp_amount, CACHE_LONG)
                return ptkp_amount
            
            # For backward compatibility
            if hasattr(ptkp, 'status_pajak') and ptkp.status_pajak == status_pajak:
                ptkp_amount = flt(ptkp.ptkp_amount)
                cache_value(cache_key, ptkp_amount, CACHE_LONG)
                return ptkp_amount
        
        # If not found, try to match prefix (TK0 -> TK)
        prefix = status_pajak[:2] if len(status_pajak) >= 2 else status_pajak
        for ptkp in ptkp_table:
            ptkp_status = ptkp.tax_status if hasattr(ptkp, 'tax_status') else ptkp.status_pajak
            if ptkp_status and ptkp_status.startswith(prefix):
                ptkp_amount = flt(ptkp.amount if hasattr(ptkp, 'amount') else ptkp.ptkp_amount)
                cache_value(cache_key, ptkp_amount, CACHE_LONG)
                return ptkp_amount
        
        # Default values if not found or settings don't exist - based on PMK-101/PMK.010/2016 and updated values
        default_ptkp = {
            "TK": 54000000,  # TK/0
            "K": 58500000,   # K/0
            "HB": 112500000  # HB/0
        }
        
        # Return default based on prefix
        for key, value in default_ptkp.items():
            if prefix.startswith(key):
                frappe.log_error(
                    "PTKP not found in settings for {0}, using default value {1}".format(
                        status_pajak, value
                    ),
                    "PTKP Fallback Warning"
                )
                cache_value(cache_key, value, CACHE_LONG)
                return value
                
        # Last resort - TK0
        default_value = 54000000  # Default for TK0
        frappe.log_error(
            "No PTKP match found for {0}, using TK0 default ({1})".format(
                status_pajak, default_value
            ),
            "PTKP Default Warning"
        )
        cache_value(cache_key, default_value, CACHE_LONG)
        return default_value
    
    except Exception as e:
        # Non-critical error - log and return default
        frappe.log_error(
            "Error getting PTKP amount for {0}: {1}".format(status_pajak, str(e)),
            "PTKP Calculation Error"
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
        employee_id = employee.name if hasattr(employee, 'name') else employee.get('name', 'unknown')
            
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
                pph_settings = frappe.get_cached_value(
                    "PPh 21 Settings", 
                    "PPh 21 Settings",
                    ["calculation_method", "use_ter"],
                    as_dict=True
                ) or {}
                
                # Cache settings for 1 hour
                cache_value(settings_cache_key, pph_settings, CACHE_MEDIUM)
        
        # Fast path for global TER setting disabled
        if not pph_settings or pph_settings.get('calculation_method') != "TER" or not pph_settings.get('use_ter'):
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
        tipe_karyawan = getattr(employee, 'tipe_karyawan', None) or employee.get('tipe_karyawan', '')
        override_tax_method = getattr(employee, 'override_tax_method', None) or employee.get('override_tax_method', '')
        
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
                getattr(employee, 'name', 'unknown') if hasattr(employee, 'name') else employee.get('name', 'unknown'), 
                str(e)
            ),
            "TER Eligibility Error"
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
        # Validate parameters
        if not employee:
            frappe.throw(
                _("Employee ID is required for annual PPh calculation"),
                title=_("Missing Parameter")
            )
            
        if not year:
            frappe.throw(
                _("Tax year is required for annual PPh calculation"),
                title=_("Missing Parameter")
            )
            
        # Get employee document if not provided
        emp_doc = employee_details or None
        if not emp_doc:
            try:
                emp_doc = frappe.get_doc("Employee", employee)
            except Exception as e:
                frappe.throw(
                    _("Error retrieving employee {0}: {1}").format(employee, str(e)),
                    title=_("Employee Not Found")
                )
        
        # Get all salary slips for the year
        salary_slips = frappe.db.get_all(
            "Salary Slip",
            filters={
                "employee": employee,
                "docstatus": 1,
                "start_date": ["between", [f"{year}-01-01", f"{year}-12-31"]]
            },
            fields=["name", "gross_pay", "total_bpjs", "start_date", "is_using_ter", "ter_rate", "ter_category"],
            order_by="start_date asc"
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
                "ter_used": False
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
        status_pajak = getattr(emp_doc, "status_pajak", None) or emp_doc.get("status_pajak", "TK0") if emp_doc else "TK0"
        ptkp = get_ptkp_amount(status_pajak)
        
        # Calculate PKP (taxable income)
        pkp = max(annual_net - ptkp, 0)
        
        # Check if TER was used in any month
        ter_used = any(getattr(slip, "is_using_ter", 0) or slip.get("is_using_ter", 0) for slip in salary_slips)
        
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
            "ter_category": ter_category
        }
        
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # For other errors, log and re-raise with clear message
        frappe.log_error(
            "Error calculating annual PPh for {0}, year {1}: {2}".format(
                employee, year, str(e)
            ),
            "Annual PPh Calculation Error"
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
        tax_components = frappe.db.sql("""
            SELECT parent, amount
            FROM `tabSalary Detail`
            WHERE 
                parent IN %s
                AND parentfield = 'deductions'
                AND salary_component = 'PPh 21'
        """, [tuple(slip_names)], as_dict=1)
        
        # Sum up tax amounts
        for comp in tax_components:
            total_tax += flt(comp.amount)
            
    except Exception as e:
        # Non-critical error - log, show warning and return 0
        frappe.log_error(
            "Error calculating already paid tax: {0}".format(str(e)),
            "Tax Calculation Warning"
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

def calculate_monthly_tax_with_ter(income, ter_category):
    """
    Calculate monthly PPh 21 using TER method
    
    Args:
        income: Monthly income amount
        ter_category: TER category
        
    Returns:
        tuple: (monthly_tax, ter_rate)
    """
    try:
        # Get TER rate for income and category
        ter_rate = get_ter_rate(ter_category, income)
        
        # Calculate tax
        monthly_tax = flt(income * ter_rate)
        
        return monthly_tax, ter_rate
    except Exception as e:
        # Log error and re-raise
        frappe.log_error(
            "Error calculating monthly tax with TER for income {0}: {1}".format(income, str(e)),
            "TER Calculation Error"
        )
        raise