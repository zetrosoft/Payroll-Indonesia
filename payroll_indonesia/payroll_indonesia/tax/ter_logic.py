# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 08:55:02 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate, cint, now_datetime

# Import mapping function from pph_ter.py - the source of truth for TER calculations
from payroll_indonesia.payroll_indonesia.tax.pph_ter import map_ptkp_to_ter_category, get_ter_rate

def hitung_pph_tahunan(employee, year):
    """
    Calculate annual PPh 21 for an employee with support for both TER and progressive methods.
    This is called by both monthly and yearly tax processes.
    
    Args:
        employee: Employee ID
        year: Tax year
        
    Returns:
        dict: Tax calculation data
    """
    try:
        # Validate parameters
        if not employee:
            frappe.throw(
                _("Employee ID is required for annual PPh calculation"),
                title=_("Missing Parameter")
            )
            
        if not year:
            frappe.throw(
                _("Tax year is required for annual PPh calculation"),
                title=_("Missing Parameter")
            )
            
        # Get employee document
        try:
            emp_doc = frappe.get_doc("Employee", employee)
        except Exception as e:
            frappe.throw(
                _("Error retrieving employee {0}: {1}").format(employee, str(e)),
                title=_("Employee Not Found")
            )
        
        # Get all salary slips for the year
        salary_slips = frappe.db.get_all(
            "Salary Slip",
            filters={
                "employee": employee,
                "docstatus": 1,
                "start_date": ["between", [f"{year}-01-01", f"{year}-12-31"]]
            },
            fields=["name", "gross_pay", "total_bpjs", "start_date", "is_using_ter", "ter_rate", "ter_category"],
            order_by="start_date asc"
        )
        
        if not salary_slips:
            return {
                "annual_income": 0,
                "biaya_jabatan": 0,
                "bpjs_total": 0,
                "annual_net": 0,
                "ptkp": 0,
                "pkp": 0,
                "already_paid": 0,
                "annual_tax": 0,
                "ter_used": False
            }
            
        # Calculate annual totals
        annual_income = sum(flt(slip.gross_pay) for slip in salary_slips)
        bpjs_total = sum(flt(slip.total_bpjs) for slip in salary_slips)
        
        # Calculate biaya jabatan (job allowance)
        biaya_jabatan = min(annual_income * 0.05, 500000)  # 5% of annual income, max 500k
        
        # Calculate annual net income
        annual_net = annual_income - biaya_jabatan - bpjs_total
        
        # Get PTKP value based on employee's tax status
        ptkp = get_ptkp_amount(emp_doc.get("status_pajak", "TK0"))
        
        # Calculate PKP (taxable income)
        pkp = max(annual_net - ptkp, 0)
        
        # Check if TER was used in any month
        ter_used = any(getattr(slip, "is_using_ter", 0) for slip in salary_slips)
        
        # Calculate tax paid during the year
        already_paid = calculate_tax_already_paid(salary_slips)
        
        # Calculate annual tax using progressive method (always used for annual calculation)
        annual_tax, _ = calculate_progressive_tax(pkp)
        
        # Determine most common TER category if TER was used
        ter_categories = [slip.ter_category for slip in salary_slips 
                          if getattr(slip, "is_using_ter", 0) and getattr(slip, "ter_category", "")]
        
        ter_category = ""
        if ter_categories:
            # Get the most common category
            from collections import Counter
            category_counts = Counter(ter_categories)
            ter_category = category_counts.most_common(1)[0][0]
        
        return {
            "annual_income": annual_income,
            "biaya_jabatan": biaya_jabatan,
            "bpjs_total": bpjs_total,
            "annual_net": annual_net,
            "ptkp": ptkp,
            "pkp": pkp,
            "already_paid": already_paid,
            "annual_tax": annual_tax,
            "ter_used": ter_used,
            "ter_category": ter_category
        }
        
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # For other errors, log and re-raise with clear message
        frappe.log_error(
            "Error calculating annual PPh for {0}, year {1}: {2}".format(
                employee, year, str(e)
            ),
            "Annual PPh Calculation Error"
        )
        frappe.throw(
            _("Error calculating annual tax: {0}").format(str(e)),
            title=_("Tax Calculation Failed")
        )

def get_ptkp_amount(status_pajak):
    """
    Get PTKP amount based on tax status from PPh 21 Settings or defaults
    
    Args:
        status_pajak: Tax status code (e.g., 'TK0', 'K1', etc.)
        
    Returns:
        float: PTKP amount
    """
    try:
        # Validate input
        if not status_pajak:
            frappe.log_error(
                "Empty tax status provided, using TK0 as default",
                "PTKP Warning"
            )
            status_pajak = "TK0"
            
        # Check if PPh 21 Settings exists
        if frappe.db.exists("DocType", "PPh 21 Settings"):
            pph_settings = frappe.get_cached_doc("PPh 21 Settings")
            
            # Get PTKP from settings
            ptkp_table = getattr(pph_settings, 'ptkp_table', [])
            
            # If not found in cached doc, query from database
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
        
        # Default values if not found or settings don't exist
        default_ptkp = {
            "TK": 54000000,  # TK/0
            "K": 58500000,   # K/0
            "HB": 112500000  # HB/0
        }
        
        # Return default based on prefix
        prefix = status_pajak[:2] if len(status_pajak) >= 2 else status_pajak
        for key, value in default_ptkp.items():
            if prefix.startswith(key):
                frappe.log_error(
                    "PTKP not found in settings for {0}, using default value {1}".format(
                        status_pajak, value
                    ),
                    "PTKP Fallback Warning"
                )
                return value
                
        # Last resort - TK0
        frappe.log_error(
            "No PTKP match found for {0}, using TK0 default (54,000,000)".format(status_pajak),
            "PTKP Default Warning"
        )
        return 54000000  # Default for TK0
    
    except Exception as e:
        # Non-critical error - log and return default
        frappe.log_error(
            "Error getting PTKP amount for {0}: {1}".format(status_pajak, str(e)),
            "PTKP Calculation Error"
        )
        frappe.msgprint(
            _("Error retrieving PTKP value for tax status {0}. Using default.").format(status_pajak),
            indicator="orange"
        )
        # Return default PTKP for TK0
        return 54000000

def calculate_tax_already_paid(salary_slips):
    """
    Calculate total tax already paid in the given salary slips
    
    Args:
        salary_slips: List of salary slips
        
    Returns:
        float: Total tax already paid
    """
    # Initialize total
    total_tax = 0
    
    try:
        # Get slip names for efficient querying
        slip_names = [slip.name for slip in salary_slips]
        
        if not slip_names:
            return 0
            
        # Get PPh 21 component amounts in bulk
        tax_components = frappe.db.sql("""
            SELECT parent, amount
            FROM `tabSalary Detail`
            WHERE 
                parent IN %s
                AND parentfield = 'deductions'
                AND salary_component = 'PPh 21'
        """, [slip_names], as_dict=1)
        
        # Sum up tax amounts
        for comp in tax_components:
            total_tax += flt(comp.amount)
            
    except Exception as e:
        # Non-critical error - log, show warning and return 0
        frappe.log_error(
            "Error calculating already paid tax: {0}".format(str(e)),
            "Tax Calculation Warning"
        )
        frappe.msgprint(
            _("Error retrieving previously paid tax amounts. Using 0 as fallback."),
            indicator="orange"
        )
    
    return total_tax

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
        # Validate input
        if pkp < 0:
            frappe.log_error(
                "Negative PKP value {0} provided, using 0 instead".format(pkp),
                "PKP Validation Warning"
            )
            pkp = 0

        # Get settings
        if not pph_settings and frappe.db.exists("DocType", "PPh 21 Settings"):
            try:
                pph_settings = frappe.get_cached_doc("PPh 21 Settings")
            except Exception as settings_error:
                frappe.log_error(
                    "Error retrieving PPh 21 Settings: {0}".format(str(settings_error)),
                    "Settings Retrieval Warning"
                )
                pph_settings = None

        # First check if bracket_table is directly available as attribute
        bracket_table = []
        if pph_settings and hasattr(pph_settings, 'bracket_table'):
            bracket_table = pph_settings.bracket_table
            
        # If not found or empty, query from database
        if not bracket_table and pph_settings:
            bracket_table = frappe.db.sql("""
                SELECT income_from, income_to, tax_rate
                FROM `tabPPh 21 Tax Bracket`
                WHERE parent = 'PPh 21 Settings'
                ORDER BY income_from ASC
            """, as_dict=1)

        # If still not found, use default values
        if not bracket_table:
            # Log warning about missing brackets
            frappe.log_error(
                "No tax brackets found in settings, using default values",
                "Tax Bracket Warning"
            )
            
            # Default bracket values if not found - based on PMK 101/2016 and UU HPP 2021
            bracket_table = [
                {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
                {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
                {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
                {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
            ]

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
        # Non-critical error - log and return default values
        frappe.log_error(
            "Error calculating progressive tax for PKP {0}: {1}".format(pkp, str(e)),
            "Tax Bracket Calculation Error"
        )
        frappe.msgprint(
            _("Error calculating tax using progressive rates. Please check the error log."),
            indicator="orange"
        )
        return 0, []