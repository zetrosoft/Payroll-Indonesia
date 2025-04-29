# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-29 19:55:00 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate, cint, now_datetime
import hashlib

from .base import update_component_amount

# Cache for TER rates to avoid repeated queries - cleared every 30 minutes
_ter_rate_cache = {}
_ter_rate_last_clear = now_datetime()

def calculate_monthly_pph_with_ter(doc, employee):
    """Calculate PPh 21 using TER method"""
    try:
        # Validate employee status_pajak
        if not hasattr(employee, 'status_pajak') or not employee.status_pajak:
            employee.status_pajak = "TK0"  # Default to TK0 if not set
            frappe.msgprint(_("Warning: Employee tax status not set, using TK0 as default"))

        # Get TER rate based on status and gross income - with caching
        status_pajak = employee.status_pajak
        gross_pay = doc.gross_pay
        
        # Get TER rate with caching
        ter_rate = get_ter_rate(status_pajak, gross_pay)
        
        # Calculate tax using TER
        monthly_tax = gross_pay * ter_rate

        # Save TER info
        doc.is_using_ter = 1
        doc.ter_rate = ter_rate * 100  # Convert to percentage for display

        # Update PPh 21 component
        update_component_amount(doc, "PPh 21", monthly_tax, "deductions")

        # Update note with TER info
        doc.payroll_note += "\n\n=== Perhitungan PPh 21 dengan TER ==="
        doc.payroll_note += f"\nStatus Pajak: {status_pajak}"
        doc.payroll_note += f"\nPenghasilan Bruto: Rp {gross_pay:,.0f}"
        doc.payroll_note += f"\nTarif Efektif Rata-rata: {ter_rate * 100:.2f}%"
        doc.payroll_note += f"\nPPh 21 Sebulan: Rp {monthly_tax:,.0f}"
        doc.payroll_note += "\n\nSesuai PMK 168/2023 tentang Tarif Efektif Rata-rata"

    except Exception as e:
        frappe.log_error(
            f"TER Calculation Error for Employee {getattr(employee, 'name', 'unknown')}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "TER Calculation Error"
        )
        frappe.throw(_("Error calculating PPh 21 with TER: {0}").format(str(e)))

def get_ter_rate(status_pajak, income):
    """
    Get TER rate based on status and income - with caching for efficiency
    Args:
        status_pajak: Employee tax status (e.g., "TK0", "K1", etc.)
        income: Monthly income amount
    Returns:
        float: TER rate as decimal (e.g., 0.05 for 5%)
    """
    global _ter_rate_cache, _ter_rate_last_clear
    
    try:
        # Check if cache clearing is needed (every 30 minutes)
        now = now_datetime()
        if (now - _ter_rate_last_clear).total_seconds() > 1800:  # 30 minutes in seconds
            _ter_rate_cache = {}
            _ter_rate_last_clear = now
        
        # Validate inputs
        if not status_pajak:
            status_pajak = "TK0"
            
        if not income or income <= 0:
            return 0
            
        # Create a unique cache key
        income_bracket = round(income, -3)  # Round to nearest thousand for better cache hits
        cache_key = f"{status_pajak}:{income_bracket}"
        
        # Check cache first
        if cache_key in _ter_rate_cache:
            return _ter_rate_cache[cache_key]
        
        # Get TER rate from database - use efficient SQL query
        ter = frappe.db.sql("""
            SELECT rate
            FROM `tabPPh 21 TER Table`
            WHERE status_pajak = %s
              AND %s >= income_from
              AND (%s <= income_to OR income_to = 0)
            LIMIT 1
        """, (status_pajak, income, income), as_dict=1)

        if not ter:
            # Try fallback to simpler status (e.g., TK3 -> TK0)
            status_fallback = status_pajak[0:2] + "0"  # Fallback to TK0/K0/HB0
            
            # Check fallback cache
            fallback_cache_key = f"{status_fallback}:{income_bracket}"
            if fallback_cache_key in _ter_rate_cache:
                # Cache the result for original key too
                _ter_rate_cache[cache_key] = _ter_rate_cache[fallback_cache_key]
                return _ter_rate_cache[fallback_cache_key]
            
            # Query with fallback status
            ter = frappe.db.sql("""
                SELECT rate
                FROM `tabPPh 21 TER Table`
                WHERE status_pajak = %s
                  AND %s >= income_from
                  AND (%s <= income_to OR income_to = 0)
                LIMIT 1
            """, (status_fallback, income, income), as_dict=1)

            if not ter:
                # As a last resort, use default rate from settings
                # Get this using cached value for better performance
                try:
                    pph_settings = frappe.get_cached_value(
                        "PPh 21 Settings", 
                        "PPh 21 Settings", 
                        "default_ter_rate",
                        as_dict=False
                    )
                    
                    if pph_settings:
                        default_rate = flt(pph_settings)
                        
                        # Cache the result
                        rate_value = default_rate / 100.0
                        _ter_rate_cache[cache_key] = rate_value
                        return rate_value
                    else:
                        # Last resort - use hardcoded default
                        _ter_rate_cache[cache_key] = 0.05  # Default 5%
                        return 0.05
                        
                except Exception:
                    # Last resort - use hardcoded default
                    _ter_rate_cache[cache_key] = 0.05  # Default 5%
                    return 0.05
        
        # Cache the result before returning
        rate_value = float(ter[0].rate) / 100.0
        _ter_rate_cache[cache_key] = rate_value
        
        # Return the decimal rate (e.g., 0.05 for 5%)
        return rate_value
        
    except Exception as e:
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
        frappe.log_error(
            f"Error getting TER rate for status {status_pajak} and income {income}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "TER Rate Error"
        )
        # Return default rate on error (5%)
        return 0.05

def should_use_ter_method(employee, pph_settings=None):
    """
    Determine if TER method should be used for this employee - optimized version
    Args:
        employee: Employee document
        pph_settings: PPh 21 Settings document (optional)
    Returns:
        bool: True if TER should be used, False otherwise
    """
    try:
        # Get PPh 21 Settings if not provided - use cached value for better performance
        if not pph_settings:
            pph_settings = frappe.get_cached_value(
                "PPh 21 Settings", 
                "PPh 21 Settings",
                ["calculation_method", "use_ter"],
                as_dict=True
            ) or {}
        
        # Fast path for global TER setting disabled
        if (pph_settings.get('calculation_method') != "TER" or 
            not pph_settings.get('use_ter')):
            return False
            
        # Fast path for employee exclusions
        if hasattr(employee, 'tipe_karyawan') and employee.tipe_karyawan == "Freelance":
            return False
            
        if hasattr(employee, 'override_tax_method') and employee.override_tax_method == "Progressive":
            return False
            
        # If we made it here, use TER method
        return True
            
    except Exception as e:
        frappe.log_error(
            f"Error determining TER eligibility for {getattr(employee, 'name', 'unknown')}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "TER Eligibility Error"
        )
        # Default to False on error
        return False

# Enhanced functions for better YTD tax calculations
def get_ytd_totals_from_tax_summary(employee, year, month):
    """
    Get YTD tax totals from Employee Tax Summary with caching
    Args:
        employee: Employee ID
        year: Current year
        month: Current month (1-12)
    Returns:
        dict: Dictionary with ytd_gross, ytd_tax, ytd_bpjs
    """
    global _ytd_tax_cache
    
    # Create cache key
    cache_key = f"{employee}:{year}:{month}"
    
    # Check cache first
    if cache_key in _ytd_tax_cache:
        return _ytd_tax_cache[cache_key]
    
    try:
        # Use a single efficient SQL query to get all needed data
        ytd_data = frappe.db.sql("""
            SELECT 
                ETS.ytd_tax,
                SUM(ETSD.gross_pay) as ytd_gross,
                SUM(ETSD.bpjs_deductions) as ytd_bpjs
            FROM 
                `tabEmployee Tax Summary` ETS
            LEFT JOIN
                `tabEmployee Tax Summary Detail` ETSD ON ETS.name = ETSD.parent
            WHERE 
                ETS.employee = %s
                AND ETS.year = %s
                AND ETSD.month < %s
            GROUP BY
                ETS.name
        """, (employee, year, month), as_dict=1)
        
        if ytd_data and ytd_data[0]:
            result = {
                'ytd_gross': flt(ytd_data[0].ytd_gross),
                'ytd_tax': flt(ytd_data[0].ytd_tax),
                'ytd_bpjs': flt(ytd_data[0].ytd_bpjs)
            }
            
            # Cache the result (for 10 minutes)
            _ytd_tax_cache[cache_key] = result
            
            # Schedule cache cleanup
            schedule_cache_cleanup()
            
            return result
        else:
            # No data found, return zeros
            result = {'ytd_gross': 0, 'ytd_tax': 0, 'ytd_bpjs': 0}
            _ytd_tax_cache[cache_key] = result
            return result
    
    except Exception as e:
        frappe.log_error(
            f"Error getting YTD tax data for {employee}, {year}, {month}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "YTD Tax Data Error"
        )
        
        # Fallback to the older method if SQL fails
        return get_ytd_totals_from_tax_summary_legacy(employee, year, month)

def get_ytd_totals_from_tax_summary_legacy(employee, year, month):
    """
    Legacy fallback method to get YTD tax totals from Employee Tax Summary
    """
    try:
        # Find Employee Tax Summary for this employee and year
        tax_summary = frappe.get_all(
            "Employee Tax Summary",
            filters={"employee": employee, "year": year, "docstatus": ["!=", 2]},
            fields=["name", "ytd_tax"],
            limit=1
        )
        
        if not tax_summary:
            return {'ytd_gross': 0, 'ytd_tax': 0, 'ytd_bpjs': 0}
            
        # Get monthly details for YTD calculations
        monthly_details = frappe.get_all(
            "Employee Tax Summary Detail",
            filters={"parent": tax_summary[0].name, "month": ["<", month]},
            fields=["gross_pay", "bpjs_deductions"],
            order_by="month asc"
        )
        
        # Calculate YTD totals
        ytd_gross = sum(flt(d.gross_pay) for d in monthly_details)
        ytd_bpjs = sum(flt(d.bpjs_deductions) for d in monthly_details)
        ytd_tax = flt(tax_summary[0].ytd_tax)
        
        return {
            'ytd_gross': ytd_gross,
            'ytd_tax': ytd_tax,
            'ytd_bpjs': ytd_bpjs
        }
        
    except Exception as e:
        frappe.log_error(
            f"Error getting YTD tax data (legacy) for {employee}, {year}, {month}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "YTD Tax Legacy Error"
        )
        return {'ytd_gross': 0, 'ytd_tax': 0, 'ytd_bpjs': 0}

# Function to schedule cache cleanup after 10 minutes
_cleanup_scheduled = False
def schedule_cache_cleanup():
    """Schedule cache cleanup to prevent memory bloat"""
    global _cleanup_scheduled
    
    if not _cleanup_scheduled:
        _cleanup_scheduled = True
        
        try:
            frappe.enqueue(
                clean_ytd_tax_cache,
                queue='long',
                is_async=True,
                job_name='clean_ytd_tax_cache',
                enqueue_after=600  # 10 minutes
            )
        except Exception:
            # If scheduling fails, we'll try again next time
            _cleanup_scheduled = False

def clean_ytd_tax_cache():
    """Clean YTD tax cache to prevent memory bloat"""
    global _ytd_tax_cache, _cleanup_scheduled
    _ytd_tax_cache = {}
    _cleanup_scheduled = False

