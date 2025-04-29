# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 07:35:26 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate, cint

from .base import update_component_amount, get_component_amount
from .ter_calculator import calculate_monthly_pph_with_ter, get_ter_rate

def calculate_tax_components(doc, employee):
    """Calculate tax related components"""
    try:
        # Handle NPWP Gabung Suami case
        if hasattr(employee, 'gender') and employee.gender == "Female" and hasattr(employee, 'npwp_gabung_suami') and cint(employee.get("npwp_gabung_suami")):
            doc.is_final_gabung_suami = 1
            doc.payroll_note = "Pajak final digabung dengan NPWP suami"
            return

        # Calculate Biaya Jabatan (5% of gross, max 500k)
        doc.biaya_jabatan = min(doc.gross_pay * 0.05, 500000)

        # Calculate netto income
        doc.netto = doc.gross_pay - doc.biaya_jabatan - doc.total_bpjs

        # Set basic payroll note
        set_basic_payroll_note(doc, employee)

        # Calculate PPh 21
        if is_december(doc):
            calculate_december_pph(doc, employee)
        else:
            # IMPROVED: Strategy selection is already done in the controller
            # This function just handles the calculation based on the month
            check_and_apply_selected_method(doc, employee)

        # Initialize total_bpjs to 0 if None to prevent NoneType subtraction error
        if doc.total_bpjs is None:
            doc.total_bpjs = 0
    
        # Now the subtraction will work without errors
        doc.netto = doc.gross_pay - doc.biaya_jabatan - doc.total_bpjs
    
    except Exception as e:
        frappe.log_error(
            f"Tax Calculation Error for Employee {employee.name}: {str(e)}",
            "Tax Calculation Error"
        )
        # Convert to user-friendly error
        frappe.throw(_("Error calculating tax components: {0}").format(str(e)))

def check_and_apply_selected_method(doc, employee):
    """
    Check which method has been selected (TER attribute already set)
    and perform any necessary adjustments
    """
    # The actual tax calculation is now handled in controller by the selected strategy
    # This function only does method-specific post-processing if needed
    pass

def calculate_monthly_pph_with_ter(doc, employee):
    """Calculate PPh 21 using TER method"""
    try:
        # Validate employee status_pajak
        if not hasattr(employee, 'status_pajak') or not employee.status_pajak:
            employee.status_pajak = "TK0"  # Default to TK0 if not set
            frappe.msgprint(_("Warning: Employee tax status not set, using TK0 as default"))

        # Get TER rate based on status and gross income
        ter_rate = get_ter_rate(employee.status_pajak, doc.gross_pay)

        # Calculate tax using TER
        monthly_tax = doc.gross_pay * ter_rate

        # Save TER info
        doc.is_using_ter = 1
        doc.ter_rate = ter_rate * 100  # Convert to percentage for display

        # Update PPh 21 component
        update_component_amount(doc, "PPh 21", monthly_tax, "deductions")

        # Update note with TER info
        doc.payroll_note += "\n\n=== Perhitungan PPh 21 dengan TER ==="
        doc.payroll_note += f"\nStatus Pajak: {employee.status_pajak}"
        doc.payroll_note += f"\nPenghasilan Bruto: Rp {doc.gross_pay:,.0f}"
        doc.payroll_note += f"\nTarif Efektif Rata-rata: {ter_rate * 100:.2f}%"
        doc.payroll_note += f"\nPPh 21 Sebulan: Rp {monthly_tax:,.0f}"
        doc.payroll_note += "\n\nSesuai PMK 168/2023 tentang Tarif Efektif Rata-rata"

    except Exception as e:
        frappe.log_error(
            f"TER Calculation Error for Employee {employee.name}: {str(e)}",
            "TER Calculation Error"
        )
        frappe.throw(_("Error calculating PPh 21 with TER: {0}").format(str(e)))
        
def calculate_december_pph(doc, employee):
    """Calculate year-end tax correction for December"""
    try:
        year = getdate(doc.end_date).year

        # Get PPh 21 Settings
        try:
            pph_settings = frappe.get_single("PPh 21 Settings")
        except Exception as e:
            frappe.throw(_("Error retrieving PPh 21 Settings: {0}. Please configure PPh 21 Settings properly.").format(str(e)))

        # For December, always use progressive method even if TER is enabled
        # This is according to PMK 168/2023

        # Get year-to-date totals from tax summary instead of recalculating
        ytd = get_ytd_totals_from_tax_summary(doc, year)

        # Calculate annual totals
        annual_gross = ytd.get("gross", 0) + doc.gross_pay
        annual_bpjs = ytd.get("bpjs", 0) + doc.total_bpjs
        annual_biaya_jabatan = min(annual_gross * 0.05, 500000)
        annual_netto = annual_gross - annual_bpjs - annual_biaya_jabatan

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

        # Set detailed December note
        set_december_note(
            doc,
            annual_gross=annual_gross,
            annual_biaya_jabatan=annual_biaya_jabatan,
            annual_bpjs=annual_bpjs,
            annual_netto=annual_netto,
            ptkp=ptkp,
            pkp=pkp,
            tax_details=tax_details,
            annual_pph=annual_pph,
            ytd_pph=ytd.get("pph21", 0),
            correction=correction
        )
        
    except Exception as e:
        frappe.log_error(
            f"December PPh Calculation Error for Employee {employee.name}: {str(e)}",
            "December PPh Error"
        )
        frappe.throw(_("Error calculating December PPh 21 correction: {0}").format(str(e)))

def calculate_progressive_tax(pkp, pph_settings=None):
    """Calculate tax using progressive rates"""
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
            # Default bracket values if not found
            bracket_table = [
                {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
                {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
                {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
                {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
            ]
            frappe.msgprint(_("Tax brackets not configured, using default progressive rates."))

        # Calculate tax
        total_tax = 0
        tax_details = []
        remaining_pkp = pkp

        for bracket in sorted(bracket_table, key=lambda x: flt(x.get("income_from", 0))):
            if remaining_pkp <= 0:
                break

            income_from = flt(bracket.get("income_from", 0))
            income_to = flt(bracket.get("income_to", 0))
            tax_rate = flt(bracket.get("tax_rate", 0))

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
            f"Progressive Tax Calculation Error for PKP {pkp}: {str(e)}",
            "Tax Bracket Calculation Error"
        )
        frappe.throw(_("Error calculating progressive tax brackets: {0}").format(str(e)))

def get_ytd_totals_from_tax_summary(doc, year):
    """
    Get YTD data from Employee Tax Summary instead of recalculating from salary slips
    
    Args:
        year: The tax year
        
    Returns:
        dict: A dictionary with YTD values
    """
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
            ["name"]
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
                
                return result
            else:
                frappe.msgprint(_("No monthly details found in Tax Summary, using traditional YTD calculation"))
    
    except Exception as e:
        frappe.log_error(
            f"Error getting YTD data from tax summary for {doc.employee}: {str(e)}", 
            "YTD Tax Calculation Error"
        )
        frappe.msgprint(_("Error retrieving tax summary data: {0}").format(str(e)))
        
    # Fall back to traditional method if tax summary not found or error occurs
    return get_ytd_totals(doc, year)

def get_ytd_totals(doc, year):
    """Get year-to-date totals for the employee (legacy method)"""
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
        # but before the current month
        try:
            salary_slips = frappe.get_all(
                "Salary Slip",
                filters={
                    "employee": doc.employee,
                    "start_date": [">=", f"{year}-01-01"],
                    "end_date": ["<", doc.start_date],
                    "docstatus": 1
                },
                fields=["name", "gross_pay", "total_deduction"]
            )
        except Exception as e:
            frappe.log_error(
                f"Error querying salary slips for {doc.employee}: {str(e)}",
                "Salary Slip Query Error"
            )
            return result

        # Sum up the values
        for slip in salary_slips:
            try:
                slip_doc = frappe.get_doc("Salary Slip", slip.name)
            except Exception as e:
                frappe.log_error(
                    f"Error retrieving Salary Slip {slip.name}: {str(e)}",
                    "Salary Slip Retrieval Error"
                )
                continue

            # Add to gross
            result["gross"] += flt(slip_doc.gross_pay)

            # Add BPJS components
            bpjs_components = ["BPJS JHT Employee", "BPJS JP Employee", "BPJS Kesehatan Employee"]
            for component in bpjs_components:
                result["bpjs"] += get_component_amount(slip_doc, component, "deductions")

            # Add PPh 21
            result["pph21"] += get_component_amount(slip_doc, "PPh 21", "deductions")

        return result
        
    except Exception as e:
        frappe.log_error(
            f"Error calculating YTD totals for {doc.employee}: {str(e)}",
            "YTD Totals Error"
        )
        # Return empty result on error
        return {"gross": 0, "bpjs": 0, "pph21": 0}

def set_basic_payroll_note(doc, employee):
    """Set basic payroll note with component details"""
    try:
        status_pajak = employee.status_pajak if hasattr(employee, 'status_pajak') and employee.status_pajak else "TK0"
        
        doc.payroll_note = "\n".join([
            f"Status Pajak: {status_pajak}",
            f"Penghasilan Bruto: Rp {doc.gross_pay:,.0f}",
            f"Biaya Jabatan: Rp {doc.biaya_jabatan:,.0f}",
            f"BPJS (JHT+JP+Kesehatan): Rp {doc.total_bpjs:,.0f}",
            f"Penghasilan Neto: Rp {doc.netto:,.0f}"
        ])
    except Exception as e:
        frappe.log_error(
            f"Error setting basic payroll note for {doc.employee}: {str(e)}",
            "Payroll Note Error"
        )
        # Just set a basic note
        doc.payroll_note = f"Penghasilan Bruto: Rp {doc.gross_pay:,.0f}"
        frappe.msgprint(_("Error setting detailed payroll note: {0}").format(str(e)))

def set_december_note(doc, **kwargs):
    """Set detailed December correction note"""
    try:
        # Build the note with proper error handling
        note_parts = [
            "=== Perhitungan PPh 21 Tahunan ===",
            f"Penghasilan Bruto Setahun: Rp {kwargs.get('annual_gross', 0):,.0f}",
            f"Biaya Jabatan: Rp {kwargs.get('annual_biaya_jabatan', 0):,.0f}",
            f"Total BPJS: Rp {kwargs.get('annual_bpjs', 0):,.0f}",
            f"Penghasilan Neto: Rp {kwargs.get('annual_netto', 0):,.0f}",
            f"PTKP: Rp {kwargs.get('ptkp', 0):,.0f}",
            f"PKP: Rp {kwargs.get('pkp', 0):,.0f}",
            "",
            "Perhitungan Per Lapisan Pajak:"
        ]
        
        # Add tax bracket details if available
        tax_details = kwargs.get('tax_details', [])
        if tax_details:
            for d in tax_details:
                rate = flt(d.get('rate', 0))
                taxable = flt(d.get('taxable', 0))
                tax = flt(d.get('tax', 0))
                note_parts.append(
                    f"- Lapisan {rate:.0f}%: "
                    f"Rp {taxable:,.0f} × {rate:.0f}% = "
                    f"Rp {tax:,.0f}"
                )
        else:
            note_parts.append("- (Tidak ada rincian pajak)")
            
        # Add summary values
        annual_pph = flt(kwargs.get('annual_pph', 0))
        ytd_pph = flt(kwargs.get('ytd_pph', 0))
        correction = flt(kwargs.get('correction', 0))
        
        note_parts.extend([
            "",
            f"Total PPh 21 Setahun: Rp {annual_pph:,.0f}",
            f"PPh 21 Sudah Dibayar: Rp {ytd_pph:,.0f}",
            f"Koreksi Desember: Rp {correction:,.0f}",
            f"({'Kurang Bayar' if correction > 0 else 'Lebih Bayar'})"
        ])

        # Add note about using progressive method for annual correction
        note_parts.append("\n\nMetode perhitungan Desember menggunakan metode progresif sesuai PMK 168/2023")
        
        # Set the note
        doc.payroll_note = "\n".join(note_parts)
        
    except Exception as e:
        frappe.log_error(
            f"Error setting December payroll note for {doc.employee}: {str(e)}",
            "December Note Error"
        )
        # Set a basic note
        doc.payroll_note = "Perhitungan koreksi PPh 21 tahunan"
        frappe.msgprint(_("Error setting detailed December note: {0}").format(str(e)))

def is_december(doc):
    """Check if salary slip is for December"""
    try:
        return getdate(doc.end_date).month == 12
    except Exception:
        # Default to False if there's an error
        return False