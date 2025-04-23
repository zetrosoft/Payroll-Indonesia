# -*- coding: utf-8 -*-
# Copyright (c) 2025, Danny Audian and contributors
# For license information, please see license.txt

import frappe
import os
from frappe import _
from frappe.utils import flt, cint

def get_bpjs_settings():
    """Get BPJS settings from DocType or .env file or site_config.json"""
    # First try to get from DocType if it exists
    try:
        if frappe.db.exists("DocType", "BPJS Settings") and frappe.db.get_all("BPJS Settings"):
            doc = frappe.get_single("BPJS Settings")
            return {
                'kesehatan_employee': doc.kesehatan_employee_percent,
                'kesehatan_employer': doc.kesehatan_employer_percent,
                'jht_employee': doc.jht_employee_percent,
                'jht_employer': doc.jht_employer_percent,
                'jp_employee': doc.jp_employee_percent,
                'jp_employer': doc.jp_employer_percent,
                'jkk_employer': doc.jkk_percent,
                'jkm_employer': doc.jkm_percent,
                'max_salary_kesehatan': doc.kesehatan_max_salary,
                'max_salary_jp': doc.jp_max_salary
            }
    except Exception:
        # Fall back to config methods if DocType approach fails
        pass
        
    settings = frappe.conf.get('bpjs_settings', {})
    
    # Check for environment variables
    env_settings = {
        'kesehatan_employee': os.getenv('BPJS_KESEHATAN_PERCENT_KARYAWAN'),
        'kesehatan_employer': os.getenv('BPJS_KESEHATAN_PERCENT_PERUSAHAAN'),
        'jht_employee': os.getenv('BPJS_JHT_PERCENT_KARYAWAN'),
        'jht_employer': os.getenv('BPJS_JHT_PERCENT_PERUSAHAAN'),
        'jp_employee': os.getenv('BPJS_JP_PERCENT_KARYAWAN'),
        'jp_employer': os.getenv('BPJS_JP_PERCENT_PERUSAHAAN'),
        'jkk_employer': os.getenv('BPJS_JKK_PERCENT'),
        'jkm_employer': os.getenv('BPJS_JKM_PERCENT'),
        'max_salary_kesehatan': os.getenv('BPJS_KES_MAX_SALARY'),
        'max_salary_jp': os.getenv('BPJS_JP_MAX_SALARY'),
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
        'max_salary_kesehatan': 12000000,
        'max_salary_jp': 9077600,
    }
    
    # Apply defaults for missing values
    for key, value in defaults.items():
        if key not in settings:
            settings[key] = value
            
    return settings

def get_ptkp_settings():
    """Get PTKP settings from DocType or .env file or defaults"""
    # First try to get from DocType if it exists
    try:
        if frappe.db.exists("DocType", "PPh 21 Settings") and frappe.db.get_all("PPh 21 Settings"):
            doc = frappe.get_single("PPh 21 Settings")
            result = {}
            
            # Get PTKP values from child table
            for row in doc.ptkp_table:
                result[row.status_pajak] = row.ptkp_amount
                
            if result:
                return result
    except Exception:
        # Fall back to config methods if DocType approach fails
        pass
    
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
            
    # Calculate standard PTKP values if not from DocType
    if 'TK0' not in settings:
        settings['TK0'] = settings['pribadi']
        settings['K0'] = settings['pribadi'] + settings['kawin']
        settings['K1'] = settings['pribadi'] + settings['kawin'] + settings['anak']
        settings['K2'] = settings['pribadi'] + settings['kawin'] + (2 * settings['anak'])
        settings['K3'] = settings['pribadi'] + settings['kawin'] + (3 * settings['anak'])
            
    return settings

def calculate_bpjs_contributions(gaji_pokok):
    """Calculate BPJS contributions based on salary
    
    Args:
        gaji_pokok (float): Base salary amount
        
    Returns:
        dict: Dictionary containing BPJS contribution values
    """
    # Get BPJS settings
    settings = get_bpjs_settings()
    
    # Get percentages (convert to decimal)
    jht_karyawan = settings.get('jht_employee', 2.0) / 100
    jht_perusahaan = settings.get('jht_employer', 3.7) / 100
    jp_karyawan = settings.get('jp_employee', 1.0) / 100
    jp_perusahaan = settings.get('jp_employer', 2.0) / 100
    jkk_perusahaan = settings.get('jkk_employer', 0.24) / 100
    jkm_perusahaan = settings.get('jkm_employer', 0.3) / 100
    kesehatan_karyawan = settings.get('kesehatan_employee', 1.0) / 100
    kesehatan_perusahaan = settings.get('kesehatan_employer', 4.0) / 100
    
    # Get salary caps
    jp_max_salary = settings.get('max_salary_jp', 9077600)
    kesehatan_max_salary = settings.get('max_salary_kesehatan', 12000000)
    
    # Apply salary caps
    jp_base = min(gaji_pokok, jp_max_salary)
    kesehatan_base = min(gaji_pokok, kesehatan_max_salary)
    
    # Calculate contributions
    result = {
        "ketenagakerjaan": {
            "jht": {
                "karyawan": flt(gaji_pokok * jht_karyawan),
                "perusahaan": flt(gaji_pokok * jht_perusahaan)
            },
            "jp": {
                "karyawan": flt(jp_base * jp_karyawan),
                "perusahaan": flt(jp_base * jp_perusahaan)
            },
            "jkk": {
                "perusahaan": flt(gaji_pokok * jkk_perusahaan)
            },
            "jkm": {
                "perusahaan": flt(gaji_pokok * jkm_perusahaan)
            }
        },
        "kesehatan": {
            "karyawan": flt(kesehatan_base * kesehatan_karyawan),
            "perusahaan": flt(kesehatan_base * kesehatan_perusahaan)
        }
    }
    
    return result

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