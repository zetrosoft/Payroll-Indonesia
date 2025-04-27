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
            calculate_monthly_pph(doc, employee)

    except Exception as e:
        frappe.log_error(
            f"Tax Calculation Error for Employee {employee.name}: {str(e)}",
            "Tax Calculation Error"
        )
        # Convert to user-friendly error
        frappe.throw(_("Error calculating tax components: {0}").format(str(e)))

def calculate_monthly_pph(doc, employee):
    """Calculate PPh 21 for regular months"""
    try:
        # Get PPh 21 Settings with validation
        try:
            pph_settings = frappe.get_single("PPh 21 Settings")
        except Exception as e:
            frappe.throw(_("Error retrieving PPh 21 Settings: {0}. Please configure PPh 21 Settings properly.").format(str(e)))
        
        # Check if calculation_method and use_ter fields exist
        if not hasattr(pph_settings, 'calculation_method'):
            frappe.msgprint(_("PPh 21 Settings missing calculation_method, defaulting to Progressive"))
            pph_settings.calculation_method = "Progressive"
            
        if not hasattr(pph_settings, 'use_ter'):
            frappe.msgprint(_("PPh 21 Settings missing use_ter, defaulting to No"))
            pph_settings.use_ter = 0

        # Check if TER method is enabled
        if pph_settings.calculation_method == "TER" and pph_settings.use_ter:
            calculate_monthly_pph_with_ter(doc, employee)
        else:
            calculate_monthly_pph_progressive(doc, employee)
            
    except Exception as e:
        frappe.log_error(
            f"Monthly PPh Calculation Error for Employee {employee.name}: {str(e)}",
            "PPh Calculation Error"
        )
        # Convert to user-friendly error
        frappe.throw(_("Error calculating monthly PPh 21: {0}").format(str(e)))

def calculate_monthly_pph_progressive(doc, employee):
    """Calculate PPh 21 using progressive method"""
    try:
        # Get PPh 21 Settings
        try:
            pph_settings = frappe.get_single("PPh 21 Settings")
        except Exception as e:
            frappe.throw(_("Error retrieving PPh 21 Settings: {0}. Please configure PPh 21 Settings properly.").format(str(e)))

        # Get PTKP value
        if not hasattr(employee, 'status_pajak') or not employee.status_pajak:
            employee.status_pajak = "TK0"  # Default to TK0 if not set
            frappe.msgprint(_("Warning: Employee tax status not set, using TK0 as default"))

        ptkp = get_ptkp_amount(pph_settings, employee.status_pajak)

        # Annualize monthly netto
        annual_netto = doc.netto * 12

        # Calculate PKP
        pkp = max(annual_netto - ptkp, 0)

        # Calculate annual tax
        annual_tax, tax_details = calculate_progressive_tax(pkp, pph_settings)

        # Get monthly tax (1/12 of annual)
        monthly_tax = annual_tax / 12

        # Update PPh 21 component
        update_component_amount(doc, "PPh 21", monthly_tax, "deductions")

        # Update note with tax info
        doc.payroll_note += f"\n\n=== Perhitungan PPh 21 Progresif ==="
        doc.payroll_note += f"\nPenghasilan Neto Setahun: Rp {annual_netto:,.0f}"
        doc.payroll_note += f"\nPTKP ({employee.status_pajak}): Rp {ptkp:,.0f}"
        doc.payroll_note += f"\nPKP: Rp {pkp:,.0f}"

        # Add tax calculation details
        if tax_details:
            doc.payroll_note += f"\n\nPerhitungan Pajak:"
            for detail in tax_details:
                doc.payroll_note += f"\n- {detail['rate']}% x Rp {detail['taxable']:,.0f} = Rp {detail['tax']:,.0f}"

        doc.payroll_note += f"\n\nPPh 21 Setahun: Rp {annual_tax:,.0f}"
        doc.payroll_note += f"\nPPh 21 Sebulan: Rp {monthly_tax:,.0f}"
        
    except Exception as e:
        frappe.log_error(
            f"Progressive Tax Calculation Error for Employee {employee.name}: {str(e)}",
            "Progressive Tax Error"
        )
        frappe.throw(_("Error calculating progressive tax: {0}").format(str(e)))

def get_ptkp_amount(pph_settings, status_pajak):
    """Get PTKP amount for a given tax status"""
    try:
        # Validate inputs
        if not status_pajak:
            status_pajak = "TK0"
            frappe.msgprint(_("Tax status not provided, using TK0 as default"))
        
        # Attempt to get from method if it exists
        if hasattr(pph_settings, 'get_ptkp_amount'):
            return pph_settings.get_ptkp_amount(status_pajak)

        # Otherwise query directly from PTKP table
        ptkp = frappe.db.sql("""
            SELECT ptkp_amount
            FROM `tabPPh 21 PTKP`
            WHERE status_pajak = %s
            AND parent = 'PPh 21 Settings'
            LIMIT 1
        """, status_pajak, as_dict=1)

        if not ptkp:
            # Default PTKP values if not found
            default_ptkp = {
                "TK0": 54000000, "K0": 58500000, "K1": 63000000,
                "K2": 67500000, "K3": 72000000, "TK1": 58500000,
                "TK2": 63000000, "TK3": 67500000
            }
            frappe.msgprint(_(
                "PTKP for status {0} not found in settings, using default value."
            ).format(status_pajak))
            
            # If we don't have a default for this status, use TK0
            if status_pajak not in default_ptkp:
                frappe.msgprint(_("No default PTKP for status {0}, using TK0 value.").format(status_pajak))
                return default_ptkp["TK0"]
                
            return default_ptkp.get(status_pajak)

        return flt(ptkp[0].ptkp_amount)
        
    except Exception as e:
        frappe.log_error(
            f"Error getting PTKP for status {status_pajak}: {str(e)}",
            "PTKP Retrieval Error"
        )
        frappe.throw(_("Error retrieving PTKP amount: {0}").format(str(e)))

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