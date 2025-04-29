# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 11:23:46 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate
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
