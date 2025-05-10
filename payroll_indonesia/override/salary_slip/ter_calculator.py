# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-08 08:54:46 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate, cint, now_datetime
import hashlib

from .base import update_component_amount

# Import the newly created add_tax_info_to_note function from tax_calculator
from .tax_calculator import add_tax_info_to_note

# Cache for TER rates to avoid repeated queries - cleared every 30 minutes
_ter_rate_cache = {}
_ter_rate_last_clear = now_datetime()
_ptkp_mapping_cache = None

def calculate_monthly_pph_with_ter(doc, employee):
    """Calculate PPh 21 using TER method based on PMK 168/2023"""
    try:
        # Validate employee status_pajak
        if not hasattr(employee, 'status_pajak') or not employee.status_pajak:
            employee.status_pajak = "TK0"  # Default to TK0 if not set
            frappe.msgprint(_("Warning: Employee tax status not set, using TK0 as default"))

        # Log start of TER calculation for debugging
        frappe.logger().debug(f"TER calculation start for {doc.name}, employee: {getattr(employee, 'name', 'unknown')}")
        frappe.logger().debug(f"Initial gross_pay: {doc.gross_pay}")

        # Pastikan gross_pay adalah nilai bulanan, bukan tahunan
        original_gross_pay = doc.gross_pay
        monthly_gross_pay = original_gross_pay
        
        # Improved detection logic for annual vs monthly gross_pay
        total_earnings = sum(flt(e.amount) for e in doc.earnings) if hasattr(doc, 'earnings') and doc.earnings else 0
        
        # Detect if gross_pay might be annual
        is_annual = False
        reason = ""
        
        # Case 1: Compare with total earnings if available
        if total_earnings > 0:
            if original_gross_pay > total_earnings * 3:
                is_annual = True
                reason = f"gross_pay ({original_gross_pay}) significantly exceeds total earnings ({total_earnings})"
                monthly_gross_pay = total_earnings
        
        # Case 2: Check for unreasonably high values (likely annual)
        elif original_gross_pay > 100000000:  # 100 million threshold
            is_annual = True
            reason = f"gross_pay exceeds 100,000,000 which is unlikely for monthly salary"
            monthly_gross_pay = original_gross_pay / 12
        
        # Case 3: Look for specific components if earnings comparison didn't trigger
        elif not is_annual and hasattr(doc, 'earnings'):
            # Find Gaji Pokok or Basic Salary component
            basic_salary = 0
            for e in doc.earnings:
                if e.salary_component in ["Gaji Pokok", "Basic Salary", "Basic Pay"]:
                    basic_salary = flt(e.amount)
                    break
            
            # Compare gross_pay with basic salary if found
            if basic_salary > 0 and original_gross_pay > basic_salary * 10:
                is_annual = True
                reason = f"gross_pay ({original_gross_pay}) is more than 10x basic salary ({basic_salary})"
                
                # Check if gross_pay is close to 12x the basic salary
                if 11 < (original_gross_pay / basic_salary) < 13:
                    monthly_gross_pay = original_gross_pay / 12
                else:
                    monthly_gross_pay = total_earnings  # Use total earnings as fallback
                    
        # Log if an adjustment was made
        if is_annual:
            frappe.logger().warning(
                f"Detected annual gross_pay in TER calculation for {doc.name}: {reason}. "
                f"Adjusted from {original_gross_pay} to {monthly_gross_pay}"
            )
            
            # Store the adjustment reason for reference
            if hasattr(doc, 'ter_calculation_note'):
                doc.ter_calculation_note = f"Adjusted gross_pay from {original_gross_pay:,.0f} to {monthly_gross_pay:,.0f} ({reason})"
                
        frappe.logger().debug(f"Using monthly_gross_pay: {monthly_gross_pay} for TER calculation")
        
        # Get status_pajak
        status_pajak = employee.status_pajak
        
        # Map PTKP status to TER category
        ter_category = map_ptkp_to_ter_category(status_pajak)
        frappe.logger().debug(f"TER category: {ter_category}")
        
        # Get TER rate using TER category and MONTHLY INCOME
        ter_rate = get_ter_rate(ter_category, monthly_gross_pay)
        frappe.logger().debug(f"TER rate: {ter_rate}")
        
        # Calculate tax using TER - LANGSUNG MENGALIKAN DENGAN INCOME BULANAN
        monthly_tax = monthly_gross_pay * ter_rate
        frappe.logger().debug(f"Monthly tax calculation: {monthly_gross_pay} * {ter_rate} = {monthly_tax}")

        # Save TER info - NILAI INI PERLU DIATUR DAN DISIMPAN DENGAN BENAR
        doc.is_using_ter = 1
        doc.ter_rate = ter_rate * 100  # Convert to percentage for display
        
        # PENTING: Pastikan nilai tersimpan ke database menggunakan db_set
        # Ini akan memastikan nilai tersimpan langsung ke database, bukan hanya di objek Python
        doc.db_set('is_using_ter', 1, update_modified=False)
        doc.db_set('ter_rate', ter_rate * 100, update_modified=False)
        
        # Simpan juga ter_category jika field tersedia
        if hasattr(doc, 'ter_category'):
            doc.ter_category = ter_category
            doc.db_set('ter_category', ter_category, update_modified=False)

        # Tambahkan logging debug untuk memverifikasi nilai telah diatur
        frappe.logger().debug(f"TER values set: is_using_ter={doc.is_using_ter}, ter_rate={doc.ter_rate}, ter_category={ter_category}")

        # Update PPh 21 component
        update_component_amount(doc, "PPh 21", monthly_tax, "deductions")

        # Add note about adjustment if needed
        adjustment_note = ""
        if monthly_gross_pay != original_gross_pay:
            adjustment_note = f" (Penghasilan disesuaikan dari {original_gross_pay:,.0f} ke {monthly_gross_pay:,.0f})"

        # Use the centralized function to add tax info to payroll note
        add_tax_info_to_note(doc, "TER", {
            "status_pajak": status_pajak,
            "ter_category": ter_category,
            "gross_pay": monthly_gross_pay,  # Use the adjusted monthly gross pay
            "ter_rate": ter_rate * 100,
            "monthly_tax": monthly_tax,
            "note": f"Perhitungan TER: penghasilan bulanan × tarif TER{adjustment_note}"
        })
        
        # TAMBAHAN: Verifikasi nilai ter setelah kalkulasi
        verify_ter_values(doc, ter_rate, ter_category)
        
        frappe.logger().debug(f"TER calculation completed for {doc.name}")

    except Exception as e:
        frappe.log_error(
            f"TER Calculation Error for Employee {getattr(employee, 'name', 'unknown')}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "TER Calculation Error"
        )
        frappe.throw(_("Error calculating PPh 21 with TER: {0}").format(str(e)))

def verify_ter_values(doc, ter_rate, ter_category):
    """
    Verifikasi nilai TER telah diatur dan tersimpan dengan benar
    Mencoba memastikan nilai is_using_ter tercenting
    """
    try:
        # Cek nilai is_using_ter seharusnya 1
        if not getattr(doc, 'is_using_ter', 0) == 1:
            frappe.logger().warning(f"TER values verification failed - is_using_ter not set to 1 for {doc.name}")
            # Atur ulang nilai menggunakan db_set langsung ke database
            doc.is_using_ter = 1
            doc.db_set('is_using_ter', 1, update_modified=False)
            
        # Verifikasi ter_rate
        expected_ter_rate = ter_rate * 100
        current_ter_rate = getattr(doc, 'ter_rate', 0)
        if abs(current_ter_rate - expected_ter_rate) > 0.01:  # Allow small floating point differences
            frappe.logger().warning(
                f"TER rate verification failed for {doc.name}: expected {expected_ter_rate}, got {current_ter_rate}"
            )
            # Atur ulang nilai
            doc.ter_rate = expected_ter_rate
            doc.db_set('ter_rate', expected_ter_rate, update_modified=False)
            
        # Verifikasi ter_category jika field tersedia
        if hasattr(doc, 'ter_category') and doc.ter_category != ter_category:
            frappe.logger().warning(
                f"TER category verification failed for {doc.name}: expected {ter_category}, got {doc.ter_category}"
            )
            doc.ter_category = ter_category
            doc.db_set('ter_category', ter_category, update_modified=False)
            
        # Verifikasi ulang setelah pengaturan
        frappe.logger().debug(
            f"TER values after verification: is_using_ter={getattr(doc, 'is_using_ter', 0)}, "
            f"ter_rate={getattr(doc, 'ter_rate', 0)}, ter_category={getattr(doc, 'ter_category', '')}"
        )
        
        # Force reload objek untuk memastikan nilai baru terbaca dari database
        if hasattr(doc, 'reload'):
            doc.reload()
            frappe.logger().debug(
                f"TER values after reload: is_using_ter={getattr(doc, 'is_using_ter', 0)}, "
                f"ter_rate={getattr(doc, 'ter_rate', 0)}"
            )
            
    except Exception as e:
        frappe.logger().error(f"Error during TER values verification for {doc.name}: {str(e)}")
        # We don't throw here since this is a verification function, not a critical calculation
              
def map_ptkp_to_ter_category(status_pajak):
    """
    Map PTKP status to TER category based on PMK 168/2023
    
    Args:
        status_pajak (str): PTKP status (e.g., 'TK0', 'K1', etc.)
    
    Returns:
        str: TER category ('TER A', 'TER B', or 'TER C')
    """
    global _ptkp_mapping_cache
    
    try:
        # Try to get the mapping from cache first
        if _ptkp_mapping_cache is None:
            # Get mapping from defaults.json config
            try:
                from payroll_indonesia.payroll_indonesia.utils import get_default_config
                config = get_default_config()
                if config and "ptkp_to_ter_mapping" in config:
                    mapping = config["ptkp_to_ter_mapping"]
                else:
                    mapping = None
            except ImportError:
                mapping = None
            
            if not mapping:
                # Use hardcoded mapping based on PMK 168/2023
                mapping = {
                    # TER A: PTKP TK/0 (Rp 54 juta/tahun)
                    "TK0": "TER A",
                    
                    # TER B: PTKP K/0, TK/1, TK/2, K/1 (Rp 58,5-63 juta/tahun)
                    "TK1": "TER B",
                    "TK2": "TER B",
                    "K0": "TER B",
                    "K1": "TER B",
                    
                    # TER C: All other PTKP statuses with higher values
                    "TK3": "TER C",
                    "K2": "TER C", 
                    "K3": "TER C",
                    "HB0": "TER C",
                    "HB1": "TER C",
                    "HB2": "TER C",
                    "HB3": "TER C"
                }
                
            # Cache the mapping
            _ptkp_mapping_cache = mapping
        
        # Return mapped category or default to TER C if status not found
        if status_pajak in _ptkp_mapping_cache:
            return _ptkp_mapping_cache[status_pajak]
        else:
            # Default to TER C for any unknown status
            return "TER C"
            
    except Exception as e:
        frappe.log_error(
            f"Error mapping PTKP status to TER category: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "TER Mapping Error"
        )
        # Default to TER C as safest option
        return "TER C"

def get_ter_rate(ter_category, income):
    """
    Get TER rate based on TER category and income - with caching for efficiency
    
    Args:
        ter_category: TER category ('TER A', 'TER B', 'TER C')
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
        if not ter_category:
            ter_category = "TER C"  # Default to highest category if not specified
            
        if not income or income <= 0:
            return 0
            
        # Create a unique cache key
        income_bracket = round(income, -3)  # Round to nearest thousand for better cache hits
        cache_key = f"{ter_category}:{income_bracket}"
        
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
            ORDER BY income_from DESC
            LIMIT 1
        """, (ter_category, income, income), as_dict=1)

        if ter:
            # Cache the result before returning
            rate_value = float(ter[0].rate) / 100.0
            _ter_rate_cache[cache_key] = rate_value
            return rate_value
        else:
            # Try to find using highest available bracket
            ter = frappe.db.sql("""
                SELECT rate
                FROM `tabPPh 21 TER Table`
                WHERE status_pajak = %s
                  AND is_highest_bracket = 1
                LIMIT 1
            """, (ter_category,), as_dict=1)
            
            if ter:
                # Cache the highest bracket result
                rate_value = float(ter[0].rate) / 100.0
                _ter_rate_cache[cache_key] = rate_value
                return rate_value
            else:
                # As a last resort, use default rate from settings or hardcoded value
                try:
                    # Fall back to defaults.json values
                    from payroll_indonesia.payroll_indonesia.utils import get_default_config
                    config = get_default_config()
                    if config and "ter_rates" in config and ter_category in config["ter_rates"]:
                        # Get the highest rate from the category
                        highest_rate = 0
                        for rate_data in config["ter_rates"][ter_category]:
                            if "is_highest_bracket" in rate_data and rate_data["is_highest_bracket"]:
                                highest_rate = flt(rate_data["rate"])
                                break
                        
                        if highest_rate > 0:
                            rate_value = highest_rate / 100.0
                            _ter_rate_cache[cache_key] = rate_value
                            return rate_value
                    
                    # PMK 168/2023 highest rate is 34% for all categories
                    _ter_rate_cache[cache_key] = 0.34
                    return 0.34
                        
                except Exception:
                    # Last resort - use PMK 168/2023 highest rate
                    _ter_rate_cache[cache_key] = 0.34
                    return 0.34
        
    except Exception as e:
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
        frappe.log_error(
            f"Error getting TER rate for category {ter_category} and income {income}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "TER Rate Error"
        )
        # Return PMK 168/2023 highest rate on error (34%)
        return 0.34

def should_use_ter_method(employee, pph_settings=None):
    """
    Determine if TER method should be used for this employee according to PMK 168/2023
    
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
            
        # Special cases
        
        # December always uses Progressive method as per PMK 168/2023
        # Check if current month is December
        current_month = getdate().month
        if current_month == 12:
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
    
    # Ensure _ytd_tax_cache exists
    if "_ytd_tax_cache" not in globals():
        global _ytd_tax_cache
        _ytd_tax_cache = {}
    
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
    global _ytd_tax_cache, _cleanup_scheduled, _ptkp_mapping_cache
    _ytd_tax_cache = {}
    _ptkp_mapping_cache = None  # Also clear the PTKP mapping cache
    _cleanup_scheduled = False