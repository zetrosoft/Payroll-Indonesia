# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 08:01:55 by dannyaudianlanjutkan

"""
Tax Functions for TER (Tarif Efektif Rata-rata) Method
as per PMK 168/PMK.010/2023.

TER is a simplified tax calculation method used for Indonesian PPh 21 income tax.
Instead of calculating annual tax with progressive rates and dividing by 12,
it directly applies an effective rate to monthly income.
"""

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate
from datetime import datetime
import json
from typing import Dict, Any, Optional, List, Tuple, Union

# Import the cache utilities
from payroll_indonesia.payroll_indonesia.utilities.cache_utils import get_cached_value, cache_value, clear_cache

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
                        cache_value(cache_key, result, 86400)  # Cache for 24 hours
                        return result
        except Exception as e:
            # Non-critical error - we can fall back to default mapping
            frappe.log_error(
                "Error retrieving TER mapping from settings: {0}".format(str(e)),
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
            result = "TER A"
        elif prefix == "TK" and suffix in ["1", "2", "3"]:
            result = "TER B"
        elif prefix == "K" and suffix == "0":
            result = "TER B"
        elif prefix == "K" and suffix in ["1", "2", "3"]:
            result = "TER C"
        elif prefix == "HB":  # Special case for HB (single parent)
            result = "TER C"
        else:
            # If unsure, use the highest TER category
            result = "TER C"
            # Log warning about using default
            frappe.log_error(
                "Unknown tax status {0} for TER mapping, defaulting to {1}".format(status_pajak, result),
                "TER Mapping Warning"
            )
            frappe.msgprint(
                _("Warning: Unknown tax status {0} for TER mapping. Using {1} as default.").format(status_pajak, result),
                indicator="orange"
            )
            
        # Cache the result
        cache_value(cache_key, result, 86400)  # Cache for 24 hours
        return result
            
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # This is a critical error - TER category is essential for tax calculation
        frappe.log_error(
            "Error mapping PTKP {0} to TER category: {1}".format(status_pajak, str(e)),
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
        pph_settings = frappe.get_single("PPh 21 Settings")
        
        # Check if TER mapping is available
        if hasattr(pph_settings, 'ter_mapping') and pph_settings.ter_mapping:
            result = pph_settings.ter_mapping
            cache_value(cache_key, result, 86400)  # Cache for 24 hours
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
                    
                cache_value(cache_key, result, 86400)  # Cache for 24 hours
                return result
            except Exception as parse_error:
                # Non-critical error - we can continue with default mapping
                frappe.log_error(
                    "Error parsing legacy TER mapping: {0}".format(str(parse_error)),
                    "TER Mapping Parse Error"
                )
    except Exception as e:
        # Non-critical error - we can continue with default mapping
        frappe.log_error(
            "Error retrieving TER mapping from PPh 21 Settings: {0}".format(str(e)),
            "TER Settings Error"
        )
    
    # Return empty list if not found
    cache_value(cache_key, [], 86400)  # Cache empty result for 24 hours
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
        if category not in ['TER A', 'TER B', 'TER C']:
            # Default to TER C (highest rates) if invalid
            frappe.log_error(
                "Invalid TER category '{0}', defaulting to 'TER C'".format(category),
                "TER Rate Error"
            )
            frappe.msgprint(
                _("Warning: Invalid TER category '{0}'. Using 'TER C' as default.").format(category),
                indicator="orange"
            )
            category = 'TER C'
            
        # Create cache key based on income bracket and category
        # Round income to nearest thousand for better cache hits
        income_bracket = round(income, -3)
        cache_key = f"ter_rate:{category}:{income_bracket}"
        
        # Check cache first
        cached_rate = get_cached_value(cache_key)
        if cached_rate is not None:
            return cached_rate
            
        # Query the TER rate from database
        ter = frappe.db.get_all(
            "PPh 21 TER Table",
            filters={
                "status_pajak": category,
                "income_from": ["<=", income],
                "income_to": [">=", income]
            },
            fields=["rate"],
            order_by="income_from desc",
            limit=1
        )
        
        if ter:
            # Convert percentage to decimal
            rate = flt(ter[0].rate) / 100.0
            cache_value(cache_key, rate, 3600)  # Cache for 1 hour
            return rate
            
        # If no exact match, try to find the highest bracket
        ter = frappe.db.get_all(
            "PPh 21 TER Table",
            filters={
                "status_pajak": category,
                "income_from": ["<=", income],
                "is_highest_bracket": 1
            },
            fields=["rate"],
            limit=1
        )
        
        if ter:
            # Convert percentage to decimal
            rate = flt(ter[0].rate) / 100.0
            cache_value(cache_key, rate, 3600)  # Cache for 1 hour
            return rate
            
        # If still not found, use the default fallback values based on PMK 168/2023
        # These are the highest rates for each category
        default_rates = {
            "TER A": 0.30,  # 30% for TER A
            "TER B": 0.32,  # 32% for TER B
            "TER C": 0.34   # 34% for TER C
        }
        
        default_rate = default_rates.get(category, 0.34)
        frappe.log_error(
            "No TER rate found for category '{0}' and income {1}. Using default rate {2}%".format(
                category, income, default_rate * 100
            ),
            "TER Rate Warning"
        )
        frappe.msgprint(
            _("Warning: Could not find TER rate for category '{0}' and income {1}. Using default rate {2}%.").format(
                category, income, default_rate * 100
            ),
            indicator="orange"
        )
        
        # Cache the default rate
        cache_value(cache_key, default_rate, 3600)  # Cache for 1 hour
        return default_rate
        
    except Exception as e:
        # This is a critical error for tax calculation
        frappe.log_error(
            "Error retrieving TER rate for category '{0}' and income {1}: {2}".format(
                category, income, str(e)
            ),
            "TER Rate Critical Error"
        )
        frappe.throw(_("Failed to determine TER rate: {0}").format(str(e)))

def calculate_income_tax_with_ter(monthly_income: float, status_pajak: str = 'TK0') -> Dict[str, Any]:
    """
    Calculate income tax using the TER method
    
    Args:
        monthly_income (float): Monthly gross income
        status_pajak (str, optional): PTKP status (e.g., 'TK0', 'K1'). Defaults to 'TK0'.
        
    Returns:
        Dict[str, Any]: Dictionary with tax calculation details
    """
    try:
        # Validate inputs
        if not monthly_income or monthly_income < 0:
            frappe.throw(_("Monthly income must be a positive number"))
            
        if not status_pajak:
            frappe.throw(_("Tax status (PTKP) is required"))
            
        # Get TER category
        ter_category = map_ptkp_to_ter_category(status_pajak)
        
        # Get TER rate
        ter_rate = get_ter_rate(monthly_income, ter_category)
        
        # Calculate tax
        monthly_tax = monthly_income * ter_rate
        
        # Return detailed calculation
        return {
            'monthly_income': monthly_income,
            'status_pajak': status_pajak,
            'ter_category': ter_category,
            'ter_rate': ter_rate,
            'ter_rate_percent': ter_rate * 100,
            'monthly_tax': monthly_tax,
            'annual_income': monthly_income * 12,
            'annual_tax': monthly_tax * 12
        }
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # This is a critical error for tax calculation
        frappe.log_error(
            "Error calculating income tax with TER method for income {0} and status {1}: {2}".format(
                monthly_income, status_pajak, str(e)
            ),
            "TER Calculation Error"
        )
        frappe.throw(_("Failed to calculate tax using TER method: {0}").format(str(e)))

def create_ter_table_entry(
    tax_category: str, 
    income_from: float, 
    income_to: float, 
    rate: float,
    is_highest_bracket: bool = False
) -> Dict[str, Any]:
    """
    Create a TER table entry
    
    Args:
        tax_category (str): TER category ('TER A', 'TER B', 'TER C')
        income_from (float): Lower income bracket limit
        income_to (float): Upper income bracket limit (0 for highest bracket)
        rate (float): TER rate as percentage (e.g., 5.0 for 5%)
        is_highest_bracket (bool, optional): Whether this is the highest bracket. Defaults to False.
        
    Returns:
        Dict[str, Any]: Created entry details or error message
    """
    try:
        # Validate inputs
        if tax_category not in ['TER A', 'TER B', 'TER C']:
            frappe.throw(_("Invalid TER category. Must be one of: 'TER A', 'TER B', 'TER C'"))
            
        if income_from < 0 or (income_to < income_from and income_to != 0):
            frappe.throw(_("Invalid income bracket. From must be >= 0 and To must be > From or 0"))
            
        if rate < 0 or rate > 100:
            frappe.throw(_("Invalid rate. Must be between 0 and 100"))
            
        # Check if entry already exists
        existing = frappe.db.get_all(
            "PPh 21 TER Table",
            filters={
                "status_pajak": tax_category,
                "income_from": income_from,
                "income_to": income_to
            },
            fields=["name"]
        )
        
        if existing:
            # Update existing entry
            doc = frappe.get_doc("PPh 21 TER Table", existing[0].name)
            doc.rate = rate
            doc.is_highest_bracket = is_highest_bracket
            doc.save()
            frappe.db.commit()
            
            # Clear cache
            clear_cache(f"ter_rate:{tax_category}:")
            
            return {
                "status": "updated",
                "message": _("Updated existing TER table entry"),
                "entry": doc.as_dict()
            }
        else:
            # Create new TER entry
            settings = frappe.get_single("PPh 21 Settings")
            
            # Create child table entry
            child_doc = frappe.new_doc("PPh 21 TER Table")
            child_doc.status_pajak = tax_category
            child_doc.income_from = income_from
            child_doc.income_to = income_to
            child_doc.rate = rate
            child_doc.is_highest_bracket = is_highest_bracket
            child_doc.parent = "PPh 21 Settings"
            child_doc.parenttype = "PPh 21 Settings"
            child_doc.parentfield = "ter_table"
            
            # Add to parent
            settings.append("ter_table", child_doc)
            settings.save()
            frappe.db.commit()
            
            # Clear cache
            clear_cache(f"ter_rate:{tax_category}:")
            
            return {
                "status": "created",
                "message": _("Created new TER table entry"),
                "entry": child_doc.as_dict()
            }
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # This is an administrative error, not a calculation error
        frappe.log_error(
            "Error creating TER table entry for category {0}, income range {1}-{2}, rate {3}%: {4}".format(
                tax_category, income_from, income_to, rate, str(e)
            ),
            "TER Table Entry Error"
        )
        frappe.throw(_("Failed to create TER table entry: {0}").format(str(e)))