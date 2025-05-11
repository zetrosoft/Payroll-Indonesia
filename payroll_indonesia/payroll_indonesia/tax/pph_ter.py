# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 15:30:13 by dannyaudian

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
from frappe.utils import flt, cint, getdate
from datetime import datetime
import json
from typing import Dict, Any, Optional, List, Tuple, Union

# Import the cache utilities
from payroll_indonesia.utilities.cache_utils import get_cached_value, cache_value, clear_cache

# Import constants
from payroll_indonesia.constants import (
    CACHE_MEDIUM, CACHE_SHORT, CACHE_LONG,
    TER_CATEGORY_A, TER_CATEGORY_B, TER_CATEGORY_C, TER_CATEGORIES,
    TER_MAX_RATE
)

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
        if not status_pajak:
            # Critical error - tax status is required
            frappe.log_error(
                "Empty tax status provided for TER category mapping",
                "TER Category Mapping Error"
            )
            frappe.throw(_("Cannot determine TER category: Tax status (PTKP) is required"))
        
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
                    ptkp_list = entry.get('ptkp_status_list', '').split(',')
                    ptkp_list = [p.strip() for p in ptkp_list]
                    
                    if status_pajak in ptkp_list:
                        result = entry.get('ter_category', 'TER C')
                        cache_value(cache_key, result, CACHE_LONG)  # Cache for 24 hours
                        return result
        except Exception as e:
            # Non-critical error - we can fall back to default mapping
            frappe.log_error(
                f"Error retrieving TER mapping from settings: {str(e)}",
                "TER Mapping Error"
            )
            frappe.msgprint(
                _("Warning: Could not retrieve TER mapping from settings. Using default mapping."),
                indicator="orange"
            )
                
        # Use the default mapping as per PMK 168/2023
        prefix = status_pajak[:2] if len(status_pajak) >= 2 else status_pajak
        suffix = status_pajak[2:] if len(status_pajak) >= 3 else "0"
        
        # Default mapping logic:
        if status_pajak == "TK0":
            result = TER_CATEGORY_A
        elif prefix == "TK" and suffix in ["1", "2"]:
            result = TER_CATEGORY_B
        elif prefix == "TK" and suffix == "3":
            result = TER_CATEGORY_C
        elif prefix == "K" and suffix == "0":
            result = TER_CATEGORY_B
        elif prefix == "K" and suffix in ["1", "2", "3"]:
            result = TER_CATEGORY_C
        elif prefix == "HB":  # Special case for HB (single parent)
            result = TER_CATEGORY_C
        else:
            # If unsure, use the highest TER category
            result = TER_CATEGORY_C
            # Log warning about using default
            frappe.log_error(
                f"Unknown tax status {status_pajak} for TER mapping, defaulting to {result}",
                "TER Mapping Warning"
            )
            frappe.msgprint(
                _("Warning: Unknown tax status {0} for TER mapping. Using {1} as default.").format(status_pajak, result),
                indicator="orange"
            )
            
        # Cache the result
        cache_value(cache_key, result, CACHE_LONG)  # Cache for 24 hours
        return result
            
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # This is a critical error - TER category is essential for tax calculation
        frappe.log_error(
            f"Error mapping PTKP {status_pajak} to TER category: {str(e)}",
            "TER Mapping Critical Error"
        )
        frappe.throw(
            _("Failed to determine TER category for tax status {0}: {1}").format(status_pajak, str(e))
        )

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
        if hasattr(pph_settings, 'ter_mapping') and pph_settings.ter_mapping:
            result = pph_settings.ter_mapping
            cache_value(cache_key, result, CACHE_LONG)  # Cache for 24 hours
            return result
            
        # Check for legacy field
        if hasattr(pph_settings, 'ter_category_mapping') and pph_settings.ter_category_mapping:
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
                frappe.log_error(
                    f"Error parsing legacy TER mapping: {str(parse_error)}",
                    "TER Mapping Parse Error"
                )
    except Exception as e:
        # Non-critical error - we can continue with default mapping
        frappe.log_error(
            f"Error retrieving TER mapping from PPh 21 Settings: {str(e)}",
            "TER Settings Error"
        )
    
    # Return empty list if not found
    cache_value(cache_key, [], CACHE_LONG)  # Cache empty result for 24 hours
    return []

def get_ter_rate(income: float, category: str = 'TER C') -> float:
    """
    Get the TER (Tarif Efektif Rata-rata) rate for a given income and category.
    
    Args:
        income (float): Monthly income amount
        category (str, optional): TER category ('TER A', 'TER B', 'TER C'). Defaults to 'TER C'.
        
    Returns:
        float: The TER rate as decimal (e.g., 0.05 for 5%)
    """
    try:
        if income <= 0:
            return 0
            
        # Validate the category
        if category not in TER_CATEGORIES:
            # Default to TER C (highest rates) if invalid
            frappe.log_error(
                f"Invalid TER category '{category}', defaulting to '{TER_CATEGORY_C}'",
                "TER Rate Error"
            )
            frappe.msgprint(
                _("Warning: Invalid TER category '{0}'. Using '{1}' as default.").format(category, TER_CATEGORY_C),
                indicator="orange"
            )
            category = TER_CATEGORY_C
            
        # Create cache key based on income bracket and category
        # Round income to nearest thousand for better cache hits
        income_bracket = round(income, -3)
        cache_key = f"ter_rate:{category}:{income_bracket}"
        
        # Check cache first
        cached_rate = get_cached_value(cache_key)
        if cached_rate is not None:
            return cached_rate

        # Use parameterized query to find exact bracket match
        query = """
            SELECT rate
            FROM `tabPPh 21 TER Table`
            WHERE status_pajak = %s
            AND income_from <= %s
            AND (income_to >= %s OR income_to = 0)
            ORDER BY income_from DESC
            LIMIT 1
        """
        ter = frappe.db.sql(
            query,
            [category, income, income],
            as_dict=1
        )
        
        if ter:
            # Convert percentage to decimal
            rate = flt(ter[0].rate) / 100.0
            cache_value(cache_key, rate, CACHE_SHORT)  # Cache for 30 minutes
            return rate
            
        # If no exact match, try to find the highest bracket using parameterized query
        query = """
            SELECT rate
            FROM `tabPPh 21 TER Table`
            WHERE status_pajak = %s
            AND is_highest_bracket = 1
            LIMIT 1
        """
        ter = frappe.db.sql(
            query,
            [category],
            as_dict=1
        )
        
        if ter:
            # Convert percentage to decimal
            rate = flt(ter[0].rate) / 100.0
            cache_value(cache_key, rate, CACHE_SHORT)  # Cache for 30 minutes
            return rate
            
        # If still not found, use the default fallback values based on PMK 168/2023
        # These are the highest rates for each category
        default_rates = {
            TER_CATEGORY_A: 0.30,  # 30% for TER A
            TER_CATEGORY_B: 0.32,  # 32% for TER B
            TER_CATEGORY_C: 0.34   # 34% for TER C
        }
        
        default_rate = default_rates.get(category, 0.34)
        frappe.log_error(
            f"No TER rate found for category '{category}' and income {income}. Using default rate {default_rate * 100}%",
            "TER Rate Warning"
        )
        frappe.msgprint(
            _("Warning: Could not find TER rate for category '{0}' and income {1}. Using default rate {2}%.").format(
                category, income, default_rate * 100
            ),
            indicator="orange"
        )
        
        # Cache the default rate
        cache_value(cache_key, default_rate, CACHE_SHORT)  # Cache for 30 minutes
        return default_rate
        
    except Exception as e:
        # This is a critical error for tax calculation
        frappe.log_error(
            f"Error retrieving TER rate for category '{category}' and income {income}: {str(e)}",
            "TER Rate Critical Error"
        )
        frappe.throw(_("Failed to determine TER rate: {0}").format(str(e)))

def calculate_monthly_tax_with_ter(income: float, ter_category: str) -> Tuple[float, float]:
    """
    Calculate monthly PPh 21 using TER method
    
    Args:
        income (float): Monthly income amount
        ter_category (str): TER category ('TER A', 'TER B', 'TER C')
        
    Returns:
        tuple: (monthly_tax, ter_rate)
    """
    try:
        # Get TER rate for income and category
        ter_rate = get_ter_rate(income, ter_category)
        
        # Calculate tax
        monthly_tax = flt(income * ter_rate)
        
        return monthly_tax, ter_rate
    except Exception as e:
        # Log error and re-raise
        frappe.log_error(
            f"Error calculating monthly tax with TER for income {income}: {str(e)}",
            "TER Calculation Error"
        )
        raise