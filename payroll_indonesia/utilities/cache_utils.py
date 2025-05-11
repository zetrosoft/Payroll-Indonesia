# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 05:48:47 by dannyaudian

import frappe
from frappe.utils import now_datetime, add_to_date

# Cache containers with module-level scope
_TER_RATE_CACHE = {}
_TER_RATE_LAST_CLEAR = now_datetime()

_YTD_CACHE = {}
_YTD_CACHE_LAST_CLEAR = now_datetime()

_PTKP_MAPPING_CACHE = {}
_PTKP_MAPPING_LAST_CLEAR = now_datetime()

# Cache for tax settings to avoid repeated DB queries
_TAX_SETTINGS_CACHE = {}
_TAX_SETTINGS_LAST_CLEAR = now_datetime()

# Constants for cache timing
TER_CACHE_TIMEOUT_SECONDS = 1800  # 30 minutes
YTD_CACHE_TIMEOUT_SECONDS = 3600  # 1 hour
PTKP_CACHE_TIMEOUT_SECONDS = 3600  # 1 hour
TAX_SETTINGS_CACHE_TIMEOUT_SECONDS = 3600  # 1 hour

def get_ter_rate_cache():
    """
    Get TER rate cache with auto-expiry check
    
    Returns:
        dict: The current TER rate cache
    """
    global _TER_RATE_CACHE, _TER_RATE_LAST_CLEAR
    
    # Check if cache clearing is needed
    now = now_datetime()
    if (now - _TER_RATE_LAST_CLEAR).total_seconds() > TER_CACHE_TIMEOUT_SECONDS:
        _TER_RATE_CACHE = {}
        _TER_RATE_LAST_CLEAR = now
        frappe.logger().debug("TER rate cache cleared due to timeout")
    
    return _TER_RATE_CACHE

def get_ytd_cache():
    """
    Get YTD cache with auto-expiry check
    
    Returns:
        dict: The current YTD cache
    """
    global _YTD_CACHE, _YTD_CACHE_LAST_CLEAR
    
    # Check if cache clearing is needed
    now = now_datetime()
    if (now - _YTD_CACHE_LAST_CLEAR).total_seconds() > YTD_CACHE_TIMEOUT_SECONDS:
        _YTD_CACHE = {}
        _YTD_CACHE_LAST_CLEAR = now
        frappe.logger().debug("YTD cache cleared due to timeout")
    
    return _YTD_CACHE

def get_ptkp_mapping_cache():
    """
    Get PTKP mapping cache with auto-expiry check
    
    Returns:
        dict: The current PTKP mapping cache
    """
    global _PTKP_MAPPING_CACHE, _PTKP_MAPPING_LAST_CLEAR
    
    # Check if cache clearing is needed
    now = now_datetime()
    if (now - _PTKP_MAPPING_LAST_CLEAR).total_seconds() > PTKP_CACHE_TIMEOUT_SECONDS:
        _PTKP_MAPPING_CACHE = {}
        _PTKP_MAPPING_LAST_CLEAR = now
        frappe.logger().debug("PTKP mapping cache cleared due to timeout")
    
    return _PTKP_MAPPING_CACHE

def get_tax_settings_cache():
    """
    Get tax settings cache with auto-expiry check
    
    Returns:
        dict: The current tax settings cache
    """
    global _TAX_SETTINGS_CACHE, _TAX_SETTINGS_LAST_CLEAR
    
    # Check if cache clearing is needed
    now = now_datetime()
    if (now - _TAX_SETTINGS_LAST_CLEAR).total_seconds() > TAX_SETTINGS_CACHE_TIMEOUT_SECONDS:
        _TAX_SETTINGS_CACHE = {}
        _TAX_SETTINGS_LAST_CLEAR = now
        frappe.logger().debug("Tax settings cache cleared due to timeout")
    
    return _TAX_SETTINGS_CACHE

def clear_ter_cache():
    """Clear TER rate cache"""
    global _TER_RATE_CACHE, _TER_RATE_LAST_CLEAR
    _TER_RATE_CACHE = {}
    _TER_RATE_LAST_CLEAR = now_datetime()
    frappe.logger().debug("TER rate cache manually cleared")

def clear_ytd_cache():
    """Clear YTD cache"""
    global _YTD_CACHE, _YTD_CACHE_LAST_CLEAR
    _YTD_CACHE = {}
    _YTD_CACHE_LAST_CLEAR = now_datetime()
    frappe.logger().debug("YTD cache manually cleared")

def clear_ptkp_mapping_cache():
    """Clear PTKP mapping cache"""
    global _PTKP_MAPPING_CACHE, _PTKP_MAPPING_LAST_CLEAR
    _PTKP_MAPPING_CACHE = {}
    _PTKP_MAPPING_LAST_CLEAR = now_datetime()
    frappe.logger().debug("PTKP mapping cache manually cleared")

def clear_tax_settings_cache():
    """Clear tax settings cache"""
    global _TAX_SETTINGS_CACHE, _TAX_SETTINGS_LAST_CLEAR
    _TAX_SETTINGS_CACHE = {}
    _TAX_SETTINGS_LAST_CLEAR = now_datetime()
    frappe.logger().debug("Tax settings cache manually cleared")

def clear_all_caches():
    """Clear all caches related to payroll calculations"""
    clear_ter_cache()
    clear_ytd_cache()
    clear_ptkp_mapping_cache()
    clear_tax_settings_cache()
    
    # Also clear frappe caches for tax and payroll related keys
    cache_keys = [
        'tax_calculator_cache',
        'ter_calculator_cache',
        'ptkp_mapping',
        'ytd_tax_data'
    ]
    
    for key in cache_keys:
        frappe.cache().delete_key(key)
        
    frappe.logger().info("All payroll caches cleared")

def schedule_cache_clearing(minutes=30):
    """
    Schedule a background job to clear all caches after specified minutes
    
    Args:
        minutes (int): Minutes after which to clear caches
    """
    try:
        # Use enqueue to schedule the job
        frappe.enqueue(
            clear_all_caches,
            queue='long',
            is_async=True,
            job_name='clear_payroll_caches',
            enqueue_after=add_to_date(now_datetime(), minutes=minutes)
        )
        frappe.logger().debug(f"Scheduled cache clearing in {minutes} minutes")
        return True
    except Exception as e:
        frappe.logger().error(f"Error scheduling cache clearing: {str(e)}")
        return False

def cache_ter_rate(ter_category, income_bracket, rate_value):
    """
    Cache a TER rate value with appropriate key
    
    Args:
        ter_category (str): TER category (e.g., 'TER A')
        income_bracket (int): Income bracket rounded to nearest thousand
        rate_value (float): TER rate as decimal (e.g., 0.05 for 5%)
    """
    cache = get_ter_rate_cache()
    cache_key = f"{ter_category}:{income_bracket}"
    cache[cache_key] = rate_value

def get_cached_ter_rate(ter_category, income_bracket):
    """
    Get a cached TER rate value if it exists
    
    Args:
        ter_category (str): TER category (e.g., 'TER A')
        income_bracket (int): Income bracket rounded to nearest thousand
        
    Returns:
        float or None: Cached rate value or None if not found
    """
    cache = get_ter_rate_cache()
    cache_key = f"{ter_category}:{income_bracket}"
    return cache.get(cache_key)

def cache_ytd_data(employee, year, month, data):
    """
    Cache YTD data for an employee
    
    Args:
        employee (str): Employee ID
        year (int): Tax year
        month (int): Current month (1-12)
        data (dict): YTD data dictionary
    """
    cache = get_ytd_cache()
    cache_key = f"{employee}:{year}:{month}"
    cache[cache_key] = data

def get_cached_ytd_data(employee, year, month):
    """
    Get cached YTD data for an employee if it exists
    
    Args:
        employee (str): Employee ID
        year (int): Tax year
        month (int): Current month (1-12)
        
    Returns:
        dict or None: Cached YTD data or None if not found
    """
    cache = get_ytd_cache()
    cache_key = f"{employee}:{year}:{month}"
    return cache.get(cache_key)

def cache_ptkp_mapping(mapping):
    """
    Cache PTKP to TER category mapping
    
    Args:
        mapping (dict): PTKP to TER category mapping dictionary
    """
    global _PTKP_MAPPING_CACHE
    _PTKP_MAPPING_CACHE = mapping

def get_cached_ptkp_mapping():
    """
    Get cached PTKP to TER category mapping if it exists
    
    Returns:
        dict or None: Cached mapping or None if not found
    """
    cache = get_ptkp_mapping_cache()
    return cache if cache else None

def cache_tax_settings(key, value, expiry_seconds=None):
    """
    Cache tax settings with optional custom expiry
    
    Args:
        key (str): Cache key
        value (any): Value to cache
        expiry_seconds (int, optional): Custom expiry time in seconds
    """
    cache = get_tax_settings_cache()
    cache[key] = {
        'value': value,
        'timestamp': now_datetime(),
        'expiry': expiry_seconds or TAX_SETTINGS_CACHE_TIMEOUT_SECONDS
    }

def get_cached_tax_settings(key):
    """
    Get cached tax settings if it exists and has not expired
    
    Args:
        key (str): Cache key
        
    Returns:
        any or None: Cached value or None if not found or expired
    """
    cache = get_tax_settings_cache()
    entry = cache.get(key)
    
    if not entry:
        return None
        
    # Check if entry has expired by its custom expiry
    now = now_datetime()
    if (now - entry['timestamp']).total_seconds() > entry['expiry']:
        del cache[key]
        return None
        
    return entry['value']