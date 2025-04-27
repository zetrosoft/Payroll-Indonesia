# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 02:25:18 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate, get_first_day, get_last_day, add_months, date_diff, cint
from datetime import datetime
from payroll_indonesia.payroll_indonesia.utils import get_ptkp_settings, get_spt_month

def hitung_pph_tahunan(employee, tahun_pajak):
    """
    Calculate annual progressive income tax (Pasal 17) for December correction
    with improved validation and error handling
    
    Args:
        employee (str): Employee ID
        tahun_pajak (int): Tax year
        
    Returns:
        dict: Annual tax calculation results
    """
    try:
        # Validate parameters
        if not employee:
            frappe.throw(_("Employee ID is required for annual tax calculation"))
            
        if not tahun_pajak:
            tahun_pajak = datetime.now().year
            frappe.msgprint(_("Tax year not specified, using current year ({0})").format(tahun_pajak))
        
        # Validate employee exists
        if not frappe.db.exists("Employee", employee):
            frappe.throw(_("Employee {0} not found").format(employee))
            
        # Get annual income from salary slips
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters={
                "employee": employee,
                "docstatus": 1,
                "posting_date": ["between", [f"{tahun_pajak}-01-01", f"{tahun_pajak}-12-31"]]
            },
            fields=["name", "gross_pay", "total_deduction", "posting_date"]
        )
        
        if not salary_slips:
            frappe.msgprint(
                _("No approved salary slips found for employee {0} in tax year {1}").format(
                    employee, tahun_pajak
                )
            )
            return {
                "annual_income": 0, 
                "annual_net": 0,
                "biaya_jabatan": 0,
                "bpjs_total": 0,
                "ptkp": 0,
                "pkp": 0,
                "annual_tax": 0, 
                "already_paid": 0, 
                "correction": 0,
                "slip_details": [],
                "tax_details": []
            }
        
        # Calculate totals and get slips data
        total_gross = 0
        total_deduction = 0
        total_tax_paid = 0
        slip_details = []
        
        for slip in salary_slips:
            try:
                slip_doc = frappe.get_doc("Salary Slip", slip.name)
                slip_gross = flt(slip.gross_pay)
                slip_deduction = flt(slip.total_deduction)
                
                # Validate data
                if slip_gross < 0:
                    frappe.log_error(
                        f"Negative gross pay {slip_gross} found in salary slip {slip.name}",
                        "Annual Calculation Error"
                    )
                    slip_gross = 0
                    
                total_gross += slip_gross
                total_deduction += slip_deduction
                
                # Get PPh 21 from deductions
                tax_paid = 0
                is_using_ter = 0
                ter_rate = 0
                
                # Check if deductions attribute exists
                if hasattr(slip_doc, 'deductions'):
                    for deduction in slip_doc.deductions:
                        if deduction.salary_component == "PPh 21":
                            tax_paid = flt(deduction.amount)
                            break
                else:
                    frappe.log_error(
                        f"Salary slip {slip.name} has no deductions attribute",
                        "Annual Calculation Error"
                    )
                            
                total_tax_paid += tax_paid
                
                # Get TER information if available
                if hasattr(slip_doc, 'is_using_ter'):
                    is_using_ter = cint(slip_doc.is_using_ter)
                
                if hasattr(slip_doc, 'ter_rate'):
                    ter_rate = flt(slip_doc.ter_rate)
                
                # Store details for reporting
                slip_details.append({
                    "name": slip.name,
                    "date": slip.posting_date,
                    "gross": slip_gross,
                    "tax": tax_paid,
                    "using_ter": is_using_ter,
                    "ter_rate": ter_rate if is_using_ter else 0
                })
            except Exception as e:
                frappe.log_error(
                    f"Error processing salary slip {slip.name}: {str(e)}",
                    "Annual Calculation Error"
                )
                continue
        
        # Get employee document
        try:
            employee_doc = frappe.get_doc("Employee", employee)
        except Exception as e:
            frappe.throw(_("Error retrieving employee information: {0}").format(str(e)))
        
        # Calculate biaya jabatan (job allowance) - max 6M per year
        biaya_jabatan = min(total_gross * 0.05, 6000000)
        
        # Calculate annual BPJS
        annual_bpjs = 0
        for slip in salary_slips:
            try:
                slip_doc = frappe.get_doc("Salary Slip", slip.name)
                bpjs_components = ["BPJS JHT Employee", "BPJS JP Employee", "BPJS Kesehatan Employee"]
                
                if hasattr(slip_doc, 'deductions'):
                    for component in bpjs_components:
                        for deduction in slip_doc.deductions:
                            if deduction.salary_component == component:
                                annual_bpjs += flt(deduction.amount)
                                break
            except Exception as e:
                frappe.log_error(
                    f"Error calculating BPJS for slip {slip.name}: {str(e)}",
                    "Annual BPJS Calculation Error"
                )
                continue
        
        # Get net annual - for annual calculation we need to deduct biaya jabatan and BPJS
        net_annual = total_gross - biaya_jabatan - annual_bpjs
        
        # Get employee details with validation
        status_pajak = "TK0"  # Default to TK0
        if hasattr(employee_doc, 'status_pajak') and employee_doc.status_pajak:
            status_pajak = employee_doc.status_pajak
        else:
            frappe.msgprint(_("Tax status not set for employee {0}, using default (TK0)").format(employee))
        
        # Calculate PTKP (Annual non-taxable income)
        ptkp = calculate_ptkp(status_pajak)
        
        # Calculate PKP (taxable income)
        pkp = max(0, net_annual - ptkp)
        
        # Calculate progressive tax (Pasal 17)
        annual_tax, tax_details = calculate_progressive_tax(pkp)
        
        # Calculate correction needed
        correction = annual_tax - total_tax_paid
        
        # Return the results
        return {
            "annual_income": total_gross,
            "annual_net": net_annual,
            "biaya_jabatan": biaya_jabatan,
            "bpjs_total": annual_bpjs,
            "ptkp": ptkp,
            "pkp": pkp,
            "annual_tax": annual_tax,
            "already_paid": total_tax_paid,
            "correction": correction,
            "slip_details": slip_details,
            "tax_details": tax_details
        }
        
    except Exception as e:
        frappe.log_error(
            f"Error in annual tax calculation for employee {employee}, year {tahun_pajak}: {str(e)}",
            "Annual Tax Calculation Error"
        )
        frappe.throw(_("Error in annual tax calculation: {0}").format(str(e)))
        
def calculate_ptkp(status_pajak):
    """
    Calculate PTKP based on tax status with error handling
    
    Args:
        status_pajak (str): Employee tax status (TK0, K0, etc.)
        
    Returns:
        float: PTKP amount
    """
    try:
        # Validate status_pajak
        if not status_pajak:
            status_pajak = "TK0"  # Default to TK0
            frappe.msgprint(_("Tax status not provided, using default (TK0)"))
        
        # Get PTKP settings with validation
        try:
            ptkp_settings = get_ptkp_settings()
            
            # Verify ptkp_settings is not empty
            if not ptkp_settings:
                frappe.log_error(
                    "Empty PTKP settings returned by get_ptkp_settings()",
                    "PTKP Calculation Error"
                )
                # Use default values
                ptkp_settings = {
                    'pribadi': 54000000,
                    'kawin': 4500000,
                    'anak': 4500000,
                    'hb_additional': 54000000
                }
                frappe.msgprint(_("Using default PTKP values due to missing settings"))
        except Exception as e:
            frappe.log_error(
                f"Error getting PTKP settings: {str(e)}",
                "PTKP Settings Error"
            )
            # Use default values
            ptkp_settings = {
                'pribadi': 54000000,
                'kawin': 4500000,
                'anak': 4500000,
                'hb_additional': 54000000
            }
            frappe.msgprint(_("Using default PTKP values due to error: {0}").format(str(e)))
        
        # Base PTKP
        base_ptkp = flt(ptkp_settings.get('pribadi', 54000000))
        
        # Extract status code and dependent count with validation
        try:
            # Verify status_pajak format (should be like 'TK0', 'K1', etc.)
            if len(status_pajak) < 2:
                frappe.msgprint(
                    _("Invalid tax status format: {0}, must be at least 2 characters long (e.g. TK0)").format(status_pajak)
                )
                return base_ptkp
                
            status_code = status_pajak[:-1]  # 'TK' from 'TK0'
            
            try:
                dependents = int(status_pajak[-1])
            except ValueError:
                frappe.log_error(
                    f"Invalid tax status format: {status_pajak}, last character must be a number",
                    "PTKP Calculation Error"
                )
                dependents = 0
        except Exception as e:
            frappe.log_error(
                f"Error parsing tax status {status_pajak}: {str(e)}",
                "PTKP Calculation Error"
            )
            status_code = "TK"
            dependents = 0
        
        # Calculate based on status
        if status_code == "TK":
            # TK0, TK1, TK2, TK3 - Unmarried
            return base_ptkp + (dependents * flt(ptkp_settings.get('anak', 4500000)))
            
        elif status_code == "K":
            # K0, K1, K2, K3 - Married
            # K adds for spouse plus dependents
            return (base_ptkp + 
                    flt(ptkp_settings.get('kawin', 4500000)) + 
                    (dependents * flt(ptkp_settings.get('anak', 4500000))))
                    
        elif status_code == "HB":
            # HB0, HB1, HB2, HB3 - "Penghasilan digabung suami/istri"
            # HB adds for spouse plus dependents plus additional for HB status
            return (base_ptkp + 
                    flt(ptkp_settings.get('kawin', 4500000)) + 
                    (dependents * flt(ptkp_settings.get('anak', 4500000))) +
                    flt(ptkp_settings.get('hb_additional', 54000000)))
        else:
            # Unrecognized status code
            frappe.log_error(
                f"Unrecognized tax status code: {status_code}",
                "PTKP Calculation Error"
            )
            frappe.msgprint(_("Unrecognized tax status: {0}, using basic PTKP").format(status_pajak))
            return base_ptkp
    
    except Exception as e:
        frappe.log_error(
            f"Error calculating PTKP for status {status_pajak}: {str(e)}",
            "PTKP Calculation Error"
        )
        # Return default PTKP to avoid breaking the calculation
        return 54000000

def calculate_progressive_tax(pkp):
    """
    Calculate progressive tax according to Article 17
    with improved error handling
    
    Args:
        pkp (float): Annual taxable income (PKP)
        
    Returns:
        tuple: (total_tax, tax_details)
    """
    try:
        # Validate input
        if pkp is None:
            frappe.throw(_("PKP cannot be None"))
            
        # Convert to float if needed
        pkp = flt(pkp)
        
        # Initialize result variables
        tax = 0
        tax_details = []
        
        # First check if PKP is positive
        if pkp <= 0:
            return 0, []
        
        # Get tax brackets from PPh 21 Settings if available
        try:
            pph_settings = frappe.get_single("PPh 21 Settings")
            brackets = []
            
            # Check if bracket_table exists and has records
            if hasattr(pph_settings, 'bracket_table') and pph_settings.bracket_table:
                for bracket in pph_settings.bracket_table:
                    brackets.append({
                        "income_from": flt(bracket.income_from),
                        "income_to": flt(bracket.income_to),
                        "tax_rate": flt(bracket.tax_rate)
                    })
                    
                # Sort brackets by income_from
                brackets.sort(key=lambda x: x["income_from"])
                
        except Exception as e:
            frappe.log_error(
                f"Error retrieving tax brackets from settings: {str(e)}",
                "Progressive Tax Error"
            )
            # Fall back to default brackets
            brackets = []
        
        # If brackets are empty or not found, use default progressive rates
        if not brackets:
            brackets = [
                {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
                {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
                {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
                {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
            ]
            frappe.msgprint(_("Using default progressive tax rates"))
        
        # Calculate tax by brackets
        remaining_pkp = pkp
        
        for bracket in brackets:
            if remaining_pkp <= 0:
                break
                
            income_from = flt(bracket["income_from"])
            income_to = flt(bracket["income_to"])
            tax_rate = flt(bracket["tax_rate"]) / 100  # Convert to decimal
            
            # Handle special case for highest bracket where income_to is 0
            if income_to == 0:
                income_to = float('inf')
                
            # Calculate taxable amount in this bracket
            taxable = min(remaining_pkp, income_to - income_from)
            
            # Avoid negative taxable amounts
            if taxable <= 0:
                continue
                
            # Calculate tax for this bracket
            bracket_tax = taxable * tax_rate
            tax += bracket_tax
            
            # Record tax detail
            tax_details.append({
                "rate": tax_rate * 100,  # Convert back to percentage for display
                "taxable": taxable,
                "tax": bracket_tax
            })
            
            # Reduce remaining PKP
            remaining_pkp -= taxable
        
        return tax, tax_details
        
    except Exception as e:
        frappe.log_error(
            f"Error calculating progressive tax for PKP {pkp}: {str(e)}",
            "Progressive Tax Error"
        )
        frappe.throw(_("Error calculating progressive tax: {0}").format(str(e)))

def generate_december_correction_note(calc_result):
    """
    Generate detailed note for December correction with improved validation
    
    Args:
        calc_result (dict): Result from hitung_pph_tahunan function
        
    Returns:
        str: Formatted note for December correction
    """
    try:
        # Validate input
        if not calc_result or not isinstance(calc_result, dict):
            frappe.throw(_("Invalid calculation result provided"))
            
        # Check required keys
        required_keys = [
            'annual_income', 'biaya_jabatan', 'bpjs_total', 'annual_net', 'ptkp',
            'pkp', 'tax_details', 'annual_tax', 'already_paid', 'correction', 'slip_details'
        ]
        
        for key in required_keys:
            if key not in calc_result:
                frappe.log_error(
                    f"Missing key {key} in calculation result",
                    "December Note Generation Error"
                )
                # Initialize missing keys with 0 to prevent errors
                calc_result[key] = 0 if key != 'tax_details' and key != 'slip_details' else []
        
        # Build the note
        note = [
            "=== Perhitungan PPh 21 Tahunan ===",
            f"Penghasilan Bruto Setahun: Rp {flt(calc_result['annual_income']):,.0f}",
            f"Biaya Jabatan: Rp {flt(calc_result['biaya_jabatan']):,.0f}",
            f"Total BPJS: Rp {flt(calc_result['bpjs_total']):,.0f}",
            f"Penghasilan Neto: Rp {flt(calc_result['annual_net']):,.0f}",
            f"PTKP: Rp {flt(calc_result['ptkp']):,.0f}",
            f"PKP: Rp {flt(calc_result['pkp']):,.0f}",
            "",
            "Perhitungan Per Lapisan Pajak:"
        ]
        
        # Add tax bracket details
        tax_details = calc_result['tax_details']
        if tax_details and isinstance(tax_details, list):
            for detail in tax_details:
                if not isinstance(detail, dict):
                    continue
                    
                rate = flt(detail.get('rate', 0))
                taxable = flt(detail.get('taxable', 0))
                tax = flt(detail.get('tax', 0))
                
                note.append(
                    f"- Lapisan {rate:.0f}%: "
                    f"Rp {taxable:,.0f} × {rate:.0f}% = "
                    f"Rp {tax:,.0f}"
                )
        else:
            note.append("- (Tidak ada rincian pajak)")
        
        # Add summary values
        annual_tax = flt(calc_result['annual_tax'])
        already_paid = flt(calc_result['already_paid'])
        correction = flt(calc_result['correction'])
        
        note.extend([
            "",
            f"Total PPh 21 Setahun: Rp {annual_tax:,.0f}",
            f"PPh 21 Sudah Dibayar: Rp {already_paid:,.0f}",
            f"Koreksi Desember: Rp {correction:,.0f}",
            f"({'Kurang Bayar' if correction > 0 else 'Lebih Bayar'})"
        ])
        
        # Add note about using progressive method for annual correction
        note.append("\nMetode perhitungan Desember menggunakan metode progresif sesuai PMK 168/2023")
        
        # Add details of slips using TER
        slip_details = calc_result['slip_details']
        if slip_details and isinstance(slip_details, list):
            # Filter slips that used TER
            ter_slips = [slip for slip in slip_details if slip.get('using_ter')]
            
            if ter_slips:
                note.append("\nRiwayat Perhitungan Dengan TER:")
                for slip in ter_slips:
                    slip_date = slip.get('date', '')
                    ter_rate = flt(slip.get('ter_rate', 0))
                    tax = flt(slip.get('tax', 0))
                    
                    note.append(
                        f"- {slip_date}: Rate {ter_rate:.2f}%, "
                        f"PPh 21: Rp {tax:,.0f}"
                    )
        
        return "\n".join(note)
        
    except Exception as e:
        frappe.log_error(
            f"Error generating December correction note: {str(e)}",
            "December Note Error"
        )
        # Return basic note to avoid breaking
        return "Error generating detailed note. Please check calculation results."