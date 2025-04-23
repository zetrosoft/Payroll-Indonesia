# -*- coding: utf-8 -*-
# Copyright (c) 2025, Danny Audian and contributors
# For license information, please see license.txt
# Last modified: 2025-04-23 13:01:41 by dannyaudian

import frappe
import os
from frappe import _
from frappe.utils import flt, cint, getdate

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
    """Get PTKP settings from PPh 21 Settings DocType or .env file or defaults"""
    # First try to get from DocType if it exists
    try:
        if frappe.db.exists("DocType", "PPh 21 Settings") and frappe.db.get_all("PPh 21 Settings"):
            doc = frappe.get_single("PPh 21 Settings")
            result = {}
            
            # Get PTKP values from child table
            for row in doc.ptkp_table:
                result[row.status_pajak] = float(row.ptkp_amount)
                
            if result:
                return result
    except Exception as e:
        frappe.log_error(f"Error getting PTKP settings: {str(e)}")
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

# ---- TER-related functions ----

def get_pph21_settings():
    """Get PPh 21 settings from DocType or defaults"""
    try:
        if frappe.db.exists("DocType", "PPh 21 Settings") and frappe.db.get_all("PPh 21 Settings"):
            doc = frappe.get_single("PPh 21 Settings")
            return {
                'calculation_method': doc.calculation_method,
                'use_ter': cint(doc.use_ter),
                'ptkp_settings': get_ptkp_settings(),
                'brackets': get_pph21_brackets()
            }
    except Exception as e:
        frappe.log_error(f"Error getting PPh 21 settings: {str(e)}")
        
    # Default settings
    return {
        'calculation_method': 'Progressive',
        'use_ter': 0,
        'ptkp_settings': get_ptkp_settings(),
        'brackets': get_pph21_brackets()
    }

def get_pph21_brackets():
    """Get PPh 21 tax brackets from DocType or defaults"""
    brackets = []
    
    try:
        if frappe.db.exists("DocType", "PPh 21 Settings") and frappe.db.get_all("PPh 21 Settings"):
            brackets = frappe.db.sql("""
                SELECT income_from, income_to, tax_rate 
                FROM `tabPPh 21 Tax Bracket`
                WHERE parent = 'PPh 21 Settings'
                ORDER BY income_from ASC
            """, as_dict=1)
    except Exception as e:
        frappe.log_error(f"Error getting PPh 21 brackets: {str(e)}")
    
    # If no brackets found, use defaults
    if not brackets:
        brackets = [
            {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
            {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
            {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
            {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
            {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
        ]
    
    return brackets

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
                        f"No TER rate found for status {status_pajak} or fallbacks with income {penghasilan_bruto}",
                        "PPh 21 TER Error"
                    )
                    return 0
        
        # Convert percent to decimal
        return flt(ter[0].rate) / 100.0
        
    except Exception as e:
        frappe.log_error(f"Error getting TER rate: {str(e)}")
        return 0

def should_use_ter():
    """Check if TER method should be used based on system settings"""
    try:
        pph_settings = frappe.get_single("PPh 21 Settings")
        return (pph_settings.calculation_method == "TER" and pph_settings.use_ter)
    except Exception:
        return False

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
        object: Employee Tax Summary document
    """
    try:
        # Check if a record already exists
        filters = {"employee": employee, "year": year}
        name = frappe.db.get_value("Employee Tax Summary", filters)
        
        if name:
            # Update existing record
            doc = frappe.get_doc("Employee Tax Summary", name)
            doc.ytd_tax = flt(doc.ytd_tax) + flt(tax_amount)
            if is_using_ter:
                doc.is_using_ter = 1
                doc.ter_rate = ter_rate
            doc.save(ignore_permissions=True)
            frappe.db.commit()
        else:
            # Create new record
            employee_name = frappe.db.get_value("Employee", employee, "employee_name")
            doc = frappe.new_doc("Employee Tax Summary")
            doc.employee = employee
            doc.employee_name = employee_name
            doc.year = year
            doc.ytd_tax = flt(tax_amount)
            if is_using_ter:
                doc.is_using_ter = 1
                doc.ter_rate = ter_rate
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
            
        return doc
    except Exception as e:
        frappe.log_error(f"Error creating tax summary for {employee}, year {year}: {str(e)}")
        return None

def get_ytd_tax_info(employee, date=None):
    """
    Get year-to-date tax information for an employee
    
    Args:
        employee (str): Employee ID
        date (datetime, optional): Date to determine year, defaults to current date
        
    Returns:
        dict: YTD tax information
    """
    if not date:
        date = getdate()
    
    year = date.year
    
    # Get from Employee Tax Summary if exists
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
    
    # Alternatively, calculate from submitted salary slips
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
        slip_doc = frappe.get_doc("Salary Slip", slip.name)
        
        # Get PPh 21 component
        for deduction in slip_doc.deductions:
            if deduction.salary_component == "PPh 21":
                ytd_tax += flt(deduction.amount)
                break
        
        # Check if using TER
        if hasattr(slip_doc, 'is_using_ter') and slip_doc.is_using_ter:
            is_using_ter = 1
            if hasattr(slip_doc, 'ter_rate'):
                ter_rate = flt(slip_doc.ter_rate)
    
    return {
        "ytd_tax": ytd_tax,
        "is_using_ter": is_using_ter,
        "ter_rate": ter_rate
    }