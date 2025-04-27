# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 08:00:05 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate, cint

from .base import update_component_amount

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

def get_ter_rate(status_pajak, income):
    """Get TER rate based on status and income"""
    try:
        # Validate inputs
        if not status_pajak:
            status_pajak = "TK0"
            frappe.msgprint(_("Tax status not provided, using TK0 as default"))
            
        if not income or income <= 0:
            frappe.throw(_("Income must be greater than zero for TER calculation"))
            
        # Query the TER table for matching bracket
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
            frappe.msgprint(_(
                "No TER rate found for status {0} and income {1}, falling back to {2}."
            ).format(status_pajak, frappe.format(income, {"fieldtype": "Currency"}), status_fallback))

            ter = frappe.db.sql("""
                SELECT rate
                FROM `tabPPh 21 TER Table`
                WHERE status_pajak = %s
                  AND %s >= income_from
                  AND (%s <= income_to OR income_to = 0)
                LIMIT 1
            """, (status_fallback, income, income), as_dict=1)

            if not ter:
                # As a last resort, use default rate if defined in settings
                try:
                    pph_settings = frappe.get_single("PPh 21 Settings")
                    if hasattr(pph_settings, 'default_ter_rate'):
                        default_rate = flt(pph_settings.default_ter_rate)
                        frappe.msgprint(_(
                            "No TER rate found for status {0} or {1} and income {2}. "
                            "Using default rate of {3}%."
                        ).format(status_pajak, status_fallback, 
                                frappe.format(income, {"fieldtype": "Currency"}),
                                default_rate))
                        return default_rate / 100.0
                except Exception:
                    pass
                    
                # If we get here, we have no rate to use
                frappe.throw(_(
                    "No TER rate found for status {0} or {1} and income {2}. "
                    "Please check PPh 21 TER Table settings."
                ).format(status_pajak, status_fallback,
                        frappe.format(income, {"fieldtype": "Currency"})))

        # Convert percent to decimal (e.g., 5% to 0.05)
        return float(ter[0].rate) / 100.0
        
    except Exception as e:
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
        frappe.log_error(
            f"Error getting TER rate for status {status_pajak} and income {income}: {str(e)}",
            "TER Rate Error"
        )
        frappe.throw(_("Error retrieving TER rate: {0}").format(str(e)))

def should_use_ter_method(employee, pph_settings=None):
    """Determine if TER method should be used for this employee"""
    try:
        # Get PPh 21 Settings if not provided
        if not pph_settings:
            try:
                pph_settings = frappe.get_single("PPh 21 Settings")
            except Exception as e:
                frappe.throw(_("Error retrieving PPh 21 Settings: {0}").format(str(e)))
        
        # Check if calculation_method and use_ter fields exist
        if not hasattr(pph_settings, 'calculation_method'):
            return False
            
        if not hasattr(pph_settings, 'use_ter'):
            return False
            
        # Check if global TER setting is enabled
        if pph_settings.calculation_method != "TER" or not pph_settings.use_ter:
            return False
            
        # Check if employee is eligible for TER
        # For example, we might exclude certain employee types
        if hasattr(employee, 'tipe_karyawan') and employee.tipe_karyawan == "Freelance":
            return False
            
        # Check if employee has specific tax override setting
        if hasattr(employee, 'override_tax_method') and employee.override_tax_method == "Progressive":
            return False
            
        # If we made it here, use TER method
        return True
            
    except Exception as e:
        frappe.log_error(
            f"Error determining TER eligibility for employee {employee.name}: {str(e)}",
            "TER Eligibility Error"
        )
        # Default to False on error
        return False

def get_ter_settings():
    """Get TER table settings"""
    try:
        # Try to get active TER table
        ter_table_settings = frappe.get_all(
            "PPh 21 TER Settings",
            filters={"is_active": 1},
            fields=["name", "effective_date", "description"],
            order_by="effective_date desc",
            limit=1
        )
        
        if not ter_table_settings:
            frappe.msgprint(_("No active TER settings found. Using default system table."))
            return None
            
        # Return the settings object
        try:
            return frappe.get_doc("PPh 21 TER Settings", ter_table_settings[0].name)
        except Exception as e:
            frappe.log_error(
                f"Error getting TER settings: {str(e)}",
                "TER Settings Error"
            )
            return None
            
    except Exception as e:
        frappe.log_error(
            f"Error querying TER settings: {str(e)}",
            "TER Settings Query Error"
        )
        return None
        
def generate_ter_table_report(start_date, end_date, company=None):
    """Generate PPh 21 TER table report for a period"""
    try:
        filters = {
            "docstatus": 1,  # Submitted documents
            "start_date": [">=", start_date],
            "end_date": ["<=", end_date]
        }
        
        if company:
            filters["company"] = company
            
        # Get all salary slips in the period
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters=filters,
            fields=["name", "employee", "employee_name", "is_using_ter", "ter_rate", 
                    "gross_pay", "start_date", "end_date", "company"]
        )
        
        # Sort data by employee and date
        ter_data = []
        for slip in salary_slips:
            if cint(slip.is_using_ter):
                # Get PPh 21 amount from salary slip components
                try:
                    slip_doc = frappe.get_doc("Salary Slip", slip.name)
                    pph21_amount = 0
                    
                    for deduction in slip_doc.deductions:
                        if deduction.salary_component == "PPh 21":
                            pph21_amount = flt(deduction.amount)
                            break
                            
                    # Add to report data
                    ter_data.append({
                        "employee": slip.employee,
                        "employee_name": slip.employee_name,
                        "salary_slip": slip.name,
                        "gross_income": slip.gross_pay,
                        "ter_rate": slip.ter_rate,
                        "pph21_amount": pph21_amount,
                        "month": getdate(slip.end_date).month,
                        "year": getdate(slip.end_date).year,
                        "company": slip.company
                    })
                except Exception as e:
                    frappe.log_error(
                        f"Error processing salary slip {slip.name} for TER report: {str(e)}",
                        "TER Report Error"
                    )
                    continue
        
        return ter_data
        
    except Exception as e:
        frappe.log_error(
            f"Error generating TER table report: {str(e)}",
            "TER Report Generation Error"
        )
        frappe.throw(_("Error generating TER report: {0}").format(str(e)))