# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 13:25:49 by dannyaudian

import frappe
import json
import os
from frappe import _
from frappe.utils import flt, cint, getdate, now_datetime
from typing import Dict, Any, Optional, List

# Import constants
from payroll_indonesia.constants import (
    CACHE_MEDIUM,
    CACHE_SHORT,
    CACHE_LONG,
    BIAYA_JABATAN_PERCENT,
    BIAYA_JABATAN_MAX,
    TER_CATEGORY_A,
    TER_CATEGORY_B,
    TER_CATEGORY_C,
)

# Import cache utilities
from payroll_indonesia.utilities.cache_utils import (
    get_cached_value,
    cache_value,
    memoize_with_ttl,
)

# Define exports
__all__ = [
    "debug_log",
    "get_settings",
    "get_default_config",
    "find_parent_account",
    "create_account",
    "create_parent_liability_account",
    "create_parent_expense_account",
    "retry_bpjs_mapping",
    "get_bpjs_settings",
    "calculate_bpjs_contributions",
    "get_ptkp_settings",
    "get_spt_month",
    "get_pph21_settings",
    "get_pph21_brackets",
    "get_ter_category",
    "get_ter_rate",
    "should_use_ter",
    "create_tax_summary_doc",
    "get_ytd_tax_info",
    "get_ytd_totals",
    "get_ytd_totals_from_tax_summary",
    "get_employee_details",
]

# Settings cache
settings_cache = {}
cache_expiry = {}
CACHE_EXPIRY_SECONDS = 3600  # 1 hour


def get_settings():
    """Get Payroll Indonesia Settings, create if doesn't exist"""
    try:
        # Try to get settings from cache first
        cache_key = "payroll_indonesia_settings"
        if cache_key in settings_cache:
            # Check if cache is still valid
            if cache_expiry.get(cache_key, 0) > frappe.utils.now_datetime().timestamp():
                return settings_cache[cache_key]

        # Get settings from database
        if not frappe.db.exists("Payroll Indonesia Settings", "Payroll Indonesia Settings"):
            # Create settings with defaults (fallback)
            settings = create_default_settings()
        else:
            settings = frappe.get_doc("Payroll Indonesia Settings", "Payroll Indonesia Settings")

        # Cache the settings
        settings_cache[cache_key] = settings
        cache_expiry[cache_key] = frappe.utils.now_datetime().timestamp() + CACHE_EXPIRY_SECONDS

        return settings
    except Exception as e:
        frappe.log_error(f"Error getting Payroll Indonesia Settings: {str(e)}", "Settings Error")
        # If settings can't be loaded, return an empty doc as fallback
        return frappe.get_doc({"doctype": "Payroll Indonesia Settings"})

def get_default_config(section=None) -> dict:
    """
    Returns configuration values for payroll Indonesia from settings.

    Args:
        section (str, optional): Specific configuration section to return.
                               If None, returns the entire config.

    Returns:
        dict: Configuration settings or specific section
    """
    # Get settings document
    settings = get_settings()

    # Build config dictionary from settings
    config = {
        "bpjs_kesehatan": {
            "employee_contribution": settings.kesehatan_employee_percent,
            "employer_contribution": settings.kesehatan_employer_percent,
        },
        "bpjs_ketenagakerjaan": {
            "jht": {
                "employee_contribution": getattr(settings, "jht_employee_percent", 2.0),
                "employer_contribution": getattr(settings, "jht_employer_percent", 3.7),
            },
            "jkk": {
                "employer_contribution": getattr(settings, "jkk_employer_percent", 0.24),
            },
            "jkm": {
                "employer_contribution": getattr(settings, "jkm_employer_percent", 0.3),
            },
            "jp": {
                "employee_contribution": getattr(settings, "jp_employee_percent", 1.0),
                "employer_contribution": getattr(settings, "jp_employer_percent", 2.0),
            },
        },
        "ptkp_values": settings.get_ptkp_values_dict(),
        "ptkp_to_ter_mapping": settings.get_ptkp_ter_mapping_dict(),
        "tax_brackets": settings.get_tax_brackets_list(),
        "tipe_karyawan": settings.get_tipe_karyawan_list(),
        "gl_accounts": {
            # You would need to expand this based on what's available in your settings
            "bpjs_expense_accounts": {}
        },
    }

    # Add any default account settings that might not be in the document
    config["bpjs_payable_parent_account"] = getattr(
        settings, "bpjs_payable_parent_account", "Current Liabilities"
    )
    config["bpjs_expense_parent_account"] = getattr(
        settings, "bpjs_expense_parent_account", "Expenses"
    )

    if section:
        return config.get(section, {})

    return config


def create_default_settings():
    """Create default settings when not available"""
    settings = frappe.get_doc(
        {
            "doctype": "Payroll Indonesia Settings",
            "app_version": "1.0.0",
            "app_last_updated": frappe.utils.now(),
            "app_updated_by": "dannyaudian",
            # BPJS defaults
            "kesehatan_employee_percent": 1.0,
            "kesehatan_employer_percent": 4.0,
            "kesehatan_max_salary": 12000000.0,
            "jht_employee_percent": 2.0,
            "jht_employer_percent": 3.7,
            "jp_employee_percent": 1.0,
            "jp_employer_percent": 2.0,
            "jp_max_salary": 9077600.0,
            "jkk_percent": 0.24,
            "jkm_percent": 0.3,
            # Tax defaults
            "umr_default": 4900000.0,
            "biaya_jabatan_percent": 5.0,
            "biaya_jabatan_max": 500000.0,
            "tax_calculation_method": "TER",
            "use_ter": 1,
            # Default settings
            "default_currency": "IDR",
            "payroll_frequency": "Monthly",
            "max_working_days_per_month": 22,
            "working_hours_per_day": 8,
            # Salary structure
            "basic_salary_percent": 75,
            "meal_allowance": 750000.0,
            "transport_allowance": 900000.0,
            "position_allowance_percent": 7.5,
        }
    )

    # Insert with permission bypass
    settings.flags.ignore_permissions = True
    settings.flags.ignore_mandatory = True
    settings.insert(ignore_permissions=True)

    frappe.db.commit()
    return settings


# Internal helper function for settings retrieval
def _get_payroll_settings(
    doctype: str, cache_key: str, defaults: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Internal helper to fetch single DocType settings with cache

    Args:
        doctype (str): The settings DocType name
        cache_key (str): Cache key to use
        defaults (Dict[str, Any], optional): Default values if settings don't exist

    Returns:
        Dict[str, Any]: Settings dictionary
    """
    if not defaults:
        defaults = {}

    # For Payroll Indonesia Settings, use the get_settings() function
    if doctype == "Payroll Indonesia Settings":
        settings = get_settings()
        return settings.as_dict() if settings else defaults

    # Check cache first
    settings = frappe.cache().get_value(cache_key)
    if settings:
        return settings

    try:
        # Check if DocType exists
        if frappe.db.exists("DocType", doctype):
            doc_list = frappe.db.get_all(doctype)
            if doc_list:
                settings_doc = frappe.get_single(doctype)

                # Convert DocType to dictionary for caching
                settings = settings_doc.as_dict()

                # Cache for CACHE_MEDIUM period (1 hour)
                frappe.cache().set_value(cache_key, settings, expires_in_sec=CACHE_MEDIUM)
                return settings

    except Exception as e:
        frappe.log_error(f"Error retrieving {doctype}: {str(e)}", f"{doctype} Retrieval Error")

    # If we reach here, use defaults
    frappe.log_error(f"{doctype} not found or empty. Using defaults.", f"{doctype} Fallback")

    # Cache defaults for shorter period
    frappe.cache().set_value(cache_key, defaults, expires_in_sec=CACHE_SHORT)

    return defaults


# Logging functions
def debug_log(message, title=None, max_length=500, trace=False):
    """
    Debug logging helper with consistent format

    Args:
        message (str): Message to log
        title (str, optional): Optional title/context for the log
        max_length (int, optional): Maximum message length (default: 500)
        trace (bool, optional): Whether to include traceback (default: False)
    """
    timestamp = now_datetime().strftime("%Y-%m-%d %H:%M:%S")

    if os.environ.get("DEBUG_BPJS") or trace:
        # Truncate if message is too long to avoid memory issues
        message = str(message)[:max_length]

        if title:
            log_message = f"[{timestamp}] [{title}] {message}"
        else:
            log_message = f"[{timestamp}] {message}"

        frappe.logger().debug(f"[BPJS DEBUG] {log_message}")

        if trace:
            frappe.logger().debug(f"[BPJS DEBUG] [TRACE] {frappe.get_traceback()[:max_length]}")


# BPJS Settings and Calculation Functions
@memoize_with_ttl(ttl=CACHE_MEDIUM)
def get_bpjs_settings() -> Dict[str, Any]:
    """
    Get BPJS settings from Payroll Indonesia Settings with caching

    Returns:
        dict: Dictionary containing structured BPJS settings
    """
    # Default settings to use if DocType doesn't exist
    defaults = {
        "kesehatan": {"employee_percent": 1.0, "employer_percent": 4.0, "max_salary": 12000000},
        "jht": {"employee_percent": 2.0, "employer_percent": 3.7},
        "jp": {"employee_percent": 1.0, "employer_percent": 2.0, "max_salary": 9077600},
        "jkk": {"percent": 0.24},
        "jkm": {"percent": 0.3},
    }

    # Get settings from Payroll Indonesia Settings
    settings_doc = get_settings()

    if not settings_doc:
        return defaults

    # Convert to structured format
    return {
        "kesehatan": {
            "employee_percent": flt(getattr(settings_doc, "kesehatan_employee_percent", 1.0)),
            "employer_percent": flt(getattr(settings_doc, "kesehatan_employer_percent", 4.0)),
            "max_salary": flt(getattr(settings_doc, "kesehatan_max_salary", 12000000)),
        },
        "jht": {
            "employee_percent": flt(getattr(settings_doc, "jht_employee_percent", 2.0)),
            "employer_percent": flt(getattr(settings_doc, "jht_employer_percent", 3.7)),
        },
        "jp": {
            "employee_percent": flt(getattr(settings_doc, "jp_employee_percent", 1.0)),
            "employer_percent": flt(getattr(settings_doc, "jp_employer_percent", 2.0)),
            "max_salary": flt(getattr(settings_doc, "jp_max_salary", 9077600)),
        },
        "jkk": {"percent": flt(getattr(settings_doc, "jkk_percent", 0.24))},
        "jkm": {"percent": flt(getattr(settings_doc, "jkm_percent", 0.3))},
    }


def calculate_bpjs_contributions(salary, bpjs_settings=None):
    """
    Calculate BPJS contributions based on salary and settings
    with improved validation and error handling

    Args:
        salary (float): Base salary amount
        bpjs_settings (object, optional): BPJS Settings or dict. Will fetch if not provided.

    Returns:
        dict: Dictionary containing BPJS contribution details
    """
    try:
        # Validate input
        if salary is None:
            frappe.throw(_("Salary amount is required for BPJS calculation"))

        salary = flt(salary)
        if salary < 0:
            frappe.msgprint(
                _("Negative salary amount provided for BPJS calculation, using absolute value")
            )
            salary = abs(salary)

        # Get BPJS settings if not provided
        if not bpjs_settings:
            bpjs_settings = get_bpjs_settings()

        # Extract values based on settings structure
        # Start with BPJS Kesehatan
        kesehatan = bpjs_settings.get("kesehatan", {})
        kesehatan_employee_percent = flt(kesehatan.get("employee_percent", 1.0))
        kesehatan_employer_percent = flt(kesehatan.get("employer_percent", 4.0))
        kesehatan_max_salary = flt(kesehatan.get("max_salary", 12000000))

        # BPJS JHT
        jht = bpjs_settings.get("jht", {})
        jht_employee_percent = flt(jht.get("employee_percent", 2.0))
        jht_employer_percent = flt(jht.get("employer_percent", 3.7))

        # BPJS JP
        jp = bpjs_settings.get("jp", {})
        jp_employee_percent = flt(jp.get("employee_percent", 1.0))
        jp_employer_percent = flt(jp.get("employer_percent", 2.0))
        jp_max_salary = flt(jp.get("max_salary", 9077600))

        # BPJS JKK and JKM
        jkk = bpjs_settings.get("jkk", {})
        jkm = bpjs_settings.get("jkm", {})
        jkk_percent = flt(jkk.get("percent", 0.24))
        jkm_percent = flt(jkm.get("percent", 0.3))

        # Cap salaries at maximum thresholds
        kesehatan_salary = min(flt(salary), kesehatan_max_salary)
        jp_salary = min(flt(salary), jp_max_salary)

        # Calculate BPJS Kesehatan
        kesehatan_karyawan = kesehatan_salary * (kesehatan_employee_percent / 100)
        kesehatan_perusahaan = kesehatan_salary * (kesehatan_employer_percent / 100)

        # Calculate BPJS Ketenagakerjaan - JHT
        jht_karyawan = flt(salary) * (jht_employee_percent / 100)
        jht_perusahaan = flt(salary) * (jht_employer_percent / 100)

        # Calculate BPJS Ketenagakerjaan - JP
        jp_karyawan = jp_salary * (jp_employee_percent / 100)
        jp_perusahaan = jp_salary * (jp_employer_percent / 100)

        # Calculate BPJS Ketenagakerjaan - JKK and JKM
        jkk = flt(salary) * (jkk_percent / 100)
        jkm = flt(salary) * (jkm_percent / 100)

        # Return structured result
        return {
            "kesehatan": {
                "karyawan": kesehatan_karyawan,
                "perusahaan": kesehatan_perusahaan,
                "total": kesehatan_karyawan + kesehatan_perusahaan,
            },
            "ketenagakerjaan": {
                "jht": {
                    "karyawan": jht_karyawan,
                    "perusahaan": jht_perusahaan,
                    "total": jht_karyawan + jht_perusahaan,
                },
                "jp": {
                    "karyawan": jp_karyawan,
                    "perusahaan": jp_perusahaan,
                    "total": jp_karyawan + jp_perusahaan,
                },
                "jkk": jkk,
                "jkm": jkm,
            },
        }
    except Exception as e:
        frappe.log_error(
            f"Error calculating BPJS contributions: {str(e)}", "BPJS Calculation Error"
        )
        debug_log(
            f"Error calculating BPJS contributions: {str(e)}", "Calculation Error", trace=True
        )

        # Return empty structure to avoid breaking code that relies on the structure
        return {
            "kesehatan": {"karyawan": 0, "perusahaan": 0, "total": 0},
            "ketenagakerjaan": {
                "jht": {"karyawan": 0, "perusahaan": 0, "total": 0},
                "jp": {"karyawan": 0, "perusahaan": 0, "total": 0},
                "jkk": 0,
                "jkm": 0,
            },
        }


# PPh 21 Settings functions
@memoize_with_ttl(ttl=CACHE_MEDIUM)
def get_pph21_settings() -> Dict[str, Any]:
    """
    Get PPh 21 settings from Payroll Indonesia Settings with caching

    Returns:
        dict: PPh 21 settings including calculation method and TER usage
    """
    # Default settings if DocType not found
    defaults = {
        "calculation_method": "Progressive",
        "use_ter": 0,
        "ptkp_settings": get_ptkp_settings(),
        "brackets": get_pph21_brackets(),
    }

    # Get settings from Payroll Indonesia Settings
    settings_doc = get_settings()

    if not settings_doc:
        return defaults

    # Extract relevant fields
    calculation_method = getattr(settings_doc, "tax_calculation_method", "Progressive")
    use_ter = cint(getattr(settings_doc, "use_ter", 0))

    return {
        "calculation_method": calculation_method,
        "use_ter": use_ter,
        "ptkp_settings": get_ptkp_settings(),
        "brackets": get_pph21_brackets(),
    }


@memoize_with_ttl(ttl=CACHE_LONG)  # PTKP values rarely change
def get_ptkp_settings() -> Dict[str, float]:
    """
    Get PTKP settings from Payroll Indonesia Settings with caching

    Returns:
        dict: Dictionary mapping tax status codes to PTKP values
    """
    # Default PTKP values
    defaults = {
        "TK0": 54000000,
        "TK1": 58500000,
        "TK2": 63000000,
        "TK3": 67500000,
        "K0": 58500000,
        "K1": 63000000,
        "K2": 67500000,
        "K3": 72000000,
        "HB0": 112500000,
        "HB1": 117000000,
        "HB2": 121500000,
        "HB3": 126000000,
    }

    try:
        # Get settings from Payroll Indonesia Settings
        settings = get_settings()

        if not settings:
            return defaults

        # Check if settings has ptkp_table
        if hasattr(settings, "ptkp_table") and settings.ptkp_table:
            result = {}
            # Get PTKP values from child table
            for row in settings.ptkp_table:
                if hasattr(row, "status_pajak") and hasattr(row, "ptkp_amount"):
                    result[row.status_pajak] = float(row.ptkp_amount)

            if result:
                # Cache for 24 hours
                frappe.cache().set_value("ptkp_settings", result, expires_in_sec=CACHE_LONG)
                return result
    except Exception as e:
        frappe.log_error(
            f"Error retrieving PTKP settings from Payroll Indonesia Settings: {str(e)}",
            "PTKP Settings Error",
        )

    # Cache default values for 1 hour
    frappe.cache().set_value("ptkp_settings", defaults, expires_in_sec=CACHE_MEDIUM)
    return defaults


@memoize_with_ttl(ttl=CACHE_LONG)  # Tax brackets rarely change
def get_pph21_brackets() -> List[Dict[str, Any]]:
    """
    Get PPh 21 tax brackets from Payroll Indonesia Settings with caching

    Returns:
        list: List of tax brackets with income ranges and rates
    """
    # Default brackets based on current regulations
    defaults = [
        {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
        {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
        {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
        {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
        {"income_from": 5000000000, "income_to": 0, "tax_rate": 35},
    ]

    try:
        # Get settings from Payroll Indonesia Settings
        settings = get_settings()

        if not settings:
            return defaults

        # Check if settings has tax_brackets_table
        if hasattr(settings, "tax_brackets_table") and settings.tax_brackets_table:
            brackets = []
            # Process brackets from child table
            for row in settings.tax_brackets_table:
                if (
                    hasattr(row, "income_from")
                    and hasattr(row, "income_to")
                    and hasattr(row, "tax_rate")
                ):
                    brackets.append(
                        {
                            "income_from": flt(row.income_from),
                            "income_to": flt(row.income_to),
                            "tax_rate": flt(row.tax_rate),
                        }
                    )

            if brackets:
                # Sort by income_from
                brackets.sort(key=lambda x: x["income_from"])

                # Cache for 24 hours
                frappe.cache().set_value("pph21_brackets", brackets, expires_in_sec=CACHE_LONG)
                return brackets
    except Exception as e:
        frappe.log_error(
            f"Error retrieving PPh 21 brackets from Payroll Indonesia Settings: {str(e)}",
            "PPh 21 Brackets Error",
        )

    # Cache default values for 1 hour
    frappe.cache().set_value("pph21_brackets", defaults, expires_in_sec=CACHE_MEDIUM)
    return defaults


def get_spt_month() -> int:
    """
    Get the month for annual SPT calculation

    Returns:
        int: Month number (1-12)
    """
    try:
        # Try to get from Payroll Indonesia Settings
        settings = get_settings()
        spt_month = getattr(settings, "spt_month", None)

        if spt_month and isinstance(spt_month, int) and 1 <= spt_month <= 12:
            return spt_month

        # Get from environment variable as fallback
        spt_month_str = os.environ.get("SPT_BULAN")

        if spt_month_str:
            try:
                spt_month = int(spt_month_str)
                # Validate month is in correct range
                if 1 <= spt_month <= 12:
                    return spt_month
            except ValueError:
                pass

        return 12  # Default to December
    except Exception as e:
        frappe.log_error(f"Error getting SPT month: {str(e)}", "SPT Month Error")
        return 12  # Default to December


# TER-related functions
def get_ter_category(ptkp_status):
    """
    Map PTKP status to TER category using Payroll Indonesia Settings

    Args:
        ptkp_status (str): Tax status code (e.g., 'TK0', 'K1')

    Returns:
        str: Corresponding TER category
    """
    try:
        # Get mapping from Payroll Indonesia Settings
        settings = get_settings()

        # Check if settings has ptkp_ter_mapping_table
        if hasattr(settings, "ptkp_ter_mapping_table") and settings.ptkp_ter_mapping_table:
            # Look for the mapping in the child table
            for row in settings.ptkp_ter_mapping_table:
                if row.ptkp_status == ptkp_status:
                    return row.ter_category

        # Default mapping logic
        prefix = ptkp_status[:2] if len(ptkp_status) >= 2 else ptkp_status
        suffix = ptkp_status[2:] if len(ptkp_status) >= 3 else "0"

        if ptkp_status == "TK0":
            return TER_CATEGORY_A
        elif prefix == "TK" and suffix in ["1", "2", "3"]:
            return TER_CATEGORY_B
        elif prefix == "K" and suffix == "0":
            return TER_CATEGORY_B
        elif prefix == "K" and suffix in ["1", "2", "3"]:
            return TER_CATEGORY_C
        elif prefix == "HB":  # Single parent
            return TER_CATEGORY_C
        else:
            # Default to highest category
            return TER_CATEGORY_C
    except Exception as e:
        frappe.log_error(f"Error mapping PTKP to TER: {str(e)}", "PTKP-TER Mapping Error")
        return TER_CATEGORY_C  # Default to highest category on error


def get_ter_rate(status_pajak, penghasilan_bruto):
    """
    Get TER rate for a specific tax status and income level

    Args:
        status_pajak (str): Tax status (TK0, K0, etc)
        penghasilan_bruto (float): Gross income

    Returns:
        float: TER rate as decimal (e.g., 0.05 for 5%)
    """
    try:
        # Validate inputs
        if not status_pajak:
            status_pajak = "TK0"

        if not penghasilan_bruto:
            penghasilan_bruto = 0

        penghasilan_bruto = flt(penghasilan_bruto)
        if penghasilan_bruto < 0:
            penghasilan_bruto = abs(penghasilan_bruto)

        # Map PTKP status to TER category using new centralized function
        ter_category = get_ter_category(status_pajak)

        # Create cache key
        cache_key = (
            f"ter_rate:{ter_category}:{int(penghasilan_bruto/1000)*1000}"  # Round to nearest 1000
        )
        cached_rate = frappe.cache().get_value(cache_key)

        if cached_rate is not None:
            return cached_rate

        # Try getting rate from settings
        settings = get_settings()
        if settings:
            # Check if settings has a method to get TER rate
            if hasattr(settings, "get_ter_rate") and callable(settings.get_ter_rate):
                try:
                    rate = settings.get_ter_rate(ter_category, penghasilan_bruto)
                    if rate is not None:
                        # Convert to decimal
                        decimal_rate = flt(rate) / 100.0
                        frappe.cache().set_value(
                            cache_key, decimal_rate, expires_in_sec=CACHE_MEDIUM
                        )
                        return decimal_rate
                except Exception as e:
                    frappe.log_error(
                        f"Error getting TER rate from settings: {str(e)}", "TER Rate Error"
                    )

        # Query from database
        if frappe.db.exists("DocType", "PPh 21 TER Table"):
            ter = frappe.db.sql(
                """
                SELECT rate
                FROM `tabPPh 21 TER Table`
                WHERE status_pajak = %s
                  AND %s >= income_from
                  AND (%s < income_to OR income_to = 0)
                ORDER BY income_from DESC
                LIMIT 1
            """,
                (ter_category, penghasilan_bruto, penghasilan_bruto),
                as_dict=1,
            )

            if ter:
                rate = flt(ter[0].rate) / 100.0
                frappe.cache().set_value(cache_key, rate, expires_in_sec=CACHE_MEDIUM)
                return rate

            # Try to find highest bracket
            ter = frappe.db.sql(
                """
                SELECT rate
                FROM `tabPPh 21 TER Table`
                WHERE status_pajak = %s
                  AND is_highest_bracket = 1
                LIMIT 1
            """,
                (ter_category,),
                as_dict=1,
            )

            if ter:
                rate = flt(ter[0].rate) / 100.0
                frappe.cache().set_value(cache_key, rate, expires_in_sec=CACHE_MEDIUM)
                return rate

        # Default rates if not found
        if ter_category == TER_CATEGORY_A:
            rate = 0.05
        elif ter_category == TER_CATEGORY_B:
            rate = 0.10
        else:  # TER_CATEGORY_C
            rate = 0.15

        frappe.cache().set_value(cache_key, rate, expires_in_sec=CACHE_MEDIUM)
        return rate

    except Exception as e:
        frappe.log_error(
            f"Error getting TER rate for status {status_pajak} and income {penghasilan_bruto}: {str(e)}",
            "TER Rate Error",
        )
        return 0


def should_use_ter():
    """
    Check if TER method should be used based on Payroll Indonesia Settings

    Returns:
        bool: True if TER should be used, False otherwise
    """
    try:
        # Get settings from Payroll Indonesia Settings
        settings = get_settings()

        if not settings:
            return False

        calc_method = getattr(settings, "tax_calculation_method", "Progressive")
        use_ter = cint(getattr(settings, "use_ter", 0))

        # December always uses Progressive method as per PMK 168/2023
        current_month = getdate().month
        if current_month == 12:
            return False

        # Check settings
        return calc_method == "TER" and use_ter
    except Exception as e:
        frappe.log_error(f"Error checking TER method settings: {str(e)}", "TER Settings Error")
        return False


# YTD Functions - Consolidated for easier testing and reuse
def get_employee_details(employee_id=None, salary_slip=None):
    """
    Get employee details from either employee ID or salary slip
    with efficient caching

    Args:
        employee_id (str, optional): Employee ID
        salary_slip (str, optional): Salary slip name to extract employee ID from

    Returns:
        dict: Employee details
    """
    try:
        if not employee_id and not salary_slip:
            return None

        # If salary slip provided but not employee_id, extract it from salary slip
        if not employee_id and salary_slip:
            # Check cache for salary slip
            slip_cache_key = f"salary_slip:{salary_slip}"
            slip = get_cached_value(slip_cache_key)

            if slip is None:
                # Query employee directly from salary slip if not in cache
                employee_id = frappe.db.get_value("Salary Slip", salary_slip, "employee")

                if not employee_id:
                    # Salary slip not found or doesn't have employee
                    return None
            else:
                # Extract employee_id from cached slip
                employee_id = slip.employee

        # Now we should have employee_id, get employee details from cache or DB
        cache_key = f"employee_details:{employee_id}"
        employee_data = get_cached_value(cache_key)

        if employee_data is None:
            # Query employee document
            employee_doc = frappe.get_doc("Employee", employee_id)

            # Extract relevant fields for lighter caching
            employee_data = {
                "name": employee_doc.name,
                "employee_name": employee_doc.employee_name,
                "company": employee_doc.company,
                "status_pajak": getattr(employee_doc, "status_pajak", "TK0"),
                "npwp": getattr(employee_doc, "npwp", ""),
                "ktp": getattr(employee_doc, "ktp", ""),
                "ikut_bpjs_kesehatan": cint(getattr(employee_doc, "ikut_bpjs_kesehatan", 1)),
                "ikut_bpjs_ketenagakerjaan": cint(
                    getattr(employee_doc, "ikut_bpjs_ketenagakerjaan", 1)
                ),
            }

            # Cache employee data
            cache_value(cache_key, employee_data, CACHE_MEDIUM)

        return employee_data

    except Exception as e:
        frappe.log_error(
            "Error retrieving employee details for {0} or slip {1}: {2}".format(
                employee_id or "unknown", salary_slip or "unknown", str(e)
            ),
            "Employee Details Error",
        )
        return None


def get_ytd_totals(
    employee: str, year: int, month: int, include_current: bool = False
) -> Dict[str, Any]:
    """
    Get YTD tax and other totals for an employee with caching
    This centralized function provides consistent YTD data across the module

    Args:
        employee: Employee ID
        year: Tax year
        month: Current month (1-12)
        include_current: Whether to include current month

    Returns:
        dict: Dictionary with ytd_gross, ytd_tax, ytd_bpjs, etc.
    """
    try:
        # Validate inputs
        if not employee or not year or not month:
            return {
                "ytd_gross": 0,
                "ytd_tax": 0,
                "ytd_bpjs": 0,
                "ytd_biaya_jabatan": 0,
                "ytd_netto": 0,
            }

        # Create cache key - include current month flag
        current_flag = "with_current" if include_current else "without_current"
        cache_key = f"ytd:{employee}:{year}:{month}:{current_flag}"

        # Check cache first
        cached_result = get_cached_value(cache_key)

        if cached_result is not None:
            return cached_result

        # First try to get from tax summary
        from_summary = get_ytd_totals_from_tax_summary(employee, year, month, include_current)

        # If summary had data, use it
        if from_summary and from_summary.get("has_data", False):
            # Cache result
            cache_value(cache_key, from_summary, CACHE_MEDIUM)
            return from_summary

        # If summary didn't have data or was incomplete, calculate from salary slips
        result = calculate_ytd_from_salary_slips(employee, year, month, include_current)

        # Cache result
        cache_value(cache_key, result, CACHE_MEDIUM)
        return result

    except Exception as e:
        frappe.log_error(
            "Error getting YTD totals for {0}, year {1}, month {2}: {3}".format(
                employee, year, month, str(e)
            ),
            "YTD Totals Error",
        )
        # Return default values on error
        return {"ytd_gross": 0, "ytd_tax": 0, "ytd_bpjs": 0, "ytd_biaya_jabatan": 0, "ytd_netto": 0}


def get_ytd_totals_from_tax_summary(
    employee: str, year: int, month: int, include_current: bool = False
) -> Dict[str, Any]:
    """
    Get YTD tax totals from Employee Tax Summary with efficient caching

    Args:
        employee: Employee ID
        year: Tax year
        month: Current month (1-12)
        include_current: Whether to include current month

    Returns:
        dict: Dictionary with YTD totals and summary data
    """
    try:
        # Find Employee Tax Summary for this year
        tax_summary = frappe.db.get_value(
            "Employee Tax Summary",
            {"employee": employee, "year": year},
            ["name", "ytd_tax"],
            as_dict=1,
        )

        if not tax_summary:
            return {"has_data": False}

        # Prepare filter for monthly details
        month_filter = ["<=", month] if include_current else ["<", month]

        # Efficient query to get monthly details with all fields at once
        monthly_details = frappe.get_all(
            "Employee Tax Summary Detail",
            filters={"parent": tax_summary.name, "month": month_filter},
            fields=[
                "gross_pay",
                "bpjs_deductions",
                "tax_amount",
                "month",
                "is_using_ter",
                "ter_rate",
            ],
        )

        if not monthly_details:
            return {"has_data": False}

        # Calculate YTD totals
        ytd_gross = sum(flt(d.gross_pay) for d in monthly_details)
        ytd_bpjs = sum(flt(d.bpjs_deductions) for d in monthly_details)
        ytd_tax = sum(
            flt(d.tax_amount) for d in monthly_details
        )  # Use sum instead of tax_summary.ytd_tax to ensure consistency

        # Estimate biaya_jabatan if not directly available
        ytd_biaya_jabatan = 0
        for detail in monthly_details:
            # Rough estimate using standard formula - this should be improved if possible
            if flt(detail.gross_pay) > 0:
                # Use constants for calculation
                monthly_biaya_jabatan = min(
                    flt(detail.gross_pay) * (BIAYA_JABATAN_PERCENT / 100), BIAYA_JABATAN_MAX
                )
                ytd_biaya_jabatan += monthly_biaya_jabatan

        # Calculate netto
        ytd_netto = ytd_gross - ytd_bpjs - ytd_biaya_jabatan

        # Extract latest TER information
        is_using_ter = False
        highest_ter_rate = 0

        for detail in monthly_details:
            if detail.is_using_ter:
                is_using_ter = True
                if flt(detail.ter_rate) > highest_ter_rate:
                    highest_ter_rate = flt(detail.ter_rate)

        result = {
            "has_data": True,
            "ytd_gross": ytd_gross,
            "ytd_tax": ytd_tax,
            "ytd_bpjs": ytd_bpjs,
            "ytd_biaya_jabatan": ytd_biaya_jabatan,
            "ytd_netto": ytd_netto,
            "is_using_ter": is_using_ter,
            "ter_rate": highest_ter_rate,
            "source": "tax_summary",
            "summary_name": tax_summary.name,
        }

        return result

    except Exception as e:
        frappe.log_error(
            "Error getting YTD tax data from summary for {0}, year {1}, month {2}: {3}".format(
                employee, year, month, str(e)
            ),
            "YTD Tax Summary Error",
        )
        return {"has_data": False}


def calculate_ytd_from_salary_slips(
    employee: str, year: int, month: int, include_current: bool = False
) -> Dict[str, Any]:
    """
    Calculate YTD totals from salary slips with caching

    Args:
        employee: Employee ID
        year: Tax year
        month: Current month (1-12)
        include_current: Whether to include current month

    Returns:
        dict: Dictionary with ytd_gross, ytd_tax, ytd_bpjs, etc.
    """
    try:
        # Calculate date range
        start_date = f"{year}-01-01"

        if include_current:
            end_date = f"{year}-{month:02d}-31"  # Use end of month
        else:
            # Use end of previous month
            if month > 1:
                end_date = f"{year}-{(month-1):02d}-31"
            else:
                # If month is January and not including current, return zeros
                return {
                    "has_data": True,
                    "ytd_gross": 0,
                    "ytd_tax": 0,
                    "ytd_bpjs": 0,
                    "ytd_biaya_jabatan": 0,
                    "ytd_netto": 0,
                    "is_using_ter": False,
                    "ter_rate": 0,
                    "source": "salary_slips",
                }

        # Get salary slips within date range using parameterized query
        slips_query = """
            SELECT name, gross_pay, is_using_ter, ter_rate, biaya_jabatan, posting_date
            FROM `tabSalary Slip`
            WHERE employee = %s
            AND start_date >= %s
            AND end_date <= %s
            AND docstatus = 1
        """

        slips = frappe.db.sql(slips_query, [employee, start_date, end_date], as_dict=1)

        if not slips:
            return {
                "has_data": True,
                "ytd_gross": 0,
                "ytd_tax": 0,
                "ytd_bpjs": 0,
                "ytd_biaya_jabatan": 0,
                "ytd_netto": 0,
                "is_using_ter": False,
                "ter_rate": 0,
                "source": "salary_slips",
            }

        # Prepare for efficient batch query of all components
        slip_names = [slip.name for slip in slips]

        # Get all components at once
        components_query = """
            SELECT sd.parent, sd.salary_component, sd.amount
            FROM `tabSalary Detail` sd
            WHERE sd.parent IN %s
            AND sd.parentfield = 'deductions'
            AND sd.salary_component IN ('PPh 21', 'BPJS JHT Employee', 'BPJS JP Employee', 'BPJS Kesehatan Employee')
        """

        components = frappe.db.sql(components_query, [tuple(slip_names)], as_dict=1)

        # Organize components by slip
        slip_components = {}
        for comp in components:
            if comp.parent not in slip_components:
                slip_components[comp.parent] = []
            slip_components[comp.parent].append(comp)

        # Calculate totals
        ytd_gross = 0
        ytd_tax = 0
        ytd_bpjs = 0
        ytd_biaya_jabatan = 0
        is_using_ter = False
        highest_ter_rate = 0

        for slip in slips:
            ytd_gross += flt(slip.gross_pay)
            ytd_biaya_jabatan += flt(getattr(slip, "biaya_jabatan", 0))

            # Check TER info
            if getattr(slip, "is_using_ter", 0):
                is_using_ter = True
                if flt(getattr(slip, "ter_rate", 0)) > highest_ter_rate:
                    highest_ter_rate = flt(getattr(slip, "ter_rate", 0))

            # Process components for this slip
            slip_comps = slip_components.get(slip.name, [])
            for comp in slip_comps:
                if comp.salary_component == "PPh 21":
                    ytd_tax += flt(comp.amount)
                elif comp.salary_component in [
                    "BPJS JHT Employee",
                    "BPJS JP Employee",
                    "BPJS Kesehatan Employee",
                ]:
                    ytd_bpjs += flt(comp.amount)

        # If biaya_jabatan wasn't in slips, estimate it
        if ytd_biaya_jabatan == 0 and ytd_gross > 0:
            # Apply standard formula per month
            months_processed = len(
                {
                    getdate(slip.posting_date).month
                    for slip in slips
                    if hasattr(slip, "posting_date")
                }
            )
            months_processed = max(1, months_processed)  # Ensure at least 1 month

            # Use constants for calculation
            ytd_biaya_jabatan = min(
                ytd_gross * (BIAYA_JABATAN_PERCENT / 100), BIAYA_JABATAN_MAX * months_processed
            )

        # Calculate netto
        ytd_netto = ytd_gross - ytd_bpjs - ytd_biaya_jabatan

        result = {
            "has_data": True,
            "ytd_gross": ytd_gross,
            "ytd_tax": ytd_tax,
            "ytd_bpjs": ytd_bpjs,
            "ytd_biaya_jabatan": ytd_biaya_jabatan,
            "ytd_netto": ytd_netto,
            "is_using_ter": is_using_ter,
            "ter_rate": highest_ter_rate,
            "source": "salary_slips",
        }

        return result

    except Exception as e:
        frappe.log_error(
            "Error calculating YTD totals from salary slips for {0}, year {1}, month {2}: {3}".format(
                employee, year, month, str(e)
            ),
            "YTD Salary Slip Error",
        )
        # Return default values
        return {
            "has_data": True,
            "ytd_gross": 0,
            "ytd_tax": 0,
            "ytd_bpjs": 0,
            "ytd_biaya_jabatan": 0,
            "ytd_netto": 0,
            "is_using_ter": False,
            "ter_rate": 0,
            "source": "fallback",
        }


def get_ytd_tax_info(employee, date=None):
    """
    Get year-to-date tax information for an employee
    Uses the centralized get_ytd_totals function

    Args:
        employee (str): Employee ID
        date (datetime, optional): Date to determine year and month, defaults to current date

    Returns:
        dict: YTD tax information
    """
    try:
        # Validate employee parameter
        if not employee:
            frappe.throw(_("Employee is required to get YTD tax information"))

        # Check if employee exists
        if not frappe.db.exists("Employee", employee):
            frappe.log_error(f"Employee {employee} does not exist", "YTD Tax Info Error")
            return {"ytd_tax": 0, "is_using_ter": 0, "ter_rate": 0}

        # Determine tax year and month from date
        if not date:
            date = getdate()

        year = date.year
        month = date.month

        # Get YTD totals using the centralized function
        ytd_data = get_ytd_totals(employee, year, month)

        # Return simplified result for backward compatibility
        return {
            "ytd_tax": flt(ytd_data.get("ytd_tax", 0)),
            "is_using_ter": ytd_data.get("is_using_ter", False),
            "ter_rate": flt(ytd_data.get("ter_rate", 0)),
        }

    except Exception as e:
        frappe.log_error(
            f"Error in get_ytd_tax_info for {employee}: {str(e)}", "YTD Tax Info Error"
        )

        # Return default values on error
        return {"ytd_tax": 0, "is_using_ter": 0, "ter_rate": 0}


def create_tax_summary_doc(employee, year, tax_amount=0, is_using_ter=0, ter_rate=0):
    """
    Create or update Employee Tax Summary document

    Args:
        employee (str): Employee ID
        year (int): Tax year
        tax_amount (float): PPh 21 amount to add
        is_using_ter (int): Whether TER method is used
        ter_rate (float): TER rate if applicable

    Returns:
        object: Employee Tax Summary document or None on error
    """
    try:
        # Validate required parameters
        if not employee:
            frappe.throw(_("Employee is required to create tax summary"))

        if not year or not isinstance(year, int):
            frappe.throw(_("Valid tax year is required to create tax summary"))

        # Convert numeric parameters
        tax_amount = flt(tax_amount)
        is_using_ter = cint(is_using_ter)
        ter_rate = flt(ter_rate)

        # Check if DocType exists
        if not frappe.db.exists("DocType", "Employee Tax Summary"):
            frappe.log_error(
                "Employee Tax Summary DocType does not exist", "Tax Summary Creation Error"
            )
            return None

        # Check if employee exists
        if not frappe.db.exists("Employee", employee):
            frappe.log_error(f"Employee {employee} does not exist", "Tax Summary Creation Error")
            return None

        # Check if tax summary exists for this employee and year
        name = frappe.db.get_value("Employee Tax Summary", {"employee": employee, "year": year})

        if name:
            # Update existing document
            doc = frappe.get_doc("Employee Tax Summary", name)

            # Update values
            doc.ytd_tax = flt(doc.ytd_tax) + tax_amount

            if is_using_ter:
                doc.is_using_ter = 1
                doc.ter_rate = max(doc.ter_rate or 0, ter_rate)

            # Save with flags to bypass validation
            doc.flags.ignore_validate_update_after_submit = True
            doc.save(ignore_permissions=True)

            return doc
        else:
            # Create new document
            employee_name = frappe.db.get_value("Employee", employee, "employee_name") or employee

            doc = frappe.new_doc("Employee Tax Summary")
            doc.employee = employee
            doc.employee_name = employee_name
            doc.year = year
            doc.ytd_tax = tax_amount

            # Set TER info if applicable
            if is_using_ter:
                doc.is_using_ter = 1
                doc.ter_rate = ter_rate

            # Set title if field exists
            if hasattr(doc, "title"):
                doc.title = f"{employee_name} - {year}"

            # Insert with flags to bypass validation
            doc.insert(ignore_permissions=True)

            return doc
    except Exception as e:
        frappe.log_error(
            f"Error creating tax summary for {employee}, year {year}: {str(e)}", "Tax Summary Error"
        )
        return None


# Account functions
def find_parent_account(
    company: str,
    parent_name: str,
    company_abbr: str,
    account_type: str,
    candidates: List[str] = None,
) -> Optional[str]:
    """
    Find parent account with multiple fallback options

    Args:
        company: Company name
        parent_name: Parent account name
        company_abbr: Company abbreviation
        account_type: Account type to find appropriate parent
        candidates: List of candidate parent account names to try

    Returns:
        str: Parent account name if found, None otherwise
    """
    debug_log(f"Finding parent account: {parent_name} for company {company}", "Account Lookup")

    # Try exact name
    parent = frappe.db.get_value(
        "Account", {"account_name": parent_name, "company": company}, "name"
    )
    if parent:
        debug_log(f"Found parent account by exact name match: {parent}", "Account Lookup")
        return parent

    # Try with company abbreviation
    parent = frappe.db.get_value("Account", {"name": f"{parent_name} - {company_abbr}"}, "name")
    if parent:
        debug_log(f"Found parent account with company suffix: {parent}", "Account Lookup")
        return parent

    # Get fallback parent account candidates
    parent_candidates = []

    # Determine which type of parent accounts to look for
    if "Payable" in parent_name or account_type in ["Payable", "Tax"]:
        # For liability accounts
        parent_candidates = candidates or [
            "Duties and Taxes",
            "Current Liabilities",
            "Accounts Payable",
        ]
        debug_log(
            f"Looking for liability parent among: {', '.join(parent_candidates)}", "Account Lookup"
        )
    else:
        # For expense accounts
        parent_candidates = candidates or ["Direct Expenses", "Indirect Expenses", "Expenses"]
        debug_log(
            f"Looking for expense parent among: {', '.join(parent_candidates)}", "Account Lookup"
        )

    # Try each candidate
    for candidate in parent_candidates:
        # Try exact account name
        candidate_account = frappe.db.get_value(
            "Account", {"account_name": candidate, "company": company}, "name"
        )

        if candidate_account:
            debug_log(f"Found parent {candidate_account} for {parent_name}", "Account Lookup")
            return candidate_account

        # Try with company abbreviation
        candidate_account = frappe.db.get_value(
            "Account", {"name": f"{candidate} - {company_abbr}"}, "name"
        )

        if candidate_account:
            debug_log(f"Found parent {candidate_account} for {parent_name}", "Account Lookup")
            return candidate_account

    # Try broad search for accounts with similar name
    similar_accounts = frappe.db.get_list(
        "Account",
        filters={"company": company, "is_group": 1, "account_name": ["like", f"%{parent_name}%"]},
        fields=["name"],
    )
    if similar_accounts:
        debug_log(f"Found similar parent account: {similar_accounts[0].name}", "Account Lookup")
        return similar_accounts[0].name

    # Try any group account of correct type as fallback
    # Use correct mapping for account types
    root_type = "Expense"  # Default for expense accounts
    if account_type in ["Payable", "Receivable", "Tax"]:
        root_type = "Liability"
    elif account_type in ["Direct Income", "Indirect Income", "Income Account"]:
        root_type = "Income"

    debug_log(f"Searching for any {root_type} group account as fallback", "Account Lookup")

    parents = frappe.get_all(
        "Account",
        filters={"company": company, "is_group": 1, "root_type": root_type},
        pluck="name",
        limit=1,
    )
    if parents:
        debug_log(f"Using fallback parent account: {parents[0]}", "Account Lookup")
        return parents[0]

    debug_log(
        f"Could not find any suitable parent account for {parent_name}", "Account Lookup Error"
    )
    return None


def create_account(
    company: str, account_name: str, account_type: str, parent: str, root_type: Optional[str] = None
) -> Optional[str]:
    """
    Create GL Account if not exists with standardized naming

    Args:
        company: Company name
        account_name: Account name without company abbreviation
        account_type: Account type (Payable, Expense, etc.)
        parent: Parent account name
        root_type: Root type (Asset, Liability, etc.). If None, determined from account_type.

    Returns:
        str: Full account name if created or already exists, None otherwise
    """
    try:
        # Validate inputs
        if not company or not account_name or not account_type or not parent:
            frappe.throw(_("Missing required parameters for account creation"))

        abbr = frappe.get_cached_value("Company", company, "abbr")
        if not abbr:
            frappe.throw(_("Company {0} does not have an abbreviation").format(company))

        # Ensure account name doesn't already include the company abbreviation
        pure_account_name = account_name.replace(f" - {abbr}", "")
        full_account_name = f"{pure_account_name} - {abbr}"

        # Check if account already exists
        if frappe.db.exists("Account", full_account_name):
            debug_log(f"Account {full_account_name} already exists", "Account Creation")

            # Verify account properties are correct
            account_doc = frappe.db.get_value(
                "Account",
                full_account_name,
                ["account_type", "parent_account", "company", "is_group"],
                as_dict=1,
            )

            if (
                account_doc.account_type != account_type
                or account_doc.parent_account != parent
                or account_doc.company != company
            ):
                debug_log(
                    f"Account {full_account_name} exists but has different properties. "
                    f"Expected: type={account_type}, parent={parent}, company={company}. "
                    f"Found: type={account_doc.account_type}, parent={account_doc.parent_account}, "
                    f"company={account_doc.company}",
                    "Account Warning",
                )
                # We don't change existing account properties, just return the name

            return full_account_name

        # Verify parent account exists
        if not frappe.db.exists("Account", parent):
            frappe.throw(_("Parent account {0} does not exist").format(parent))

        # Determine root_type based on account_type if not provided
        if not root_type:
            root_type = "Liability"  # Default
            if account_type in ["Direct Expense", "Indirect Expense", "Expense Account", "Expense"]:
                root_type = "Expense"
            elif account_type == "Asset":
                root_type = "Asset"
            elif account_type in ["Direct Income", "Indirect Income", "Income Account"]:
                root_type = "Income"

        # Create new account with explicit permissions
        debug_log(
            f"Creating account: {full_account_name} (Type: {account_type}, Parent: {parent})",
            "Account Creation",
        )

        doc = frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": pure_account_name,
                "company": company,
                "parent_account": parent,
                "account_type": account_type,
                "account_currency": frappe.get_cached_value("Company", company, "default_currency"),
                "is_group": 0,
                "root_type": root_type,
            }
        )

        # Bypass permissions and mandatory checks during setup
        doc.flags.ignore_permissions = True
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)

        # Commit database changes immediately
        frappe.db.commit()

        # Verify account was created
        if frappe.db.exists("Account", full_account_name):
            debug_log(f"Successfully created account: {full_account_name}", "Account Creation")
            return full_account_name
        else:
            frappe.throw(
                _("Failed to create account {0} despite no errors").format(full_account_name)
            )

    except Exception as e:
        frappe.log_error(
            f"Error creating account {account_name} for {company}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Account Creation Error",
        )
        debug_log(
            f"Error creating account {account_name}: {str(e)}", "Account Creation Error", trace=True
        )
        return None


def create_parent_liability_account(company: str) -> Optional[str]:
    """
    Create or get parent liability account for BPJS accounts

    Args:
        company: Company name

    Returns:
        str: Parent account name if created or already exists, None otherwise
    """
    try:
        # Validate company
        if not company:
            frappe.throw(_("Company is required to create parent liability account"))

        abbr = frappe.get_cached_value("Company", company, "abbr")
        if not abbr:
            frappe.throw(_("Company {0} does not have an abbreviation").format(company))

        # Get settings from Payroll Indonesia Settings
        settings = get_settings()
        account_name = "BPJS Payable"  # Default

        # Check if settings has a GL account configuration
        if settings:
            # Try to get GL accounts data from settings
            gl_accounts_data = {}
            try:
                if hasattr(settings, "gl_accounts") and settings.gl_accounts:
                    if isinstance(settings.gl_accounts, str):
                        gl_accounts_data = json.loads(settings.gl_accounts)
                    else:
                        gl_accounts_data = settings.gl_accounts
            except (ValueError, AttributeError):
                debug_log("Error parsing GL accounts data from settings", "Account Creation")

            # Look for parent_accounts configuration
            if gl_accounts_data and "parent_accounts" in gl_accounts_data:
                parent_accounts = gl_accounts_data.get("parent_accounts", {})
                if "bpjs_payable" in parent_accounts:
                    account_name = parent_accounts.get("bpjs_payable", {}).get(
                        "account_name", account_name
                    )

        parent_name = f"{account_name} - {abbr}"

        # Check if account already exists
        if frappe.db.exists("Account", parent_name):
            # Verify the account is a group account
            is_group = frappe.db.get_value("Account", parent_name, "is_group")
            if not is_group:
                # Convert to group account if needed
                try:
                    account_doc = frappe.get_doc("Account", parent_name)
                    account_doc.is_group = 1
                    account_doc.flags.ignore_permissions = True
                    account_doc.save()
                    frappe.db.commit()
                    debug_log(f"Updated {parent_name} to be a group account", "Account Fix")
                except Exception as e:
                    frappe.log_error(
                        f"Could not convert {parent_name} to group account: {str(e)}",
                        "Account Creation Error",
                    )
                    # Continue and return the account name anyway

            debug_log(f"Parent liability account {parent_name} already exists", "Account Creation")
            return parent_name

        # Find a suitable parent account
        parent_candidates = ["Duties and Taxes", "Current Liabilities", "Accounts Payable"]
        parent_account = find_parent_account(
            company=company,
            parent_name="Duties and Taxes",
            company_abbr=abbr,
            account_type="Payable",
            candidates=parent_candidates,
        )

        if not parent_account:
            # Try to find any liability group account as fallback
            liability_accounts = frappe.get_all(
                "Account",
                filters={"company": company, "is_group": 1, "root_type": "Liability"},
                order_by="lft",
                limit=1,
            )

            if liability_accounts:
                parent_account = liability_accounts[0].name
                debug_log(
                    f"Using fallback liability parent account: {parent_account}", "Account Creation"
                )
            else:
                frappe.throw(
                    _(
                        "No suitable liability parent account found for creating BPJS accounts in company {0}"
                    ).format(company)
                )
                return None

        # Create parent account with explicit error handling
        try:
            debug_log(
                f"Creating parent liability account {parent_name} under {parent_account}",
                "Account Creation",
            )

            doc = frappe.get_doc(
                {
                    "doctype": "Account",
                    "account_name": account_name,
                    "parent_account": parent_account,
                    "company": company,
                    "account_type": "Payable",
                    "account_currency": frappe.get_cached_value(
                        "Company", company, "default_currency"
                    ),
                    "is_group": 1,
                    "root_type": "Liability",
                }
            )

            # Bypass permissions and mandatory checks during setup
            doc.flags.ignore_permissions = True
            doc.flags.ignore_mandatory = True
            doc.insert(ignore_permissions=True)

            # Commit database changes immediately
            frappe.db.commit()

            # Verify account was created
            if frappe.db.exists("Account", parent_name):
                debug_log(
                    f"Successfully created parent liability account: {parent_name}",
                    "Account Creation",
                )
                return parent_name
            else:
                frappe.throw(
                    _("Failed to create parent liability account {0} despite no errors").format(
                        parent_name
                    )
                )

        except Exception as e:
            frappe.log_error(
                f"Error creating parent liability account {parent_name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Account Creation Error",
            )
            debug_log(
                f"Error creating parent liability account for {company}: {str(e)}",
                "Account Creation Error",
                trace=True,
            )
            return None

    except Exception as e:
        frappe.log_error(
            f"Critical error in create_parent_liability_account for {company}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Account Creation Error",
        )
        return None


def create_parent_expense_account(company: str) -> Optional[str]:
    """
    Create or get parent expense account for BPJS accounts

    Args:
        company: Company name

    Returns:
        str: Parent account name if created or already exists, None otherwise
    """
    try:
        # Validate company
        if not company:
            frappe.throw(_("Company is required to create parent expense account"))

        abbr = frappe.get_cached_value("Company", company, "abbr")
        if not abbr:
            frappe.throw(_("Company {0} does not have an abbreviation").format(company))

        # Get account name from Payroll Indonesia Settings
        settings = get_settings()
        account_name = "BPJS Expenses"  # Default

        # Check if settings has a GL account configuration
        if settings:
            # Try to get GL accounts data from settings
            gl_accounts_data = {}
            try:
                if hasattr(settings, "gl_accounts") and settings.gl_accounts:
                    if isinstance(settings.gl_accounts, str):
                        gl_accounts_data = json.loads(settings.gl_accounts)
                    else:
                        gl_accounts_data = settings.gl_accounts
            except (ValueError, AttributeError):
                debug_log("Error parsing GL accounts data from settings", "Account Creation")

            # Look for parent_accounts configuration
            if gl_accounts_data and "parent_accounts" in gl_accounts_data:
                parent_accounts = gl_accounts_data.get("parent_accounts", {})
                if "bpjs_expenses" in parent_accounts:
                    account_name = parent_accounts.get("bpjs_expenses", {}).get(
                        "account_name", account_name
                    )

        parent_name = f"{account_name} - {abbr}"

        # Check if account already exists
        if frappe.db.exists("Account", parent_name):
            # Verify the account is a group account
            is_group = frappe.db.get_value("Account", parent_name, "is_group")
            if not is_group:
                # Convert to group account if needed
                try:
                    account_doc = frappe.get_doc("Account", parent_name)
                    account_doc.is_group = 1
                    account_doc.flags.ignore_permissions = True
                    account_doc.save()
                    frappe.db.commit()
                    debug_log(f"Updated {parent_name} to be a group account", "Account Fix")
                except Exception as e:
                    frappe.log_error(
                        f"Could not convert {parent_name} to group account: {str(e)}",
                        "Account Creation Error",
                    )
                    # Continue and return the account name anyway

            debug_log(f"Parent expense account {parent_name} already exists", "Account Creation")
            return parent_name

        # Find a suitable parent account
        parent_candidates = ["Direct Expenses", "Indirect Expenses", "Expenses"]
        parent_account = find_parent_account(
            company=company,
            parent_name="Direct Expenses",
            company_abbr=abbr,
            account_type="Expense",
            candidates=parent_candidates,
        )

        if not parent_account:
            # Try to find any expense group account as fallback
            expense_accounts = frappe.get_all(
                "Account",
                filters={"company": company, "is_group": 1, "root_type": "Expense"},
                order_by="lft",
                limit=1,
            )

            if expense_accounts:
                parent_account = expense_accounts[0].name
                debug_log(
                    f"Using fallback expense parent account: {parent_account}", "Account Creation"
                )
            else:
                frappe.throw(
                    _(
                        "No suitable expense parent account found for creating BPJS accounts in company {0}"
                    ).format(company)
                )
                return None

        # Create parent account with explicit error handling
        try:
            debug_log(
                f"Creating parent expense account {parent_name} under {parent_account}",
                "Account Creation",
            )

            doc = frappe.get_doc(
                {
                    "doctype": "Account",
                    "account_name": account_name,
                    "parent_account": parent_account,
                    "company": company,
                    "account_type": "Expense",
                    "account_currency": frappe.get_cached_value(
                        "Company", company, "default_currency"
                    ),
                    "is_group": 1,
                    "root_type": "Expense",
                }
            )

            # Bypass permissions and mandatory checks during setup
            doc.flags.ignore_permissions = True
            doc.flags.ignore_mandatory = True
            doc.insert(ignore_permissions=True)

            # Commit database changes immediately
            frappe.db.commit()

            # Verify account was created
            if frappe.db.exists("Account", parent_name):
                debug_log(
                    f"Successfully created parent expense account: {parent_name}",
                    "Account Creation",
                )
                return parent_name
            else:
                frappe.throw(
                    _("Failed to create parent expense account {0} despite no errors").format(
                        parent_name
                    )
                )

        except Exception as e:
            frappe.log_error(
                f"Error creating parent expense account {parent_name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Account Creation Error",
            )
            debug_log(
                f"Error creating parent expense account for {company}: {str(e)}",
                "Account Creation Error",
                trace=True,
            )
            return None

    except Exception as e:
        frappe.log_error(
            f"Critical error in create_parent_expense_account for {company}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Account Creation Error",
        )
        return None


def retry_bpjs_mapping(companies: List[str]) -> None:
    """
    Background job to retry failed BPJS mapping creation
    Called via frappe.enqueue() from ensure_bpjs_mapping_for_all_companies

    Args:
        companies: List of company names to retry mapping for
    """
    if not companies:
        return

    try:
        # Import conditionally to avoid circular imports
        module_path = (
            "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping"
        )
        try:
            module = frappe.get_module(module_path)
            create_default_mapping = getattr(module, "create_default_mapping", None)
        except (ImportError, AttributeError) as e:
            frappe.log_error(
                f"Failed to import create_default_mapping: {str(e)}", "BPJS Mapping Error"
            )
            return

        if not create_default_mapping:
            frappe.log_error("create_default_mapping function not found", "BPJS Mapping Error")
            return

        # Get account mapping from Payroll Indonesia Settings
        settings = get_settings()

        # Get account mapping from settings
        account_mapping = {}
        if settings:
            # Try to get GL accounts data from settings
            gl_accounts_data = {}
            try:
                if hasattr(settings, "gl_accounts") and settings.gl_accounts:
                    if isinstance(settings.gl_accounts, str):
                        gl_accounts_data = json.loads(settings.gl_accounts)
                    else:
                        gl_accounts_data = settings.gl_accounts

                    if "bpjs_account_mapping" in gl_accounts_data:
                        account_mapping = gl_accounts_data["bpjs_account_mapping"]
            except (ValueError, AttributeError):
                debug_log("Error parsing GL accounts data from settings", "BPJS Mapping Retry")

        for company in companies:
            try:
                if not frappe.db.exists("BPJS Account Mapping", {"company": company}):
                    debug_log(
                        f"Retrying BPJS Account Mapping creation for {company}",
                        "BPJS Mapping Retry",
                    )
                    mapping_name = create_default_mapping(company, account_mapping)

                    if mapping_name:
                        frappe.logger().info(
                            f"Successfully created BPJS Account Mapping for {company} on retry"
                        )
                        debug_log(
                            f"Successfully created BPJS Account Mapping for {company} on retry",
                            "BPJS Mapping Retry",
                        )
                    else:
                        frappe.logger().warning(
                            f"Failed again to create BPJS Account Mapping for {company}"
                        )
                        debug_log(
                            f"Failed again to create BPJS Account Mapping for {company}",
                            "BPJS Mapping Retry Error",
                        )
            except Exception as e:
                frappe.log_error(
                    f"Error creating BPJS Account Mapping for {company} on retry: {str(e)}\n\n"
                    f"Traceback: {frappe.get_traceback()}",
                    "BPJS Mapping Retry Error",
                )
                debug_log(
                    f"Error in retry for company {company}: {str(e)}",
                    "BPJS Mapping Retry Error",
                    trace=True,
                )

    except Exception as e:
        frappe.log_error(
            f"Error in retry_bpjs_mapping: {str(e)}\n\n" f"Traceback: {frappe.get_traceback()}",
            "BPJS Mapping Retry Error",
        )
