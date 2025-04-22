import frappe
import os
from frappe import _
from frappe.utils import flt, cint

def get_bpjs_settings():
    """Get BPJS settings from .env file or site_config.json"""
    settings = frappe.conf.get('bpjs_settings', {})
    
    # Check for environment variables first
    env_settings = {
        'kesehatan_employee': os.getenv('BPJS_KESEHATAN_PERCENT_KARYAWAN'),
        'kesehatan_employer': os.getenv('BPJS_KESEHATAN_PERCENT_PERUSAHAAN'),
        'jht_employee': os.getenv('BPJS_JHT_PERCENT_KARYAWAN'),
        'jht_employer': os.getenv('BPJS_JHT_PERCENT_PERUSAHAAN'),
        'jp_employee': os.getenv('BPJS_JP_PERCENT_KARYAWAN'),
        'jp_employer': os.getenv('BPJS_JP_PERCENT_PERUSAHAAN'),
        'jkk_employer': os.getenv('BPJS_JKK_PERCENT'),
        'jkm_employer': os.getenv('BPJS_JKM_PERCENT'),
        'max_salary': os.getenv('BPJS_MAX_SALARY'),
    }
    
    # Update settings from environment variables if available
    for key, value in env_settings.items():
        if value:
            try:
                settings[key] = float(value)
            except (ValueError, TypeError):
                pass
    
    # Default values if not configured
    defaults = {
        'kesehatan_employee': 1.0,
        'kesehatan_employer': 4.0,
        'jht_employee': 2.0,
        'jht_employer': 3.7,
        'jp_employee': 1.0,
        'jp_employer': 2.0,
        'jkk_employer': 0.24,
        'jkm_employer': 0.3,
        'max_salary': 12000000,
    }
    
    # Apply defaults for missing values
    for key, value in defaults.items():
        if key not in settings:
            settings[key] = value
            
    return settings

def get_ptkp_settings():
    """Get PTKP settings from .env file or defaults"""
    settings = {}
    
    # Check for environment variables
    env_settings = {
        'pribadi': os.getenv('PTKP_PRIBADI'),
        'kawin': os.getenv('PTKP_KAWIN'),
        'anak': os.getenv('PTKP_ANAK'),
    }
    
    # Update settings from environment variables if available
    for key, value in env_settings.items():
        if value:
            try:
                settings[key] = float(value)
            except (ValueError, TypeError):
                pass
    
    # Default values if not configured
    defaults = {
        'pribadi': 54000000,  # Annual PTKP for individual
        'kawin': 4500000,     # Additional for married status
        'anak': 4500000,      # Additional per dependent
    }
    
    # Apply defaults for missing values
    for key, value in defaults.items():
        if key not in settings:
            settings[key] = value
            
    return settings

def get_spt_month():
    """Get the month for annual SPT calculation from .env file or default"""
    try:
        spt_month = cint(os.getenv('SPT_BULAN', 12))
        # Ensure month is valid (1-12)
        if spt_month < 1 or spt_month > 12:
            return 12
        return spt_month
    except (ValueError, TypeError):
        return 12  # Default to December