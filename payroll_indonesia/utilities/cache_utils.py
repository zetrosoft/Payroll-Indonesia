# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 07:18:15 by dannyaudian

import frappe
from frappe.utils import now_datetime, add_to_date
import hashlib
import json

# Main cache implementation with namespaces
_UNIFIED_CACHE = {}
_LAST_CLEAR_TIMESTAMPS = {}

# Default TTL values for different cache types
DEFAULT_TTL = {
    "ter_rate": 1800,    # 30 minutes
    "ytd": 3600,         # 1 hour
    "ptkp_mapping": 3600,  # 1 hour
    "tax_settings": 3600,  # 1 hour
    "employee": 3600,    # 1 hour
    "fiscal_year": 86400,  # 24 hours
    "salary_slip": 3600,  # 1 hour
    "default": 1800      # 30 minutes (fallback)
}

def get_cached_value(cache_key, ttl=None):
    """
    Get a value from cache with expiry checking
    
    Args:
        cache_key (str): Cache key
        ttl (int, optional): Time-to-live in seconds
        
    Returns:
        any: Cached value or None if not found or expired
    """
    global _UNIFIED_CACHE
    
    # Get cache namespace from key prefix
    namespace = get_namespace_from_key(cache_key)
    
    # Check if namespace needs clearing
    check_and_clear_namespace_if_needed(namespace)
    
    # Normalize key to handle complex objects
    if not isinstance(cache_key, str):
        cache_key = normalize_key(cache_key)
    
    # Return value if present, None otherwise
    entry = _UNIFIED_CACHE.get(cache_key)
    
    if not entry:
        return None
        
    # Check if entry has expired
    now = now_datetime()
    if (now - entry.get('timestamp')).total_seconds() > entry.get('ttl', DEFAULT_TTL["default"]):
        del _UNIFIED_CACHE[cache_key]
        return None
        
    # Log hit if debug mode is on
    if frappe.conf.get("developer_mode"):
        frappe.logger().debug(f"Cache hit for key: {cache_key}")
        
    return entry.get('value')

def cache_value(cache_key, value, ttl=None):
    """
    Store a value in cache with expiry time
    
    Args:
        cache_key (str): Cache key
        value (any): Value to cache
        ttl (int, optional): Time-to-live in seconds
    """
    global _UNIFIED_CACHE
    
    if value is None:
        # Don't cache None values
        return
    
    # Get cache namespace from key prefix
    namespace = get_namespace_from_key(cache_key)
    
    # Get default TTL for this namespace
    if ttl is None:
        ttl = DEFAULT_TTL.get(namespace, DEFAULT_TTL["default"])
    
    # Normalize key to handle complex objects
    if not isinstance(cache_key, str):
        cache_key = normalize_key(cache_key)
    
    # Store with timestamp and ttl
    _UNIFIED_CACHE[cache_key] = {
        'value': value,
        'timestamp': now_datetime(),
        'ttl': ttl,
        'namespace': namespace
    }
    
    # Log if debug mode is on
    if frappe.conf.get("developer_mode"):
        frappe.logger().debug(f"Cached value for key: {cache_key}, namespace: {namespace}, TTL: {ttl}s")

def clear_cache(prefix=None):
    """
    Clear all cache entries with a specific prefix or namespace
    
    Args:
        prefix (str, optional): Key prefix to clear. If None, clear all caches.
    """
    global _UNIFIED_CACHE, _LAST_CLEAR_TIMESTAMPS
    
    if prefix is None:
        # Clear all caches
        _UNIFIED_CACHE = {}
        _LAST_CLEAR_TIMESTAMPS = {}
        frappe.logger().info("All caches cleared")
        return
    
    # Normalize prefix for exact matches
    if not prefix.endswith(':') and ':' in prefix:
        prefix += ':'
    
    # Find namespace from prefix
    namespace = get_namespace_from_key(prefix)
    
    # Clear all entries with matching prefix
    keys_to_delete = [k for k in _UNIFIED_CACHE if k.startswith(prefix)]
    for key in keys_to_delete:
        del _UNIFIED_CACHE[key]
    
    # Update clear timestamp for namespace
    _LAST_CLEAR_TIMESTAMPS[namespace] = now_datetime()
    
    frappe.logger().info(f"Cache cleared for prefix: {prefix}, keys cleared: {len(keys_to_delete)}")

def clear_all_caches():
    """Clear all caches related to payroll calculations"""
    global _UNIFIED_CACHE, _LAST_CLEAR_TIMESTAMPS
    
    # Clear our unified cache
    _UNIFIED_CACHE = {}
    _LAST_CLEAR_TIMESTAMPS = {}
    
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

def get_namespace_from_key(key):
    """
    Extract namespace from a cache key
    
    Args:
        key (str): Cache key
        
    Returns:
        str: Namespace (first part before colon or "default")
    """
    if not isinstance(key, str):
        return "default"
        
    if ':' in key:
        return key.split(':', 1)[0]
    
    return "default"

def check_and_clear_namespace_if_needed(namespace):
    """
    Check if a namespace needs clearing based on TTL
    
    Args:
        namespace (str): Cache namespace
    """
    global _LAST_CLEAR_TIMESTAMPS
    
    now = now_datetime()
    last_clear = _LAST_CLEAR_TIMESTAMPS.get(namespace)
    
    if last_clear is None:
        # First time - set timestamp
        _LAST_CLEAR_TIMESTAMPS[namespace] = now
        return
    
    namespace_ttl = DEFAULT_TTL.get(namespace, DEFAULT_TTL["default"])
    
    if (now - last_clear).total_seconds() > namespace_ttl:
        # Clear all entries for this namespace
        keys_to_delete = [
            k for k, v in _UNIFIED_CACHE.items() 
            if v.get('namespace') == namespace
        ]
        
        for key in keys_to_delete:
            del _UNIFIED_CACHE[key]
            
        # Update timestamp
        _LAST_CLEAR_TIMESTAMPS[namespace] = now
        frappe.logger().debug(f"Auto-cleared cache namespace: {namespace}, keys: {len(keys_to_delete)}")

def normalize_key(obj):
    """
    Normalize complex objects into stable string keys
    
    Args:
        obj: Any object to use as a cache key
        
    Returns:
        str: Normalized string key
    """
    if isinstance(obj, str):
        return obj
    
    try:
        # Try to convert to JSON and hash
        json_str = json.dumps(obj, sort_keys=True)
        return hashlib.md5(json_str.encode()).hexdigest()
    except (TypeError, ValueError):
        # Fallback to string representation
        return hashlib.md5(str(obj).encode()).hexdigest()

# Backward compatibility functions for older code
def get_ter_rate_cache():
    """
    Legacy function for backwards compatibility
    
    Returns:
        dict: Empty dict, as cache storage is now handled internally
    """
    frappe.logger().warning("Deprecated: get_ter_rate_cache() called - use get_cached_value() instead")
    return {}

def get_ytd_cache():
    """Legacy function for backwards compatibility"""
    frappe.logger().warning("Deprecated: get_ytd_cache() called - use get_cached_value() instead")
    return {}

def get_ptkp_mapping_cache():
    """Legacy function for backwards compatibility"""
    frappe.logger().warning("Deprecated: get_ptkp_mapping_cache() called - use get_cached_value() instead")
    return {}

def get_tax_settings_cache():
    """Legacy function for backwards compatibility"""
    frappe.logger().warning("Deprecated: get_tax_settings_cache() called - use get_cached_value() instead")
    return {}

def clear_ter_cache():
    """Legacy function for backwards compatibility"""
    frappe.logger().warning("Deprecated: clear_ter_cache() called - use clear_cache('ter_rate:') instead")
    clear_cache('ter_rate:')

def clear_ytd_cache():
    """Legacy function for backwards compatibility"""
    frappe.logger().warning("Deprecated: clear_ytd_cache() called - use clear_cache('ytd:') instead")
    clear_cache('ytd:')

def clear_ptkp_mapping_cache():
    """Legacy function for backwards compatibility"""
    frappe.logger().warning("Deprecated: clear_ptkp_mapping_cache() called - use clear_cache('ptkp_mapping:') instead")
    clear_cache('ptkp_mapping:')

def clear_tax_settings_cache():
    """Legacy function for backwards compatibility"""
    frappe.logger().warning("Deprecated: clear_tax_settings_cache() called - use clear_cache('tax_settings:') instead")
    clear_cache('tax_settings:')

# Legacy cache getter/setter functions for backward compatibility
def cache_ter_rate(ter_category, income_bracket, rate_value):
    """Legacy function for backwards compatibility"""
    cache_key = f"ter_rate:{ter_category}:{income_bracket}"
    cache_value(cache_key, rate_value)

def get_cached_ter_rate(ter_category, income_bracket):
    """Legacy function for backwards compatibility"""
    cache_key = f"ter_rate:{ter_category}:{income_bracket}"
    return get_cached_value(cache_key)

def cache_ytd_data(employee, year, month, data):
    """Legacy function for backwards compatibility"""
    cache_key = f"ytd:{employee}:{year}:{month}"
    cache_value(cache_key, data)

def get_cached_ytd_data(employee, year, month):
    """Legacy function for backwards compatibility"""
    cache_key = f"ytd:{employee}:{year}:{month}"
    return get_cached_value(cache_key)

def cache_ptkp_mapping(mapping):
    """Legacy function for backwards compatibility"""
    cache_value("ptkp_mapping:global", mapping)

def get_cached_ptkp_mapping():
    """Legacy function for backwards compatibility"""
    return get_cached_value("ptkp_mapping:global")

def cache_tax_settings(key, value, expiry_seconds=None):
    """Legacy function for backwards compatibility"""
    cache_key = f"tax_settings:{key}"
    cache_value(cache_key, value, expiry_seconds)

def get_cached_tax_settings(key):
    """Legacy function for backwards compatibility"""
    cache_key = f"tax_settings:{key}"
    return get_cached_value(cache_key)