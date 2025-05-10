# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-10 14:00:00 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate, get_first_day, get_last_day, add_months, date_diff, cint
from datetime import datetime
from payroll_indonesia.payroll_indonesia.utils import get_ptkp_settings, get_spt_month

# Import necessary functions for TER mapping
from payroll_indonesia.override.salary_slip.ter_calculator import map_ptkp_to_ter_category

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
                ter_category = ""  # Add TER category tracking
                
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
                    
                # Get TER category if available
                if hasattr(slip_doc, 'ter_category'):
                    ter_category = slip_doc.ter_category
                
                # Store details for reporting
                slip_details.append({
                    "name": slip.name,
                    "date": slip.posting_date,
                    "gross": slip_gross,
                    "tax": tax_paid,
                    "using_ter": is_using_ter,
                    "ter_rate": ter_rate if is_using_ter else 0,
                    "ter_category": ter_category if is_using_ter else ""
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
        
        # Map PTKP status to TER category for reference
        ter_category = ""
        try:
            ter_category = map_ptkp_to_ter_category(status_pajak)
        except Exception:
            # Ignore errors in TER mapping, it's just for reference
            pass
        
        # Calculate PTKP (Annual non-taxable income)
        ptkp = calculate_ptkp(status_pajak)
        
        # Calculate PKP (taxable income)
        pkp = max(0, net_annual - ptkp)
        
        # Calculate progressive tax (Pasal 17)
        annual_tax, tax_details = calculate_progressive_tax(pkp)
        
        # Calculate correction needed
        correction = annual_tax - total_tax_paid
        
        # Return the results with TER category
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
            "tax_details": tax_details,
            "status_pajak": status_pajak,
            "ter_category": ter_category  # Add TER category to result
        }
        
    except Exception as e:
        frappe.log_error(
            f"Error in annual tax calculation for employee {employee}, year {tahun_pajak}: {str(e)}",
            "Annual Tax Calculation Error"
        )
        frappe.throw(_("Error in annual tax calculation: {0}").format(str(e)))

# ... rest of the code remains unchanged ...

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
            'pkp', 'tax_details', 'annual_tax', 'already_paid', 'correction', 'slip_details',
            'status_pajak', 'ter_category'  # Add new keys
        ]
        
        for key in required_keys:
            if key not in calc_result:
                frappe.log_error(
                    f"Missing key {key} in calculation result",
                    "December Note Generation Error"
                )
                # Initialize missing keys with 0 or empty string
                if key in ['tax_details', 'slip_details']:
                    calc_result[key] = []
                elif key in ['status_pajak', 'ter_category']:
                    calc_result[key] = ""
                else:
                    calc_result[key] = 0
        
        # Build the note
        note = [
            "=== Perhitungan PPh 21 Tahunan ===",
            f"Status Pajak: {calc_result['status_pajak']}" +
            (f" ({calc_result['ter_category']})" if calc_result['ter_category'] else ""),
            f"Penghasilan Bruto Setahun: Rp {flt(calc_result['annual_income']):,.0f}",
            f"Biaya Jabatan: Rp {flt(calc_result['biaya_jabatan']):,.0f}",
            f"Total BPJS: Rp {flt(calc_result['bpjs_total']):,.0f}",
            f"Penghasilan Neto: Rp {flt(calc_result['annual_net']):,.0f}",
            f"PTKP: Rp {flt(calc_result['ptkp']):,.0f}",
            f"PKP: Rp {flt(calc_result['pkp']):,.0f}",
            "",
            "Perhitungan Per Lapisan Pajak:"
        ]
        
        # ... rest of the function remains unchanged ...
        
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
                    ter_category = slip.get('ter_category', '')
                    
                    ter_info = f"Rate {ter_rate:.2f}%"
                    if ter_category:
                        ter_info = f"{ter_category}: {ter_info}"
                    
                    note.append(
                        f"- {slip_date}: {ter_info}, "
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