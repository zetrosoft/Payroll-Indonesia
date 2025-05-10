# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-10 11:30:00 by dannyaudian

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

# Cache for YTD calculations to improve performance
_YTD_CACHE = {}
_YTD_CACHE_EXPIRY = now_datetime()

def calculate_tax_components(doc, employee):
    """
    Calculate tax related components for salary slip
    
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

        # Calculate PPh 21 - December always uses progressive method as per PMK 168/2023
        if is_december(doc):
            # Force disable TER for December according to PMK 168/2023
            doc.is_using_ter = 0
            calculate_december_pph(doc, employee)
        else:
            # Regular month - calculation method is determined by salary_slip.py controller
            # This function just calculates using progressive method
            calculate_monthly_pph_progressive(doc, employee)
    
    except Exception as e:
        frappe.log_error(
            f"Tax Calculation Error for Employee {employee.name}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "Tax Calculation Error"
        )
        # Convert to user-friendly error
        frappe.throw(_("Error calculating tax components: {0}").format(str(e)))

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

        # For December, always use progressive method even if TER is enabled (PMK 168/2023)
        # Get year-to-date totals from tax summary with improved caching
        ytd = get_ytd_totals_from_tax_summary(doc, year)

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

def get_ytd_totals_from_tax_summary(doc, year):
    """
    Get YTD data from Employee Tax Summary with caching for performance
    
    Args:
        doc: Salary slip document
        year: The tax year
        
    Returns:
        dict: A dictionary with YTD values
    """
    global _YTD_CACHE, _YTD_CACHE_EXPIRY
    
    # Check if cache needs clearing (every hour)
    now = now_datetime()
    if (now - _YTD_CACHE_EXPIRY).total_seconds() > 3600:  # 1 hour
        _YTD_CACHE = {}
        _YTD_CACHE_EXPIRY = now
    
    # Create a cache key
    cache_key = f"{doc.employee}:{year}:{getdate(doc.start_date).month}"
    
    # Check cache first
    if cache_key in _YTD_CACHE:
        return _YTD_CACHE[cache_key]
    
    # Default result
    result = {"gross": 0, "bpjs": 0, "pph21": 0}
    
    try:
        # Validate year
        if not year or not isinstance(year, int):
            year = getdate(doc.end_date).year

        # Check if Employee Tax Summary DocType exists
        if not frappe.db.exists("DocType", "Employee Tax Summary"):
            frappe.msgprint(_("Employee Tax Summary DocType not found, using traditional YTD calculation"))
            return get_ytd_totals(doc, year)
            
        # Get Employee Tax Summary
        tax_summary = frappe.db.get_value(
            "Employee Tax Summary",
            {"employee": doc.employee, "year": year},
            ["name"], 
            cache=True
        )
        
        if tax_summary:
            # Get the full document
            try:
                tax_doc = frappe.get_doc("Employee Tax Summary", tax_summary)
            except Exception as e:
                frappe.log_error(
                    f"Error retrieving Employee Tax Summary {tax_summary}: {str(e)}",
                    "Tax Summary Retrieval Error"
                )
                return get_ytd_totals(doc, year)
            
            # Get current month
            current_month = getdate(doc.start_date).month
            
            # Calculate totals from monthly details
            if hasattr(tax_doc, 'monthly_details') and tax_doc.monthly_details:
                for monthly in tax_doc.monthly_details:
                    if hasattr(monthly, 'month') and monthly.month < current_month:
                        result["gross"] += flt(monthly.gross_pay if hasattr(monthly, 'gross_pay') else 0)
                        result["bpjs"] += flt(monthly.bpjs_deductions if hasattr(monthly, 'bpjs_deductions') else 0)
                        result["pph21"] += flt(monthly.tax_amount if hasattr(monthly, 'tax_amount') else 0)
                
                # Cache the result
                _YTD_CACHE[cache_key] = result
                return result
            else:
                frappe.msgprint(_("No monthly details found in Tax Summary, using traditional YTD calculation"))
    
    except Exception as e:
        frappe.log_error(
            f"Error getting YTD data from tax summary for {doc.employee}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}", 
            "YTD Tax Calculation Error"
        )
        frappe.msgprint(_("Error retrieving tax summary data: {0}").format(str(e)))
        
    # Fall back to traditional method if tax summary not found or error occurs
    result = get_ytd_totals(doc, year)
    _YTD_CACHE[cache_key] = result
    return result

def get_ytd_totals(doc, year):
    """
    Get year-to-date totals for the employee (legacy method)
    
    Args:
        doc: Salary slip document
        year: The tax year
        
    Returns:
        dict: A dictionary with YTD values
    """
    try:
        # Create a default result with zeros
        result = {"gross": 0, "bpjs": 0, "pph21": 0}
        
        # Validate year
        if not year or not isinstance(year, int):
            year = getdate(doc.end_date).year
            
        # Validate employee
        if not doc.employee:
            return result

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
                    AND start_date < %s
                    AND docstatus = 1
            """, (doc.employee, year, doc.start_date), as_dict=1)
        except Exception as e:
            frappe.log_error(
                f"Error querying salary slips for {doc.employee}: {str(e)}",
                "Salary Slip Query Error"
            )
            return result

        # Sum up the values
        for slip in salary_slips:
            try:
                # Add to gross
                result["gross"] += flt(slip.gross_pay)
                
                # Get BPJS and PPh 21 components in a more efficient way
                components = frappe.db.sql("""
                    SELECT 
                        salary_component,
                        amount
                    FROM 
                        `tabSalary Detail`
                    WHERE 
                        parent = %s
                        AND parentfield = 'deductions'
                        AND salary_component IN ('BPJS JHT Employee', 'BPJS JP Employee', 'BPJS Kesehatan Employee', 'PPh 21')
                """, slip.name, as_dict=1)
                
                for comp in components:
                    if comp.salary_component == "PPh 21":
                        result["pph21"] += flt(comp.amount)
                    else:
                        result["bpjs"] += flt(comp.amount)
                        
            except Exception as e:
                frappe.log_error(
                    f"Error processing Salary Slip {slip.name}: {str(e)}",
                    "Salary Slip Processing Error"
                )
                continue

        return result
        
    except Exception as e:
        frappe.log_error(
            f"Error calculating YTD totals for {doc.employee}: {str(e)}\n"
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

def clear_cache():
    """
    Clear all caches used by tax calculation functions
    This can be called manually or via scheduler
    """
    global _YTD_CACHE, _YTD_CACHE_EXPIRY
    _YTD_CACHE = {}
    _YTD_CACHE_EXPIRY = now_datetime()
    frappe.cache().delete_key('tax_calculator_cache')