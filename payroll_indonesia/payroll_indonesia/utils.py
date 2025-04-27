# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 03:15:12 by dannyaudian

import frappe
import os
from frappe import _
from frappe.utils import flt, cint, getdate

def get_bpjs_settings():
    """
    Get BPJS settings from DocType or .env file or site_config.json
    with improved error handling and validation
    
    Returns:
        dict: Dictionary containing BPJS settings
    """
    try:
        # First try to get from DocType if it exists
        if frappe.db.exists("DocType", "BPJS Settings"):
            try:
                doc_list = frappe.db.get_all("BPJS Settings")
                if doc_list:
                    doc = frappe.get_single("BPJS Settings")
                    
                    # Validate required fields exist
                    required_fields = [
                        'kesehatan_employee_percent', 'kesehatan_employer_percent', 'kesehatan_max_salary',
                        'jht_employee_percent', 'jht_employer_percent', 
                        'jp_employee_percent', 'jp_employer_percent', 'jp_max_salary',
                        'jkk_percent', 'jkm_percent'
                    ]
                    
                    missing_fields = []
                    for field in required_fields:
                        if not hasattr(doc, field):
                            missing_fields.append(field)
                            
                    if missing_fields:
                        frappe.log_error(
                            f"BPJS Settings missing required fields: {', '.join(missing_fields)}",
                            "BPJS Settings Error"
                        )
                    else:
                        # All fields exist, return structured settings
                        return {
                            "kesehatan": {
                                "employee_percent": flt(doc.kesehatan_employee_percent),
                                "employer_percent": flt(doc.kesehatan_employer_percent),
                                "max_salary": flt(doc.kesehatan_max_salary)
                            },
                            "jht": {
                                "employee_percent": flt(doc.jht_employee_percent),
                                "employer_percent": flt(doc.jht_employer_percent)
                            },
                            "jp": {
                                "employee_percent": flt(doc.jp_employee_percent),
                                "employer_percent": flt(doc.jp_employer_percent),
                                "max_salary": flt(doc.jp_max_salary)
                            },
                            "jkk": {
                                "percent": flt(doc.jkk_percent)
                            },
                            "jkm": {
                                "percent": flt(doc.jkm_percent)
                            }
                        }
            except Exception as e:
                frappe.log_error(f"Error retrieving BPJS Settings from DocType: {str(e)}", "BPJS Settings Error")
                # Fall back to config methods
                pass
        
        # Get settings from frappe.conf or initialize empty dict
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
                    frappe.log_error(f"Invalid value for BPJS setting {key}: {value}", "BPJS Settings Error")
        
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
        
        # Convert to structured format
        return {
            "kesehatan": {
                "employee_percent": settings.get('kesehatan_employee'),
                "employer_percent": settings.get('kesehatan_employer'),
                "max_salary": settings.get('max_salary_kesehatan')
            },
            "jht": {
                "employee_percent": settings.get('jht_employee'),
                "employer_percent": settings.get('jht_employer')
            },
            "jp": {
                "employee_percent": settings.get('jp_employee'),
                "employer_percent": settings.get('jp_employer'),
                "max_salary": settings.get('max_salary_jp')
            },
            "jkk": {
                "percent": settings.get('jkk_employer')
            },
            "jkm": {
                "percent": settings.get('jkm_employer')
            }
        }
    except Exception as e:
        frappe.log_error(f"Error retrieving BPJS settings: {str(e)}", "BPJS Settings Error")
        
        # Return default values as fallback
        return {
            "kesehatan": {
                "employee_percent": 1.0,
                "employer_percent": 4.0,
                "max_salary": 12000000
            },
            "jht": {
                "employee_percent": 2.0,
                "employer_percent": 3.7
            },
            "jp": {
                "employee_percent": 1.0,
                "employer_percent": 2.0,
                "max_salary": 9077600
            },
            "jkk": {
                "percent": 0.24
            },
            "jkm": {
                "percent": 0.3
            }
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
            frappe.msgprint(_("Negative salary amount provided for BPJS calculation, using absolute value"))
            salary = abs(salary)
        
        # Get BPJS settings if not provided
        if not bpjs_settings:
            bpjs_settings = get_bpjs_settings()
        
        # Initialize default values
        kesehatan_employee_percent = 1.0
        kesehatan_employer_percent = 4.0
        kesehatan_max_salary = 12000000
        
        jht_employee_percent = 2.0
        jht_employer_percent = 3.7
        
        jp_employee_percent = 1.0
        jp_employer_percent = 2.0
        jp_max_salary = 9077600
        
        jkk_percent = 0.24
        jkm_percent = 0.3
        
        # Check if bpjs_settings is a dict or an object and get values
        if isinstance(bpjs_settings, dict):
            # Use dict values with validation
            kesehatan_employee_percent = flt(bpjs_settings.get("kesehatan", {}).get("employee_percent", 1))
            kesehatan_employer_percent = flt(bpjs_settings.get("kesehatan", {}).get("employer_percent", 4))
            kesehatan_max_salary = flt(bpjs_settings.get("kesehatan", {}).get("max_salary", 12000000))
            
            jht_employee_percent = flt(bpjs_settings.get("jht", {}).get("employee_percent", 2))
            jht_employer_percent = flt(bpjs_settings.get("jht", {}).get("employer_percent", 3.7))
            
            jp_employee_percent = flt(bpjs_settings.get("jp", {}).get("employee_percent", 1))
            jp_employer_percent = flt(bpjs_settings.get("jp", {}).get("employer_percent", 2))
            jp_max_salary = flt(bpjs_settings.get("jp", {}).get("max_salary", 9077600))
            
            jkk_percent = flt(bpjs_settings.get("jkk", {}).get("percent", 0.24))
            jkm_percent = flt(bpjs_settings.get("jkm", {}).get("percent", 0.3))
        else:
            # Use object attributes with validation
            if hasattr(bpjs_settings, 'kesehatan_employee_percent'):
                kesehatan_employee_percent = flt(bpjs_settings.kesehatan_employee_percent)
            
            if hasattr(bpjs_settings, 'kesehatan_employer_percent'):
                kesehatan_employer_percent = flt(bpjs_settings.kesehatan_employer_percent)
                
            if hasattr(bpjs_settings, 'kesehatan_max_salary'):
                kesehatan_max_salary = flt(bpjs_settings.kesehatan_max_salary)
                
            if hasattr(bpjs_settings, 'jht_employee_percent'):
                jht_employee_percent = flt(bpjs_settings.jht_employee_percent)
                
            if hasattr(bpjs_settings, 'jht_employer_percent'):
                jht_employer_percent = flt(bpjs_settings.jht_employer_percent)
                
            if hasattr(bpjs_settings, 'jp_employee_percent'):
                jp_employee_percent = flt(bpjs_settings.jp_employee_percent)
                
            if hasattr(bpjs_settings, 'jp_employer_percent'):
                jp_employer_percent = flt(bpjs_settings.jp_employer_percent)
                
            if hasattr(bpjs_settings, 'jp_max_salary'):
                jp_max_salary = flt(bpjs_settings.jp_max_salary)
                
            if hasattr(bpjs_settings, 'jkk_percent'):
                jkk_percent = flt(bpjs_settings.jkk_percent)
                
            if hasattr(bpjs_settings, 'jkm_percent'):
                jkm_percent = flt(bpjs_settings.jkm_percent)
        
        # Validate percentages
        if kesehatan_employee_percent < 0 or kesehatan_employee_percent > 100:
            frappe.msgprint(_("Invalid BPJS Kesehatan employee percentage. Using default 1%"))
            kesehatan_employee_percent = 1.0
            
        if kesehatan_max_salary <= 0:
            frappe.msgprint(_("Invalid BPJS Kesehatan maximum salary. Using default 12,000,000"))
            kesehatan_max_salary = 12000000
            
        if jp_max_salary <= 0:
            frappe.msgprint(_("Invalid BPJS JP maximum salary. Using default 9,077,600"))
            jp_max_salary = 9077600
        
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
                "total": kesehatan_karyawan + kesehatan_perusahaan
            },
            "ketenagakerjaan": {
                "jht": {
                    "karyawan": jht_karyawan,
                    "perusahaan": jht_perusahaan,
                    "total": jht_karyawan + jht_perusahaan
                },
                "jp": {
                    "karyawan": jp_karyawan,
                    "perusahaan": jp_perusahaan,
                    "total": jp_karyawan + jp_perusahaan
                },
                "jkk": jkk,
                "jkm": jkm
            }
        }
    except Exception as e:
        frappe.log_error(f"Error calculating BPJS contributions: {str(e)}", "BPJS Calculation Error")
        # Return empty structure to avoid breaking code that relies on the structure
        return {
            "kesehatan": {"karyawan": 0, "perusahaan": 0, "total": 0},
            "ketenagakerjaan": {
                "jht": {"karyawan": 0, "perusahaan": 0, "total": 0},
                "jp": {"karyawan": 0, "perusahaan": 0, "total": 0},
                "jkk": 0, "jkm": 0
            }
        }

def get_ptkp_settings():
    """
    Get PTKP settings from PPh 21 Settings DocType or .env file or defaults
    with improved error handling
    
    Returns:
        dict: Dictionary containing PTKP settings
    """
    try:
        # First try to get from DocType if it exists
        if frappe.db.exists("DocType", "PPh 21 Settings"):
            try:
                doc_list = frappe.db.get_all("PPh 21 Settings")
                if doc_list:
                    doc = frappe.get_single("PPh 21 Settings")
                    result = {}
                    
                    # Check if ptkp_table exists and has rows
                    if hasattr(doc, 'ptkp_table') and doc.ptkp_table:
                        # Get PTKP values from child table
                        for row in doc.ptkp_table:
                            if hasattr(row, 'status_pajak') and hasattr(row, 'ptkp_amount'):
                                result[row.status_pajak] = float(row.ptkp_amount)
                        
                        if result:
                            return result
            except Exception as e:
                frappe.log_error(f"Error getting PTKP settings from DocType: {str(e)}", "PTKP Settings Error")
                # Fall back to config methods
                pass
        
        # Initialize settings dict
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
                    frappe.log_error(f"Invalid value for PTKP setting {key}: {value}", "PTKP Settings Error")
        
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
            # Add all missing status variations for TER
            settings['TK1'] = settings['pribadi'] + settings['anak']
            settings['TK2'] = settings['pribadi'] + (2 * settings['anak'])
            settings['TK3'] = settings['pribadi'] + (3 * settings['anak'])
            # Add HB (Penghasilan Istri-Suami Digabung) statuses
            settings['HB0'] = 2 * settings['pribadi'] + settings['kawin']
            settings['HB1'] = 2 * settings['pribadi'] + settings['kawin'] + settings['anak']
            settings['HB2'] = 2 * settings['pribadi'] + settings['kawin'] + (2 * settings['anak'])
            settings['HB3'] = 2 * settings['pribadi'] + settings['kawin'] + (3 * settings['anak'])
                
        return settings
    except Exception as e:
        frappe.log_error(f"Error retrieving PTKP settings: {str(e)}", "PTKP Settings Error")
        
        # Return default PTKP values as fallback
        return {
            'TK0': 54000000, 'TK1': 58500000, 'TK2': 63000000, 'TK3': 67500000,
            'K0': 58500000, 'K1': 63000000, 'K2': 67500000, 'K3': 72000000,
            'HB0': 112500000, 'HB1': 117000000, 'HB2': 121500000, 'HB3': 126000000,
        }

def get_spt_month():
    """
    Get the month for annual SPT calculation from .env file or default
    with improved validation
    
    Returns:
        int: Month number (1-12)
    """
    try:
        # Get from environment variable
        spt_month_str = os.getenv('SPT_BULAN')
        
        if spt_month_str:
            try:
                spt_month = int(spt_month_str)
                # Validate month is in correct range
                if spt_month < 1 or spt_month > 12:
                    frappe.log_error(
                        f"Invalid SPT_BULAN value: {spt_month}. Must be between 1-12. Using default (12)",
                        "SPT Month Error"
                    )
                    return 12
                return spt_month
            except ValueError:
                frappe.log_error(
                    f"Invalid SPT_BULAN format: {spt_month_str}. Must be an integer. Using default (12)",
                    "SPT Month Error"
                )
                return 12
        else:
            return 12  # Default to December
    except Exception as e:
        frappe.log_error(f"Error getting SPT month: {str(e)}", "SPT Month Error")
        return 12  # Default to December

# ---- TER-related functions ----

def get_pph21_settings():
    """
    Get PPh 21 settings from DocType or defaults
    
    Returns:
        dict: PPh 21 settings including calculation method and TER usage
    """
    try:
        if frappe.db.exists("DocType", "PPh 21 Settings"):
            doc_list = frappe.db.get_all("PPh 21 Settings")
            if doc_list:
                try:
                    doc = frappe.get_single("PPh 21 Settings")
                    
                    # Validate required fields
                    method = "Progressive"
                    use_ter = 0
                    
                    if hasattr(doc, 'calculation_method'):
                        method = doc.calculation_method
                        
                    if hasattr(doc, 'use_ter'):
                        use_ter = cint(doc.use_ter)
                        
                    return {
                        'calculation_method': method,
                        'use_ter': use_ter,
                        'ptkp_settings': get_ptkp_settings(),
                        'brackets': get_pph21_brackets()
                    }
                except Exception as e:
                    frappe.log_error(f"Error retrieving PPh 21 settings: {str(e)}", "PPh 21 Settings Error")
    except Exception as e:
        frappe.log_error(f"Error checking for PPh 21 Settings DocType: {str(e)}", "PPh 21 Settings Error")
        
    # Default settings
    return {
        'calculation_method': 'Progressive',
        'use_ter': 0,
        'ptkp_settings': get_ptkp_settings(),
        'brackets': get_pph21_brackets()
    }

def get_pph21_brackets():
    """
    Get PPh 21 tax brackets from DocType or defaults
    with improved error handling
    
    Returns:
        list: List of tax brackets with income ranges and rates
    """
    brackets = []
    
    try:
        if frappe.db.exists("DocType", "PPh 21 Settings"):
            try:
                # Check if there are settings records
                doc_list = frappe.db.get_all("PPh 21 Settings")
                if doc_list:
                    # Query tax brackets from child table
                    brackets = frappe.db.sql("""
                        SELECT income_from, income_to, tax_rate 
                        FROM `tabPPh 21 Tax Bracket`
                        WHERE parent = 'PPh 21 Settings'
                        ORDER BY income_from ASC
                    """, as_dict=1)
            except Exception as e:
                frappe.log_error(f"Error retrieving PPh 21 brackets from DB: {str(e)}", "PPh 21 Brackets Error")
    except Exception as e:
        frappe.log_error(f"Error checking for PPh 21 Settings DocType: {str(e)}", "PPh 21 Brackets Error")
    
    # If no brackets found, use defaults
    if not brackets:
        brackets = [
            {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
            {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
            {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
            {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
            {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
        ]
    
    # Validate brackets
    for i, bracket in enumerate(brackets):
        # Ensure all required fields exist
        if not all(k in bracket for k in ['income_from', 'income_to', 'tax_rate']):
            frappe.log_error(f"Invalid bracket format at index {i}: {bracket}", "PPh 21 Brackets Error")
            continue
        
        # Ensure values are numeric
        try:
            bracket['income_from'] = flt(bracket['income_from'])
            bracket['income_to'] = flt(bracket['income_to'])
            bracket['tax_rate'] = flt(bracket['tax_rate'])
        except Exception:
            frappe.log_error(f"Non-numeric values in bracket at index {i}: {bracket}", "PPh 21 Brackets Error")
    
    # Sort brackets by income_from to ensure proper order
    brackets.sort(key=lambda x: flt(x['income_from']))
    
    return brackets

def get_ter_rate(status_pajak, penghasilan_bruto):
    """
    Get TER rate for a specific tax status and income level
    with improved validation and error handling
    
    Args:
        status_pajak (str): Tax status (TK0, K0, etc)
        penghasilan_bruto (float): Gross income
        
    Returns:
        float: TER rate as decimal (e.g., 0.05 for 5%)
    """
    try:
        # Validate inputs
        if not status_pajak:
            status_pajak = "TK0"  # Default to TK0
            frappe.msgprint(_("Tax status not provided, using default (TK0)"))
            
        if not penghasilan_bruto:
            penghasilan_bruto = 0
            
        penghasilan_bruto = flt(penghasilan_bruto)
        if penghasilan_bruto < 0:
            frappe.msgprint(_("Negative income provided for TER calculation, using absolute value"))
            penghasilan_bruto = abs(penghasilan_bruto)
            
        # Check if PPh 21 TER Table DocType exists
        if not frappe.db.exists("DocType", "PPh 21 TER Table"):
            frappe.log_error("PPh 21 TER Table DocType not found", "TER Rate Error")
            return 0
        
        # Query TER table
        ter = frappe.db.sql("""
            SELECT rate
            FROM `tabPPh 21 TER Table`
            WHERE status_pajak = %s
              AND %s >= income_from
              AND (%s <= income_to OR income_to = 0)
            LIMIT 1
        """, (status_pajak, penghasilan_bruto, penghasilan_bruto), as_dict=1)
        
        if not ter:
            # Try with fallback to status type + 0 (e.g. TK2 -> TK0, K3 -> K0)
            status_prefix = status_pajak[0:2] if len(status_pajak) > 2 else status_pajak[0:1]
            fallback_status = f"{status_prefix}0"
            
            ter = frappe.db.sql("""
                SELECT rate
                FROM `tabPPh 21 TER Table`
                WHERE status_pajak = %s
                  AND %s >= income_from
                  AND (%s <= income_to OR income_to = 0)
                LIMIT 1
            """, (fallback_status, penghasilan_bruto, penghasilan_bruto), as_dict=1)
            
            if not ter:
                # Ultimate fallback to TK0 (default lowest)
                ter = frappe.db.sql("""
                    SELECT rate
                    FROM `tabPPh 21 TER Table`
                    WHERE status_pajak = 'TK0'
                      AND %s >= income_from
                      AND (%s <= income_to OR income_to = 0)
                    LIMIT 1
                """, (penghasilan_bruto, penghasilan_bruto), as_dict=1)
                
                if not ter:
                    frappe.log_error(
                        f"No TER rate found for status {status_pajak} or fallbacks with income {penghasilan_bruto:,.0f}",
                        "PPh 21 TER Error"
                    )
                    return 0
        
        # Convert percent to decimal
        rate = flt(ter[0].rate) / 100.0
        
        # Validate rate is reasonable
        if rate < 0 or rate > 0.5:  # Maximum 50% as sanity check
            frappe.log_error(
                f"Unreasonable TER rate ({rate * 100:.2f}%) found for status {status_pajak} with income {penghasilan_bruto:,.0f}",
                "PPh 21 TER Error"
            )
            # Cap at reasonable value
            rate = min(0.35, max(0, rate))
            
        return rate
        
    except Exception as e:
        frappe.log_error(
            f"Error getting TER rate for status {status_pajak} and income {penghasilan_bruto}: {str(e)}",
            "TER Rate Error"
        )
        return 0

def should_use_ter():
    """
    Check if TER method should be used based on system settings
    with error handling
    
    Returns:
        bool: True if TER should be used, False otherwise
    """
    try:
        # Check if the DocType exists
        if not frappe.db.exists("DocType", "PPh 21 Settings"):
            return False
            
        # Check if there are settings records
        doc_list = frappe.db.get_all("PPh 21 Settings")
        if not doc_list:
            return False
            
        # Get settings
        pph_settings = frappe.get_single("PPh 21 Settings")
        
        # Check required fields
        if not hasattr(pph_settings, 'calculation_method') or not hasattr(pph_settings, 'use_ter'):
            return False
            
        return (pph_settings.calculation_method == "TER" and cint(pph_settings.use_ter) == 1)
    except Exception as e:
        frappe.log_error(f"Error checking TER method settings: {str(e)}", "TER Settings Error")
        return False

def create_tax_summary_doc(employee, year, tax_amount=0, is_using_ter=0, ter_rate=0):
    """
    Create or update Employee Tax Summary document
    with improved validation and error handling
    
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
            
        # Convert numeric parameters to appropriate types
        tax_amount = flt(tax_amount)
        is_using_ter = cint(is_using_ter)
        ter_rate = flt(ter_rate)
        
        # Check if Employee Tax Summary DocType exists
        if not frappe.db.exists("DocType", "Employee Tax Summary"):
            frappe.log_error("Employee Tax Summary DocType does not exist", "Tax Summary Creation Error")
            return None
            
        # Check if employee exists
        if not frappe.db.exists("Employee", employee):
            frappe.log_error(f"Employee {employee} does not exist", "Tax Summary Creation Error")
            return None
        
        # Check if a record already exists
        filters = {"employee": employee, "year": year}
        name = frappe.db.get_value("Employee Tax Summary", filters)
        
        if name:
            try:
                # Update existing record
                doc = frappe.get_doc("Employee Tax Summary", name)
                
                # Validate ytd_tax field exists
                if not hasattr(doc, 'ytd_tax'):
                    frappe.log_error(
                        f"Employee Tax Summary {name} missing required field: ytd_tax",
                        "Tax Summary Update Error"
                    )
                    return None
                    
                doc.ytd_tax = flt(doc.ytd_tax) + flt(tax_amount)
                
                # Set TER information if applicable and fields exist
                if is_using_ter:
                    if hasattr(doc, 'is_using_ter'):
                        doc.is_using_ter = 1
                    if hasattr(doc, 'ter_rate'):
                        doc.ter_rate = ter_rate
                
                # Save the document
                doc.flags.ignore_validate_update_after_submit = True
                doc.save(ignore_permissions=True)
                frappe.db.commit()
                return doc
            except Exception as e:
                frappe.log_error(
                    f"Error updating tax summary {name} for {employee}, year {year}: {str(e)}",
                    "Tax Summary Update Error"
                )
                return None
        else:
            try:
                # Get employee name
                employee_name = frappe.db.get_value("Employee", employee, "employee_name")
                if not employee_name:
                    employee_name = employee
                
                # Create new record
                doc = frappe.new_doc("Employee Tax Summary")
                
                # Set required fields
                doc.employee = employee
                doc.employee_name = employee_name
                doc.year = year
                doc.ytd_tax = flt(tax_amount)
                
                # Set title if field exists
                if hasattr(doc, 'title'):
                    doc.title = f"{employee_name} - {year}"
                
                # Set TER information if applicable and fields exist
                if is_using_ter:
                    if hasattr(doc, 'is_using_ter'):
                        doc.is_using_ter = 1
                    if hasattr(doc, 'ter_rate'):
                        doc.ter_rate = ter_rate
                
                # Insert the document
                doc.insert(ignore_permissions=True)
                frappe.db.commit()
                return doc
            except Exception as e:
                frappe.log_error(
                    f"Error creating tax summary for {employee}, year {year}: {str(e)}",
                    "Tax Summary Creation Error"
                )
                return None
    except Exception as e:
        frappe.log_error(
            f"Error in create_tax_summary_doc for {employee}, year {year}: {str(e)}",
            "Tax Summary Error"
        )
        return None

def get_ytd_tax_info(employee, date=None):
    """
    Get year-to-date tax information for an employee
    with improved validation and error handling
    
    Args:
        employee (str): Employee ID
        date (datetime, optional): Date to determine year, defaults to current date
        
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
        
        # Determine tax year from date
        if not date:
            date = getdate()
        
        year = date.year
        
        # First try to get from Employee Tax Summary if exists
        if frappe.db.exists("DocType", "Employee Tax Summary"):
            try:
                tax_summary = frappe.db.get_value(
                    "Employee Tax Summary",
                    {"employee": employee, "year": year},
                    ["ytd_tax", "is_using_ter", "ter_rate"],
                    as_dict=1
                )
                
                if tax_summary:
                    return {
                        "ytd_tax": flt(tax_summary.ytd_tax),
                        "is_using_ter": cint(tax_summary.is_using_ter),
                        "ter_rate": flt(tax_summary.ter_rate)
                    }
            except Exception as e:
                frappe.log_error(
                    f"Error retrieving tax summary for {employee}, year {year}: {str(e)}",
                    "YTD Tax Info Error"
                )
                # Continue to alternate method
        
        # Alternatively, calculate from submitted salary slips
        try:
            salary_slips = frappe.get_all(
                "Salary Slip",
                filters={
                    "employee": employee,
                    "start_date": [">=", f"{year}-01-01"],
                    "end_date": ["<", date],
                    "docstatus": 1
                },
                fields=["name"]
            )
            
            ytd_tax = 0
            is_using_ter = 0
            ter_rate = 0
            
            for slip in salary_slips:
                try:
                    slip_doc = frappe.get_doc("Salary Slip", slip.name)
                    
                    # Get PPh 21 component
                    if hasattr(slip_doc, 'deductions'):
                        for deduction in slip_doc.deductions:
                            if deduction.salary_component == "PPh 21":
                                ytd_tax += flt(deduction.amount)
                                break
                    
                    # Check if using TER
                    if hasattr(slip_doc, 'is_using_ter') and slip_doc.is_using_ter:
                        is_using_ter = 1
                        if hasattr(slip_doc, 'ter_rate') and slip_doc.ter_rate > ter_rate:
                            ter_rate = flt(slip_doc.ter_rate)
                except Exception as e:
                    frappe.log_error(
                        f"Error processing salary slip {slip.name}: {str(e)}",
                        "YTD Tax Calculation Error"
                    )
                    continue
            
            # Return the calculated values
            return {
                "ytd_tax": ytd_tax,
                "is_using_ter": is_using_ter,
                "ter_rate": ter_rate
            }
        except Exception as e:
            frappe.log_error(
                f"Error calculating YTD tax from salary slips for {employee}, year {year}: {str(e)}",
                "YTD Tax Calculation Error"
            )
            # Return default values on error
            return {
                "ytd_tax": 0,
                "is_using_ter": 0,
                "ter_rate": 0
            }
    except Exception as e:
        frappe.log_error(
            f"Error in get_ytd_tax_info for {employee}: {str(e)}",
            "YTD Tax Info Error"
        )
        # Return default values on error
        return {
            "ytd_tax": 0,
            "is_using_ter": 0,
            "ter_rate": 0
        }