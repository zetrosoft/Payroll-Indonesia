# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 06:46:52 by dannyaudian

"""
Implementation of tax calculation as per Indonesian regulations.

Tax calculation methods:
1. TER (Tarif Efektif Rata-rata) - As per PMK 168/2023
   - Used for monthly calculations (Jan-Nov)
   - Uses a lookup table based on employee's tax status and monthly income
   - Direct application of TER rate to monthly gross income
   
2. Progressive - Traditional method
   - Used for December calculations (required by PMK 168/2023)
   - Used for employees with irregular income
   - Calculates annual income, applies progressive tax rates, divides by 12
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, cint, now_datetime

from .base import update_component_amount, get_component_amount

# Import mapping function directly from pph_ter.py
from payroll_indonesia.payroll_indonesia.tax.pph_ter import map_ptkp_to_ter_category

# Import centralized cache utilities
from payroll_indonesia.utilities.cache_utils import get_cached_value, cache_value, clear_cache

def calculate_tax_components(doc, employee):
    """
    Central entry point for all tax calculations - decides between TER or progressive methods
    
    Args:
        doc: Salary slip document
        employee: Employee document
    """
    try:
        # Initialize total_bpjs to 0 if None to prevent NoneType subtraction error
        if doc.total_bpjs is None:
            doc.total_bpjs = 0
            
        # Handle NPWP Gabung Suami case
        if hasattr(employee, 'gender') and employee.gender == "Female" and hasattr(employee, 'npwp_gabung_suami') and cint(employee.get("npwp_gabung_suami")):
            doc.is_final_gabung_suami = 1
            add_tax_info_to_note(doc, "PROGRESSIVE", {
                "message": "Pajak final digabung dengan NPWP suami"
            })
            return

        # Calculate Biaya Jabatan (5% of gross, max 500k)
        doc.biaya_jabatan = min(doc.gross_pay * 0.05, 500000)

        # Calculate netto income
        doc.netto = doc.gross_pay - doc.biaya_jabatan - doc.total_bpjs

        # Set basic payroll note
        set_basic_payroll_note(doc, employee)
        
        # For December, always use progressive method as per PMK 168/2023
        if is_december(doc):
            # Force disable TER for December according to PMK 168/2023
            doc.is_using_ter = 0
            calculate_december_pph(doc, employee)
            return
            
        # Decision logic for other months: determine which tax method to use
        # Check employee override first
        if hasattr(employee, 'override_tax_method'):
            # If employee has explicit override to TER
            if employee.override_tax_method == "TER":
                return calculate_monthly_pph_with_ter(doc, employee)
            # If employee has explicit override to Progressive
            elif employee.override_tax_method == "Progressive":
                return calculate_monthly_pph_progressive(doc, employee)
        
        # No explicit override, check company settings
        try:
            pph_settings = frappe.get_single("PPh 21 Settings")
            if (hasattr(pph_settings, 'calculation_method') and 
                pph_settings.calculation_method == "TER" and
                hasattr(pph_settings, 'use_ter') and
                cint(pph_settings.use_ter) == 1):
                
                # Check month - TER should not be used for December as per PMK 168/2023
                current_month = getdate(doc.start_date).month if hasattr(doc, 'start_date') else getdate().month
                if current_month != 12:
                    # Check employee eligibility for TER
                    if not should_exclude_from_ter(employee):
                        return calculate_monthly_pph_with_ter(doc, employee)
        except Exception as e:
            frappe.log_error(
                f"Error checking PPh 21 Settings: {str(e)}, falling back to Progressive method",
                "Tax Method Selection Error"
            )
            
        # Default to progressive method
        return calculate_monthly_pph_progressive(doc, employee)
    
    except Exception as e:
        frappe.log_error(
            f"Tax Calculation Error for Employee {employee.name}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "Tax Calculation Error"
        )
        # Convert to user-friendly error
        frappe.throw(_("Error calculating tax components: {0}").format(str(e)))

def should_exclude_from_ter(employee):
    """
    Check if employee should be excluded from TER method based on criteria
    
    Args:
        employee: Employee document
        
    Returns:
        bool: True if employee should be excluded from TER
    """
    # Freelance employees should use Progressive method
    if hasattr(employee, 'tipe_karyawan') and employee.tipe_karyawan == "Freelance":
        return True
    
    # Check other exclusion criteria here
    # ...
    
    # Not excluded
    return False

def calculate_monthly_pph_with_ter(doc, employee):
    """
    Calculate PPh 21 using TER method based on PMK 168/2023
    This implementation replaces the imported function from ter_calculator.py
    
    Args:
        doc: Salary slip document
        employee: Employee document
        
    Returns:
        bool: True if calculation completed successfully
    """
    try:
        # Validate employee status_pajak
        if not hasattr(employee, 'status_pajak') or not employee.status_pajak:
            employee.status_pajak = "TK0"
            frappe.msgprint(_("Warning: Employee tax status not set, using TK0 as default"))

        # PENTING: Gunakan monthly_gross_for_ter untuk perhitungan
        monthly_gross_pay = detect_and_adjust_annual_value(doc)
            
        # Set dan simpan nilai bulanan dan tahunan
        annual_taxable_amount = flt(monthly_gross_pay * 12)
        
        # Simpan monthly_gross_for_ter
        if hasattr(doc, 'monthly_gross_for_ter'):
            doc.monthly_gross_for_ter = monthly_gross_pay
            doc.db_set('monthly_gross_for_ter', monthly_gross_pay, update_modified=False)
            
        # Simpan annual_taxable_amount
        if hasattr(doc, 'annual_taxable_amount'):
            doc.annual_taxable_amount = annual_taxable_amount
            doc.db_set('annual_taxable_amount', annual_taxable_amount, update_modified=False)

        # Tentukan TER category dan rate
        ter_category = map_ptkp_to_ter_category(employee.status_pajak)
        ter_rate = get_ter_rate(ter_category, monthly_gross_pay)
        
        # Hitung PPh 21 bulanan
        monthly_tax = flt(monthly_gross_pay * ter_rate)
        
        # Set dan simpan info TER
        doc.is_using_ter = 1
        doc.ter_rate = flt(ter_rate * 100)
        doc.ter_category = ter_category
        
        # Simpan langsung ke database
        doc.db_set('is_using_ter', 1, update_modified=False)
        doc.db_set('ter_rate', flt(ter_rate * 100), update_modified=False)
        doc.db_set('ter_category', ter_category, update_modified=False)

        # Update komponen PPh 21
        update_component_amount(doc, "PPh 21", monthly_tax, "deductions")

        # Add tax info to note
        add_tax_info_to_note(doc, "TER", {
            "status_pajak": employee.status_pajak,
            "ter_category": ter_category,
            "gross_pay": monthly_gross_pay,
            "ter_rate": ter_rate * 100,
            "monthly_tax": monthly_tax
        })

        frappe.logger().debug(f"[TER] Calculation completed for {doc.name}")
        return True

    except Exception as e:
        frappe.log_error(
            f"[TER] Error calculating PPh 21 for {doc.name}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "TER Calculation Error"
        )
        raise

def detect_and_adjust_annual_value(doc):
    """
    Detect if gross_pay is an annual value and adjust to monthly
    
    Args:
        doc: Salary slip document
    
    Returns:
        float: Adjusted monthly gross pay
    """
    monthly_gross_pay = flt(doc.gross_pay)  # Start with gross_pay
    is_annual = False
    reason = ""

    # Bypass annual detection if configured
    if getattr(doc, 'bypass_annual_detection', 0):
        return monthly_gross_pay
        
    # Hitung total earnings jika tersedia
    total_earnings = flt(sum(flt(e.amount) for e in doc.earnings)) if hasattr(doc, 'earnings') and doc.earnings else 0
    
    # Deteksi berdasarkan total earnings
    if total_earnings > 0 and flt(doc.gross_pay) > (total_earnings * 3):
        is_annual = True
        reason = f"Gross pay ({doc.gross_pay}) exceeds 3x total earnings ({total_earnings})"
        monthly_gross_pay = total_earnings
    
    # Deteksi nilai terlalu besar
    elif flt(doc.gross_pay) > 100000000:
        is_annual = True
        reason = "Gross pay exceeds 100 million (likely annual)"
        monthly_gross_pay = flt(doc.gross_pay / 12)

    # Deteksi berdasarkan basic salary
    elif hasattr(doc, 'earnings'):
        basic_salary = next(
            (flt(e.amount) for e in doc.earnings 
                if e.salary_component in ["Gaji Pokok", "Basic Salary", "Basic Pay"]), 
            0
        )
        if basic_salary > 0 and flt(doc.gross_pay) > (basic_salary * 10):
            is_annual = True
            reason = f"Gross pay exceeds 10x basic salary ({basic_salary})"
            monthly_gross_pay = (
                flt(doc.gross_pay / 12) 
                if 11 < (doc.gross_pay / basic_salary) < 13
                else total_earnings
            )

    # Log deteksi nilai tahunan
    if is_annual:
        frappe.logger().warning(
            f"[TAX] {doc.name}: Detected annual value - {reason}. "
            f"Adjusted from {doc.gross_pay} to monthly {monthly_gross_pay}"
        )
        
        if hasattr(doc, 'payroll_note'):
            doc.payroll_note += f"\n[TAX] {reason}. Using monthly value: {monthly_gross_pay}"
    
    return monthly_gross_pay

def get_ter_rate(ter_category, income):
    """
    Get TER rate based on TER category and income - with caching for efficiency
    
    Args:
        ter_category: TER category ('TER A', 'TER B', 'TER C')
        income: Monthly income amount
        
    Returns:
        float: TER rate as decimal (e.g., 0.05 for 5%)
    """
    try:
        # Validate inputs
        if not ter_category:
            ter_category = "TER C"  # Default to highest category if not specified
            
        if not income or income <= 0:
            return 0
            
        # Create a unique cache key
        income_bracket = round(income, -3)  # Round to nearest thousand for better cache hits
        cache_key = f"ter_rate:{ter_category}:{income_bracket}"
        
        # Check cache first using cache_utils
        cached_rate = get_cached_value(cache_key)
        if cached_rate is not None:
            return cached_rate
        
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
            cache_value(cache_key, rate_value, 1800)  # Cache for 30 minutes
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
                cache_value(cache_key, rate_value, 1800)  # Cache for 30 minutes
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
                            cache_value(cache_key, rate_value, 1800)  # Cache for 30 minutes
                            return rate_value
                    
                    # PMK 168/2023 highest rate is 34% for all categories
                    default_rate = 0.34
                    cache_value(cache_key, default_rate, 1800)  # Cache for 30 minutes
                    return default_rate
                        
                except Exception:
                    # Last resort - use PMK 168/2023 highest rate
                    default_rate = 0.34
                    cache_value(cache_key, default_rate, 1800)  # Cache for 30 minutes
                    return default_rate
        
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

def calculate_monthly_pph_progressive(doc, employee):
    """
    Calculate PPh 21 using progressive rates - for regular months
    
    Args:
        doc: Salary slip document
        employee: Employee document
    """
    try:
        # Get PPh 21 Settings
        pph_settings = frappe.get_single("PPh 21 Settings")
        
        # Get PTKP value
        if not hasattr(employee, 'status_pajak') or not employee.status_pajak:
            employee.status_pajak = "TK0"  # Default to TK0 if not set
            frappe.msgprint(_("Warning: Employee tax status not set, using TK0 as default"))

        # Get annual values
        monthly_netto = doc.netto
        annual_netto = monthly_netto * 12
        ptkp = get_ptkp_amount(pph_settings, employee.status_pajak)
        pkp = max(annual_netto - ptkp, 0)

        # Calculate annual PPh
        annual_pph, tax_details = calculate_progressive_tax(pkp, pph_settings)
        
        # Calculate monthly PPh
        monthly_pph = annual_pph / 12

        # Update PPh 21 component
        update_component_amount(doc, "PPh 21", monthly_pph, "deductions")

        # Add tax info to note
        add_tax_info_to_note(doc, "PROGRESSIVE", {
            "status_pajak": employee.status_pajak,
            "monthly_netto": monthly_netto,
            "annual_netto": annual_netto,
            "ptkp": ptkp,
            "pkp": pkp,
            "tax_details": tax_details,
            "annual_pph": annual_pph,
            "monthly_pph": monthly_pph
        })

    except Exception as e:
        frappe.log_error(
            f"Progressive Tax Calculation Error for Employee {employee.name}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "Progressive Tax Calculation Error"
        )
        frappe.throw(_("Error calculating PPh 21 with progressive method: {0}").format(str(e)))

def calculate_december_pph(doc, employee):
    """
    Calculate year-end tax correction for December as per PMK 168/2023
    
    Args:
        doc: Salary slip document
        employee: Employee document
    """
    try:
        year = getdate(doc.end_date).year

        # Get PPh 21 Settings
        try:
            pph_settings = frappe.get_single("PPh 21 Settings")
        except Exception as e:
            frappe.throw(_("Error retrieving PPh 21 Settings: {0}. Please configure PPh 21 Settings properly.").format(str(e)))

        # Get year-to-date totals using cache_utils
        month = getdate(doc.start_date).month
        ytd = get_ytd_totals(doc.employee, year, month)

        # Calculate annual totals
        annual_gross = ytd.get("gross", 0) + doc.gross_pay
        annual_bpjs = ytd.get("bpjs", 0) + doc.total_bpjs
        
        # Biaya Jabatan is 5% of annual gross, max 500k/year according to regulations
        annual_biaya_jabatan = min(annual_gross * 0.05, 500000)
        annual_netto = annual_gross - annual_biaya_jabatan - annual_bpjs

        # Get PTKP value
        if not hasattr(employee, 'status_pajak') or not employee.status_pajak:
            employee.status_pajak = "TK0"  # Default to TK0 if not set
            frappe.msgprint(_("Warning: Employee tax status not set, using TK0 as default"))

        ptkp = get_ptkp_amount(pph_settings, employee.status_pajak)
        pkp = max(annual_netto - ptkp, 0)

        # Calculate annual PPh
        annual_pph, tax_details = calculate_progressive_tax(pkp, pph_settings)

        # Calculate correction
        correction = annual_pph - ytd.get("pph21", 0)
        doc.koreksi_pph21 = correction

        # Update December PPh 21
        update_component_amount(
            doc,
            "PPh 21",
            correction,
            "deductions"
        )

        # Add tax info to note with special December data
        add_tax_info_to_note(doc, "PROGRESSIVE_DECEMBER", {
            "status_pajak": employee.status_pajak,
            "annual_gross": annual_gross,
            "annual_biaya_jabatan": annual_biaya_jabatan,
            "annual_bpjs": annual_bpjs,
            "annual_netto": annual_netto,
            "ptkp": ptkp,
            "pkp": pkp,
            "tax_details": tax_details,
            "annual_pph": annual_pph,
            "ytd_pph": ytd.get("pph21", 0),
            "correction": correction
        })
        
    except Exception as e:
        frappe.log_error(
            f"December PPh Calculation Error for Employee {employee.name}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "December PPh Error"
        )
        frappe.throw(_("Error calculating December PPh 21 correction: {0}").format(str(e)))

def add_tax_info_to_note(doc, tax_method, values):
    """
    Add tax calculation details to payroll note with consistent formatting and
    section management to avoid duplication.
    
    Args:
        doc: Salary slip document
        tax_method: "PROGRESSIVE", "TER", or "PROGRESSIVE_DECEMBER"
        values: Dictionary with calculation values
    """
    try:
        # Initialize payroll_note if needed
        if not hasattr(doc, 'payroll_note'):
            doc.payroll_note = ""
        elif doc.payroll_note is None:
            doc.payroll_note = ""
            
        # Check if Tax calculation section already exists and remove it if found
        start_marker = "<!-- TAX_CALCULATION_START -->"
        end_marker = "<!-- TAX_CALCULATION_END -->"
        
        if start_marker in doc.payroll_note and end_marker in doc.payroll_note:
            start_idx = doc.payroll_note.find(start_marker)
            end_idx = doc.payroll_note.find(end_marker) + len(end_marker)
            
            # Remove the existing section
            doc.payroll_note = doc.payroll_note[:start_idx] + doc.payroll_note[end_idx:]
        
        # Add new tax calculation with section markers
        note_content = [
            "\n\n<!-- TAX_CALCULATION_START -->",
        ]
        
        if tax_method == "TER":
            # TER method - Used by ter_calculator.py
            status_pajak = values.get('status_pajak', 'TK0')
            ter_category = values.get('ter_category', '')
            mapping_info = f" → {ter_category}" if ter_category else ""
            
            note_content.extend([
                "=== Perhitungan PPh 21 dengan TER ===",
                f"Status Pajak: {status_pajak}{mapping_info}",
                f"Penghasilan Bruto: Rp {values.get('gross_pay', 0):,.0f}",
                f"Tarif Efektif Rata-rata: {values.get('ter_rate', 0):.2f}%",
                f"PPh 21 Sebulan: Rp {values.get('monthly_tax', 0):,.0f}",
                "",
                "Sesuai PMK 168/2023 tentang Tarif Efektif Rata-rata"
            ])
            
        elif tax_method == "PROGRESSIVE_DECEMBER":
            # Progressive method for December with year-end correction
            note_content.extend([
                "=== Perhitungan PPh 21 Tahunan (Desember) ===",
                f"Penghasilan Bruto Setahun: Rp {values.get('annual_gross', 0):,.0f}",
                f"Biaya Jabatan: Rp {values.get('annual_biaya_jabatan', 0):,.0f}",
                f"Total BPJS: Rp {values.get('annual_bpjs', 0):,.0f}",
                f"Penghasilan Neto: Rp {values.get('annual_netto', 0):,.0f}",
                f"PTKP ({values.get('status_pajak', 'TK0')}): Rp {values.get('ptkp', 0):,.0f}",
                f"PKP: Rp {values.get('pkp', 0):,.0f}",
                "",
                "Perhitungan Per Lapisan Pajak:"
            ])
            
            # Add tax bracket details if available
            tax_details = values.get('tax_details', [])
            if tax_details:
                for d in tax_details:
                    rate = flt(d.get('rate', 0))
                    taxable = flt(d.get('taxable', 0))
                    tax = flt(d.get('tax', 0))
                    note_content.append(
                        f"- Lapisan {rate:.0f}%: "
                        f"Rp {taxable:,.0f} × {rate:.0f}% = "
                        f"Rp {tax:,.0f}"
                    )
            else:
                note_content.append("- (Tidak ada rincian pajak)")
                
            # Add summary values
            annual_pph = flt(values.get('annual_pph', 0))
            ytd_pph = flt(values.get('ytd_pph', 0))
            correction = flt(values.get('correction', 0))
            
            note_content.extend([
                "",
                f"Total PPh 21 Setahun: Rp {annual_pph:,.0f}",
                f"PPh 21 Sudah Dibayar: Rp {ytd_pph:,.0f}",
                f"Koreksi Desember: Rp {correction:,.0f}",
                f"({'Kurang Bayar' if correction > 0 else 'Lebih Bayar'})",
                "",
                "Metode perhitungan Desember menggunakan metode progresif sesuai PMK 168/2023"
            ])
            
        elif tax_method == "PROGRESSIVE":
            # Regular progressive method for non-December months
            note_content.extend([
                "=== Perhitungan PPh 21 dengan Metode Progresif ===",
                f"Status Pajak: {values.get('status_pajak', 'TK0')}",
                f"Penghasilan Neto Sebulan: Rp {values.get('monthly_netto', 0):,.0f}",
                f"Penghasilan Neto Setahun: Rp {values.get('annual_netto', 0):,.0f}",
                f"PTKP: Rp {values.get('ptkp', 0):,.0f}",
                f"PKP: Rp {values.get('pkp', 0):,.0f}",
                "",
                "PPh 21 Tahunan:"
            ])
            
            # Add tax bracket details if available
            tax_details = values.get('tax_details', [])
            if tax_details:
                for d in tax_details:
                    rate = flt(d.get('rate', 0))
                    taxable = flt(d.get('taxable', 0))
                    tax = flt(d.get('tax', 0))
                    note_content.append(
                        f"- Lapisan {rate:.0f}%: "
                        f"Rp {taxable:,.0f} × {rate:.0f}% = "
                        f"Rp {tax:,.0f}"
                    )
            else:
                note_content.append("- (Tidak ada rincian pajak)")
                
            # Add monthly PPh
            annual_pph = flt(values.get('annual_pph', 0))
            monthly_pph = flt(values.get('monthly_pph', 0))
            note_content.extend([
                "",
                f"Total PPh 21 Setahun: Rp {annual_pph:,.0f}",
                f"PPh 21 Sebulan: Rp {monthly_pph:,.0f}"
            ])
        
        else:
            # Simple message (e.g., for NPWP Gabung Suami case)
            if "message" in values:
                note_content.extend([
                    "=== Informasi Pajak ===",
                    values.get("message", "")
                ])
            else:
                note_content.extend([
                    "=== Informasi Pajak ===",
                    "Tidak ada perhitungan PPh 21 yang dilakukan."
                ])
        
        # Add end marker
        note_content.append("<!-- TAX_CALCULATION_END -->")
        
        # Add the formatted note to payroll_note
        doc.payroll_note += "\n" + "\n".join(note_content)
        
    except Exception as e:
        # Log error but continue
        frappe.log_error(
            f"Error adding tax info to note: {str(e)}\nTraceback: {frappe.get_traceback()}",
            "Tax Note Error"
        )
        # Add a simple note to indicate there was an error
        if hasattr(doc, 'payroll_note'):
            doc.payroll_note += f"\n\nError adding tax calculation details: {str(e)}"
            
def calculate_progressive_tax(pkp, pph_settings=None):
    """
    Calculate tax using progressive rates
    
    Args:
        pkp: Penghasilan Kena Pajak (taxable income)
        pph_settings: PPh 21 Settings document (optional)
        
    Returns:
        tuple: (total_tax, tax_details)
    """
    try:
        if not pph_settings:
            try:
                pph_settings = frappe.get_single("PPh 21 Settings")
            except Exception as e:
                frappe.throw(_("Error retrieving PPh 21 Settings: {0}").format(str(e)))

        # First check if bracket_table is directly available as attribute
        bracket_table = []
        if hasattr(pph_settings, 'bracket_table'):
            bracket_table = pph_settings.bracket_table
            
        # If not found or empty, query from database
        if not bracket_table:
            bracket_table = frappe.db.sql("""
                SELECT income_from, income_to, tax_rate
                FROM `tabPPh 21 Tax Bracket`
                WHERE parent = 'PPh 21 Settings'
                ORDER BY income_from ASC
            """, as_dict=1)

        # If still not found, use default values
        if not bracket_table:
            # Default bracket values if not found - based on PMK 101/2016 and UU HPP 2021
            bracket_table = [
                {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
                {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
                {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
                {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
            ]
            frappe.msgprint(_("Tax brackets not configured, using default progressive rates."))

        # Calculate tax using progressive rates
        total_tax = 0
        tax_details = []
        remaining_pkp = pkp

        for bracket in sorted(bracket_table, key=lambda x: flt(x.get("income_from", 0))):
            if remaining_pkp <= 0:
                break

            income_from = flt(bracket.get("income_from", 0))
            income_to = flt(bracket.get("income_to", 0))
            tax_rate = flt(bracket.get("tax_rate", 0))

            # Handle unlimited upper bracket
            upper_limit = income_to if income_to > 0 else float('inf')
            lower_limit = income_from
            taxable = min(remaining_pkp, upper_limit - lower_limit)

            tax = taxable * (tax_rate / 100)
            total_tax += tax

            if tax > 0:
                tax_details.append({
                    'rate': tax_rate,
                    'taxable': taxable,
                    'tax': tax
                })

            remaining_pkp -= taxable

        return total_tax, tax_details
        
    except Exception as e:
        frappe.log_error(
            f"Progressive Tax Calculation Error for PKP {pkp}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "Tax Bracket Calculation Error"
        )
        frappe.throw(_("Error calculating progressive tax brackets: {0}").format(str(e)))

def get_ptkp_amount(pph_settings, status_pajak):
    """
    Get PTKP amount based on tax status
    
    Args:
        pph_settings: PPh 21 Settings document
        status_pajak: Tax status (e.g., 'TK0', 'K1', etc.)
        
    Returns:
        float: PTKP amount
    """
    try:
        # Get PTKP from settings
        ptkp_table = pph_settings.ptkp_table if hasattr(pph_settings, 'ptkp_table') else []
        
        # If not found, query from database
        if not ptkp_table:
            ptkp_table = frappe.db.sql("""
                SELECT status_pajak as tax_status, ptkp_amount as amount
                FROM `tabPPh 21 PTKP Table`
                WHERE parent = 'PPh 21 Settings'
            """, as_dict=1)
        
        # Find matching status
        for ptkp in ptkp_table:
            if hasattr(ptkp, 'tax_status') and ptkp.tax_status == status_pajak:
                return flt(ptkp.amount)
            
            # For backward compatibility
            if hasattr(ptkp, 'status_pajak') and ptkp.status_pajak == status_pajak:
                return flt(ptkp.ptkp_amount)
        
        # If not found, try to match prefix (TK0 -> TK)
        prefix = status_pajak[:2] if len(status_pajak) >= 2 else status_pajak
        for ptkp in ptkp_table:
            ptkp_status = ptkp.tax_status if hasattr(ptkp, 'tax_status') else ptkp.status_pajak
            if ptkp_status and ptkp_status.startswith(prefix):
                return flt(ptkp.amount if hasattr(ptkp, 'amount') else ptkp.ptkp_amount)
        
        # Default values if not found - based on PMK-101/PMK.010/2016 and updated values
        default_ptkp = {
            "TK": 54000000,  # TK/0
            "K": 58500000,   # K/0
            "HB": 112500000  # HB/0
        }
        
        # Return default based on prefix
        for key, value in default_ptkp.items():
            if status_pajak.startswith(key):
                return value
                
        # Last resort - TK0
        return 54000000  # Default for TK0
    
    except Exception as e:
        frappe.log_error(
            f"Error getting PTKP amount for {status_pajak}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "PTKP Calculation Error"
        )
        # Return default PTKP for TK0
        return 54000000

def get_ytd_totals(employee, year, month):
    """
    Get YTD data for employee with caching using cache_utils
    
    Args:
        employee: Employee ID
        year: The tax year
        month: The current month (1-12)
        
    Returns:
        dict: A dictionary with YTD values
    """
    # Create cache key
    cache_key = f"ytd_tax:{employee}:{year}:{month}"
    
    # Check cache first using cache_utils
    cached_data = get_cached_value(cache_key)
    if cached_data is not None:
        return cached_data
    
    # Default result
    result = {"gross": 0, "bpjs": 0, "pph21": 0}
    
    try:
        # Check if Employee Tax Summary DocType exists
        if not frappe.db.exists("DocType", "Employee Tax Summary"):
            frappe.msgprint(_("Employee Tax Summary DocType not found, using traditional YTD calculation"))
            return get_ytd_totals_legacy(employee, year, month)
            
        # Get Employee Tax Summary
        tax_summary = frappe.db.get_value(
            "Employee Tax Summary",
            {"employee": employee, "year": year},
            ["name"], 
            cache=True
        )
        
        if tax_summary:
            # Get all monthly details in one query for better performance
            monthly_details = frappe.db.sql("""
                SELECT 
                    month, 
                    gross_pay, 
                    bpjs_deductions, 
                    tax_amount
                FROM 
                    `tabEmployee Tax Summary Detail`
                WHERE 
                    parent = %s
                    AND month < %s
                ORDER BY 
                    month ASC
            """, (tax_summary, month), as_dict=1)
            
            # Calculate totals from monthly details
            for monthly in monthly_details:
                result["gross"] += flt(monthly.gross_pay if hasattr(monthly, 'gross_pay') else 0)
                result["bpjs"] += flt(monthly.bpjs_deductions if hasattr(monthly, 'bpjs_deductions') else 0)
                result["pph21"] += flt(monthly.tax_amount if hasattr(monthly, 'tax_amount') else 0)
                
            # Cache the result
            cache_value(cache_key, result, 3600)  # Cache for 1 hour
            return result
        else:
            frappe.msgprint(_("No Tax Summary found for employee, using traditional YTD calculation"))
    
    except Exception as e:
        frappe.log_error(
            f"Error getting YTD data for {employee}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}", 
            "YTD Tax Calculation Error"
        )
        frappe.msgprint(_("Error retrieving tax summary data: {0}").format(str(e)))
        
    # Fall back to traditional method if tax summary not found or error occurs
    result = get_ytd_totals_legacy(employee, year, month)
    cache_value(cache_key, result, 3600)  # Cache for 1 hour
    return result

def get_ytd_totals_legacy(employee, year, month):
    """
    Get year-to-date totals for the employee (legacy method)
    using direct database queries
    
    Args:
        employee: Employee ID
        year: The tax year
        month: The current month (1-12)
        
    Returns:
        dict: A dictionary with YTD values
    """
    try:
        # Create a default result with zeros
        result = {"gross": 0, "bpjs": 0, "pph21": 0}
        
        # Get start and end dates
        start_date = f"{year}-01-01"
        month_start_date = f"{year}-{month:02d}-01"
        
        # Get salary slips for the current employee in the current year
        # but before the current month using efficient query
        try:
            salary_slips = frappe.db.sql("""
                SELECT 
                    name,
                    gross_pay
                FROM 
                    `tabSalary Slip`
                WHERE 
                    employee = %s
                    AND YEAR(start_date) = %s
                    AND start_date >= %s
                    AND start_date < %s
                    AND docstatus = 1
            """, (employee, year, start_date, month_start_date), as_dict=1)
        except Exception as e:
            frappe.log_error(
                f"Error querying salary slips for {employee}: {str(e)}",
                "Salary Slip Query Error"
            )
            return result

        if not salary_slips:
            return result

        # Get the slip names for the second query
        slip_names = [slip.name for slip in salary_slips]
        
        # Add gross pay values
        for slip in salary_slips:
            result["gross"] += flt(slip.gross_pay)
        
        # Get components in a single query for better performance
        components = frappe.db.sql("""
            SELECT 
                parent,
                salary_component,
                amount
            FROM 
                `tabSalary Detail`
            WHERE 
                parent IN %s
                AND parentfield = 'deductions'
                AND salary_component IN (
                    'BPJS JHT Employee', 
                    'BPJS JP Employee', 
                    'BPJS Kesehatan Employee',
                    'PPh 21'
                )
        """, [slip_names], as_dict=1)
        
        # Process components
        for comp in components:
            if comp.salary_component == "PPh 21":
                result["pph21"] += flt(comp.amount)
            else:  # It's a BPJS component
                result["bpjs"] += flt(comp.amount)

        return result
        
    except Exception as e:
        frappe.log_error(
            f"Error calculating YTD totals for {employee}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "YTD Totals Error"
        )
        # Return empty result on error
        return {"gross": 0, "bpjs": 0, "pph21": 0}

def set_basic_payroll_note(doc, employee):
    """
    Set basic payroll note with component details
    
    Args:
        doc: Salary slip document
        employee: Employee document
    """
    try:
        # Check if payroll_note already has content
        if hasattr(doc, 'payroll_note') and doc.payroll_note:
            # Don't overwrite existing note, add to it
            return
            
        status_pajak = employee.status_pajak if hasattr(employee, 'status_pajak') and employee.status_pajak else "TK0"
        
        doc.payroll_note = "\n".join([
                        "<!-- BASIC_INFO_START -->",
            "=== Informasi Dasar ===",
            f"Status Pajak: {status_pajak}",
            f"Penghasilan Bruto: Rp {doc.gross_pay:,.0f}",
            f"Biaya Jabatan: Rp {doc.biaya_jabatan:,.0f}",
            f"BPJS (JHT+JP+Kesehatan): Rp {doc.total_bpjs:,.0f}",
            f"Penghasilan Neto: Rp {doc.netto:,.0f}",
            "<!-- BASIC_INFO_END -->"
        ])
    except Exception as e:
        frappe.log_error(
            f"Error setting basic payroll note for {doc.employee}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "Payroll Note Error"
        )
        # Just set a basic note
        doc.payroll_note = f"Penghasilan Bruto: Rp {doc.gross_pay:,.0f}"
        frappe.msgprint(_("Error setting detailed payroll note: {0}").format(str(e)))

def is_december(doc):
    """
    Check if salary slip is for December
    
    Args:
        doc: Salary slip document
        
    Returns:
        bool: True if the salary slip is for December
    """
    try:
        return getdate(doc.end_date).month == 12
    except Exception:
        # Default to False if there's an error
        return False