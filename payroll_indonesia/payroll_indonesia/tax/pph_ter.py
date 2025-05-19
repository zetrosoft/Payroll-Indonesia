# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-19 08:17:45 by dannyaudian

"""
Tax Functions for TER (Tarif Efektif Rata-rata) Method
as per PMK 168/PMK.010/2023.

TER is a simplified tax calculation method used for Indonesian PPh 21 income tax.
Instead of calculating annual tax with progressive rates and dividing by 12,
it directly applies an effective rate to monthly income.

This module serves as the single source of truth for TER category mapping
and other TER-related utilities.
"""

import frappe
from frappe import _
from frappe.utils import flt, cint
import json
from typing import Dict, Any, List, Tuple, Optional, Union

# Import the cache utilities
from payroll_indonesia.utilities.cache_utils import get_cached_value, cache_value

# Import constants
from payroll_indonesia.constants import (
    CACHE_SHORT,
    CACHE_LONG,
    TER_CATEGORY_A,
    TER_CATEGORY_B,
    TER_CATEGORY_C,
    TER_CATEGORIES,
)

# Default rates by category based on PMK 168/2023
DEFAULT_TER_RATES = {
    TER_CATEGORY_A: 0.30,  # 30% for TER A
    TER_CATEGORY_B: 0.32,  # 32% for TER B
    TER_CATEGORY_C: 0.34,  # 34% for TER C
    "": 0.34,  # Default for empty category
}


def log_ter_error(error_type: str, message: str, data: Optional[Dict] = None) -> None:
    """
    Helper function to log TER-related errors in a consistent format
    
    Args:
        error_type: Type of error (e.g., "Mapping Error", "Rate Error")
        message: Error message
        data: Additional data to include in the log
    """
    try:
        # Create clean error title
        title = f"TER {error_type}"
        
        # Format message with data if provided
        if data:
            formatted_message = f"{message}\n\nData: {data}"
        else:
            formatted_message = message
            
        # Log the error
        frappe.log_error(formatted_message, title)
    except Exception:
        # Fallback to simple logging if the above fails
        try:
            frappe.log_error(message, "TER Error")
        except Exception:
            # If all else fails, silently fail
            pass


def map_ptkp_to_ter_category(status_pajak: str) -> str:
    """
    Map PTKP status to TER category according to PMK 168/2023.

    TER has three categories:
    - TER A: For taxpayers with PTKP status TK/0
    - TER B: For taxpayers with PTKP status K/0, TK/1, TK/2, TK/3
    - TER C: For taxpayers with PTKP status K/1, K/2, K/3, etc.

    Args:
        status_pajak (str): The PTKP status code (e.g., 'TK0', 'K1')

    Returns:
        str: The corresponding TER category ('TER A', 'TER B', or 'TER C')
    """
    try:
        # Validate input parameter
        if not status_pajak or not isinstance(status_pajak, str):
            # Use default if invalid
            log_ter_error(
                "Category Mapping", 
                f"Invalid tax status provided: {str(status_pajak)}, using TER C as default"
            )
            return TER_CATEGORY_C

        # Normalize status_pajak by removing whitespace and converting to uppercase
        status_pajak = status_pajak.strip().upper()
        
        # Return default for empty status
        if not status_pajak:
            return TER_CATEGORY_C

        # Check cache first
        cache_key = f"ter_mapping:{status_pajak}"
        cached_category = get_cached_value(cache_key)
        if cached_category:
            return cached_category

        # First check if we have configured mappings in the system
        # Get from PPh 21 Settings if available
        try:
            # Check for custom mapping in settings
            mapping = get_ter_mapping_from_settings()
            if mapping:
                for entry in mapping:
                    ptkp_list = entry.get("ptkp_status_list", "").split(",")
                    ptkp_list = [p.strip().upper() for p in ptkp_list]

                    if status_pajak in ptkp_list:
                        result = entry.get("ter_category", TER_CATEGORY_C)
                        cache_value(cache_key, result, CACHE_LONG)  # Cache for 24 hours
                        return result
        except Exception as e:
            # Non-critical error - we can fall back to default mapping
            log_ter_error(
                "Mapping Error",
                f"Error retrieving TER mapping from settings: {str(e)}",
                {"status_pajak": status_pajak}
            )
            # Continue with default mapping, don't show msgprint for better UX

        # Extract prefix and suffix for mapping
        # Use safe string operations to handle potential incorrect data
        try:
            prefix = status_pajak[:2] if len(status_pajak) >= 2 else status_pajak
            suffix = status_pajak[2:] if len(status_pajak) >= 3 else "0"
            
            # Try to convert suffix to int if possible (to handle numeric comparisons)
            numeric_suffix = None
            try:
                numeric_suffix = int(suffix)
            except (ValueError, TypeError):
                pass
        except Exception:
            # Fallback if string operations fail
            prefix = ""
            suffix = "0"
            numeric_suffix = None

        # Default mapping logic:
        if status_pajak == "TK0":
            result = TER_CATEGORY_A
        elif prefix == "TK" and (suffix in ["1", "2"] or numeric_suffix in [1, 2]):
            result = TER_CATEGORY_B
        elif prefix == "TK" and (suffix == "3" or numeric_suffix == 3):
            result = TER_CATEGORY_C
        elif prefix == "K" and (suffix == "0" or numeric_suffix == 0):
            result = TER_CATEGORY_B
        elif prefix == "K" and (suffix in ["1", "2", "3"] or (numeric_suffix is not None and 1 <= numeric_suffix <= 3)):
            result = TER_CATEGORY_C
        elif prefix == "HB":  # Special case for HB (single parent)
            result = TER_CATEGORY_C
        else:
            # If unsure, use the highest TER category
            result = TER_CATEGORY_C
            # Log warning about using default
            log_ter_error(
                "Mapping Warning",
                f"Unknown tax status {status_pajak} for TER mapping, defaulting to {result}",
                {"status_pajak": status_pajak}
            )

        # Cache the result
        cache_value(cache_key, result, CACHE_LONG)  # Cache for 24 hours
        return result

    except Exception as e:
        # Log error and return default category
        log_ter_error(
            "Critical Error",
            f"Error mapping PTKP {status_pajak} to TER category: {str(e)}",
            {"status_pajak": status_pajak}
        )
        # Return a safe default to prevent process failure
        return TER_CATEGORY_C


def get_ter_mapping_from_settings() -> List[Dict[str, Any]]:
    """
    Get TER mapping from PPh 21 Settings.

    Returns:
        List[Dict[str, Any]]: A list of mapping entries with PTKP status lists and TER categories
    """
    # Check cache first
    cache_key = "ter_mapping_settings"
    cached_mapping = get_cached_value(cache_key)
    if cached_mapping is not None:
        return cached_mapping

    try:
        # Get the settings
        if not frappe.db.exists("DocType", "PPh 21 Settings"):
            return []

        pph_settings = frappe.get_cached_doc("PPh 21 Settings")

        # Check if TER mapping is available
        if hasattr(pph_settings, "ter_mapping") and pph_settings.ter_mapping:
            result = pph_settings.ter_mapping
            cache_value(cache_key, result, CACHE_LONG)  # Cache for 24 hours
            return result

        # Check for legacy field
        if hasattr(pph_settings, "ter_category_mapping") and pph_settings.ter_category_mapping:
            try:
                # Legacy format might be JSON string
                mapping_data = pph_settings.ter_category_mapping
                if isinstance(mapping_data, str):
                    result = json.loads(mapping_data)
                else:
                    result = mapping_data

                cache_value(cache_key, result, CACHE_LONG)  # Cache for 24 hours
                return result
            except Exception as parse_error:
                # Non-critical error - we can continue with default mapping
                log_ter_error(
                    "Parse Error",
                    f"Error parsing legacy TER mapping: {str(parse_error)}"
                )
    except Exception as e:
        # Non-critical error - we can continue with default mapping
        log_ter_error(
            "Settings Error",
            f"Error retrieving TER mapping from PPh 21 Settings: {str(e)}"
        )

    # Return empty list if not found
    cache_value(cache_key, [], CACHE_LONG)  # Cache empty result for 24 hours
    return []


def get_ter_rate(income: Union[float, int], category: str = "") -> float:
    """
    Get the TER (Tarif Efektif Rata-rata) rate for a given income and category.
    Improved with better validation and fallbacks.

    Args:
        income (float): Monthly income amount
        category (str, optional): TER category ('TER A', 'TER B', 'TER C'). Defaults to empty string.

    Returns:
        float: The TER rate as decimal (e.g., 0.05 for 5%)
    """
    # Initialize with default values for safety
    default_rate = 0.34  # 34% as maximum default
    income_value = 0.0
    safe_category = TER_CATEGORY_C

    try:
        # Step 1: Validate income parameter
        try:
            income_value = flt(income)
        except (ValueError, TypeError):
            log_ter_error(
                "Rate Error", 
                f"Invalid income value: {income}, using 0",
                {"income": income, "category": category}
            )
            income_value = 0.0

        # Return 0 for zero or negative income
        if income_value <= 0:
            return 0.0

        # Step 2: Validate and normalize category parameter
        if not category or not isinstance(category, str):
            # If category is empty or not a string, default to TER C
            safe_category = TER_CATEGORY_C
            log_ter_error(
                "Rate Error",
                f"Empty or invalid TER category: '{category}', defaulting to '{safe_category}'",
                {"income": income_value, "category": category}
            )
        else:
            # Strip whitespace and ensure proper format
            safe_category = category.strip()
            
            # Validate the category
            if safe_category not in TER_CATEGORIES:
                # Default to TER C (highest rates) if invalid
                log_ter_error(
                    "Rate Error",
                    f"Invalid TER category: '{safe_category}', defaulting to '{TER_CATEGORY_C}'",
                    {"income": income_value, "category": safe_category}
                )
                safe_category = TER_CATEGORY_C

        # Step 3: Check cache based on normalized parameters
        # Round income to nearest thousand for better cache hits
        income_bracket = round(income_value, -3)
        cache_key = f"ter_rate:{safe_category}:{income_bracket}"

        # Check cache first
        cached_rate = get_cached_value(cache_key)
        if cached_rate is not None:
            return cached_rate

        # Step 4: Query database for rate with proper error handling
        try:
            # Use parameterized query to find exact bracket match
            ter = None
            
            # Check if database and table exist before querying
            if frappe.db.exists("DocType", "PPh 21 TER Table"):
                query = """
                    SELECT rate
                    FROM `tabPPh 21 TER Table`
                    WHERE status_pajak = %s
                    AND income_from <= %s
                    AND (income_to >= %s OR income_to = 0)
                    ORDER BY income_from DESC
                    LIMIT 1
                """
                ter = frappe.db.sql(query, [safe_category, income_value, income_value], as_dict=1)

            if ter and ter[0].get("rate") is not None:
                # Convert percentage to decimal
                rate = flt(ter[0].rate) / 100.0
                cache_value(cache_key, rate, CACHE_SHORT)  # Cache for 30 minutes
                return rate

            # If no exact match, try to find the highest bracket
            if frappe.db.exists("DocType", "PPh 21 TER Table"):
                query = """
                    SELECT rate
                    FROM `tabPPh 21 TER Table`
                    WHERE status_pajak = %s
                    AND is_highest_bracket = 1
                    LIMIT 1
                """
                ter = frappe.db.sql(query, [safe_category], as_dict=1)

            if ter and ter[0].get("rate") is not None:
                # Convert percentage to decimal
                rate = flt(ter[0].rate) / 100.0
                cache_value(cache_key, rate, CACHE_SHORT)  # Cache for 30 minutes
                return rate
                
        except Exception as e:
            log_ter_error(
                "Database Error", 
                f"Error querying TER rates from database: {str(e)}",
                {"income": income_value, "category": safe_category}
            )
            # Continue with fallback values

        # Step 5: Use default fallback values if no rate found
        default_rate = DEFAULT_TER_RATES.get(safe_category, 0.34)
        
        log_ter_error(
            "Rate Warning",
            f"No TER rate found for category '{safe_category}' and income {income_value}. Using default rate {default_rate * 100}%",
            {"income": income_value, "category": safe_category, "default_rate": default_rate}
        )

        # Cache the default rate
        cache_value(cache_key, default_rate, CACHE_SHORT)  # Cache for 30 minutes
        return default_rate

    except Exception as e:
        # Final fallback on catastrophic error
        log_ter_error(
            "Critical Error",
            f"Unhandled error retrieving TER rate: {str(e)}",
            {"income": income, "category": category}
        )
        
        # Return the most conservative default rate
        return DEFAULT_TER_RATES.get(TER_CATEGORY_C, 0.34)


def calculate_monthly_tax_with_ter(income: Union[float, int], ter_category: str = "") -> Tuple[float, float]:
    """
    Calculate monthly PPh 21 using TER method
    Enhanced with better validation and error handling

    Args:
        income (float): Monthly income amount
        ter_category (str): TER category ('TER A', 'TER B', 'TER C')

    Returns:
        tuple: (monthly_tax, ter_rate)
    """
    try:
        # Validate income parameter
        try:
            safe_income = flt(income)
        except (ValueError, TypeError):
            log_ter_error(
                "Calculation Error", 
                f"Invalid income value: {income}, using 0",
                {"income": income, "category": ter_category}
            )
            safe_income = 0.0

        # No tax for zero or negative income
        if safe_income <= 0:
            return 0.0, 0.0

        # Validate ter_category
        safe_category = ter_category.strip() if isinstance(ter_category, str) else ""
        
        # If category is empty or invalid, assign default
        if not safe_category or safe_category not in TER_CATEGORIES:
            # If ter_category is empty or not in valid categories, try to determine from other parameters
            # For this simplified version, we just use TER C as default
            safe_category = TER_CATEGORY_C
            log_ter_error(
                "Calculation Warning", 
                f"Invalid or empty TER category: '{ter_category}', defaulting to '{safe_category}'",
                {"income": safe_income, "category": ter_category}
            )

        # Get TER rate for income and category
        ter_rate = get_ter_rate(safe_income, safe_category)

        # Calculate tax
        monthly_tax = flt(safe_income * ter_rate)

        return monthly_tax, ter_rate
    
    except Exception as e:
        # Log error
        log_ter_error(
            "Calculation Error",
            f"Error calculating monthly tax with TER: {str(e)}",
            {"income": income, "category": ter_category}
        )
        
        # Return minimal values rather than raising exception to make the app more resilient
        # Use TER C's default rate for maximum safety
        default_rate = DEFAULT_TER_RATES.get(TER_CATEGORY_C, 0.34)
        try:
            # Try to calculate with default values
            income_value = flt(income)
            monthly_tax = flt(income_value * default_rate) if income_value > 0 else 0.0
            return monthly_tax, default_rate
        except Exception:
            # Ultimate fallback - return zeros
            return 0.0, DEFAULT_TER_RATES.get(TER_CATEGORY_C, 0.34)
