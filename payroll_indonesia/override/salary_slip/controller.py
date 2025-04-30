# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-30 10:37:39 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate, now_datetime, add_to_date
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip

class IndonesiaPayrollSalarySlip(SalarySlip):
    """Custom Salary Slip class for Indonesia Payroll"""

    def get_component(self, component_name):
        """Get amount of a salary component"""
        for d in self.earnings + self.deductions:
            if d.salary_component == component_name:
                return d.amount
        return 0

    def set_component(self, component_name, amount, is_deduction=False):
        """Set or update a component in earnings or deductions"""
        target = self.deductions if is_deduction else self.earnings
        found = False
        for d in target:
            if d.salary_component == component_name:
                d.amount = flt(amount)
                found = True
                break
        if not found:
            target.append({
                "salary_component": component_name,
                "amount": flt(amount)
            })

    def initialize_payroll_fields(self):
        """
        Initialize additional payroll fields for Indonesian Payroll.
        """
        defaults = {
            'biaya_jabatan': 0,
            'netto': 0,
            'total_bpjs': 0,
            'is_using_ter': 0,
            'ter_rate': 0,
            'koreksi_pph21': 0,
            'payroll_note': "",
            'npwp': "",
            'ktp': "",
            'is_final_gabung_suami': 0,
        }
        
        # Set defaults for fields that don't exist or are None
        for field, default in defaults.items():
            if not hasattr(self, field) or getattr(self, field) is None:
                setattr(self, field, default)
                
        return defaults  # Return defaults for external callers who might need them

    def queue_document_updates_on_cancel(self):
        """
        Schedule updates to related documents when canceling salary slip.
        This is a stub function that will be implemented in the full version.
        """
        # This will be implemented in the full version
        # For now, it's just a placeholder to ensure import works
        pass

# Module-level functions that need to be exported

def setup_fiscal_year_if_missing(date_str=None):
    """
    Automatically set up a fiscal year if missing
    Returns:
        dict: Result of the fiscal year creation
    """
    try:
        from frappe.utils import getdate, add_days, add_to_date
        test_date = getdate(date_str) if date_str else getdate()
        
        # Check if fiscal year exists
        fiscal_year = frappe.db.get_value("Fiscal Year", {
            "year_start_date": ["<=", test_date],
            "year_end_date": [">=", test_date]
        })
        
        if fiscal_year:
            return {
                "status": "exists",
                "fiscal_year": fiscal_year
            }
        
        # Create a new fiscal year
        year = test_date.year
        fy_start_month = frappe.db.get_single_value("Accounts Settings", "fy_start_date_is") or 1
        
        # Create fiscal year based on start month
        if fy_start_month == 1:
            # Calendar year
            start_date = getdate(f"{year}-01-01")
            end_date = getdate(f"{year}-12-31")
        else:
            # Custom fiscal year
            start_date = getdate(f"{year}-{fy_start_month:02d}-01")
            if start_date > test_date:
                start_date = add_to_date(start_date, years=-1)
            end_date = add_to_date(start_date, days=-1, years=1)
        
        # Create the fiscal year
        new_fy = frappe.new_doc("Fiscal Year")
        new_fy.year = f"{start_date.year}"
        if start_date.year != end_date.year:
            new_fy.year += f"-{end_date.year}"
        new_fy.year_start_date = start_date
        new_fy.year_end_date = end_date
        new_fy.save()
        
        return {
            "status": "created",
            "fiscal_year": new_fy.name,
            "year": new_fy.year,
            "start_date": start_date.strftime('%Y-%m-%d'),
            "end_date": end_date.strftime('%Y-%m-%d')
        }
        
    except Exception as e:
        frappe.log_error(
            f"Error setting up fiscal year: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Fiscal Year Setup Error"
        )
        return {
            "status": "error",
            "message": str(e)
        }

# Export these functions at the module level so they can be imported directly
get_component = IndonesiaPayrollSalarySlip.get_component
set_component = IndonesiaPayrollSalarySlip.set_component