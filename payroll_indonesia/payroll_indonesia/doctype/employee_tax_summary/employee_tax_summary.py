# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-26 18:24:06 by dannyaudian

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

class EmployeeTaxSummary(Document):
    def validate(self):
        """Validate the employee tax summary"""
        self.validate_duplicate()
        self.set_title()
        self.calculate_ytd_from_monthly()
    
    def validate_duplicate(self):
        """Check if another record exists for the same employee and year"""
        if frappe.db.exists(
            "Employee Tax Summary", 
            {
                "name": ["!=", self.name],
                "employee": self.employee,
                "year": self.year
            }
        ):
            frappe.throw(_(f"Tax summary for employee {self.employee_name} for year {self.year} already exists"))
    
    def set_title(self):
        """Set the document title"""
        self.title = f"{self.employee_name} - {self.year}"
    
    def calculate_ytd_from_monthly(self):
        """Calculate YTD tax amount from monthly details"""
        if not self.monthly_details:
            return
            
        total_tax = 0
        for monthly in self.monthly_details:
            total_tax += flt(monthly.tax_amount)
        
        self.ytd_tax = total_tax

    def add_monthly_data(self, salary_slip):
        """Add or update monthly tax data from salary slip
        
        Args:
            salary_slip: The salary slip document to get tax data from
        """
        month = getdate(salary_slip.start_date).month
        
        # Get tax amount from salary slip
        pph21_amount = 0
        bpjs_deductions = 0
        other_deductions = 0
        
        for deduction in salary_slip.deductions:
            if deduction.salary_component == "PPh 21":
                pph21_amount = flt(deduction.amount)
            elif deduction.salary_component in ["BPJS JHT Employee", "BPJS JP Employee", "BPJS Kesehatan Employee"]:
                bpjs_deductions += flt(deduction.amount)
            else:
                other_deductions += flt(deduction.amount)
        
        # Check if month already exists in monthly details
        existing_month = None
        for i, d in enumerate(self.monthly_details):
            if d.month == month:
                existing_month = i
                break
        
        if existing_month is not None:
            # Update existing month
            self.monthly_details[existing_month].salary_slip = salary_slip.name
            self.monthly_details[existing_month].gross_pay = salary_slip.gross_pay
            self.monthly_details[existing_month].bpjs_deductions = bpjs_deductions
            self.monthly_details[existing_month].other_deductions = other_deductions
            self.monthly_details[existing_month].tax_amount = pph21_amount
            self.monthly_details[existing_month].is_using_ter = 1 if hasattr(salary_slip, 'is_using_ter') and salary_slip.is_using_ter else 0
            self.monthly_details[existing_month].ter_rate = salary_slip.ter_rate if hasattr(salary_slip, 'ter_rate') else 0
        else:
            # Add new month
            self.append("monthly_details", {
                "month": month,
                "salary_slip": salary_slip.name,
                "gross_pay": salary_slip.gross_pay,
                "bpjs_deductions": bpjs_deductions,
                "other_deductions": other_deductions,
                "tax_amount": pph21_amount,
                "is_using_ter": 1 if hasattr(salary_slip, 'is_using_ter') and salary_slip.is_using_ter else 0,
                "ter_rate": salary_slip.ter_rate if hasattr(salary_slip, 'ter_rate') else 0
            })
        
        # Recalculate YTD
        self.calculate_ytd_from_monthly()
        
        # Save document
        self.save(ignore_permissions=True)
    
    def get_ytd_data_until_month(self, month):
        """Get YTD data until specified month
        
        Args:
            month: Month to get data until (1-12)
            
        Returns:
            dict: Dictionary containing YTD data with keys:
                - gross: Total gross pay
                - bpjs: Total BPJS deductions
                - pph21: Total PPh 21 paid
        """
        result = {"gross": 0, "bpjs": 0, "pph21": 0}
        
        if not self.monthly_details:
            return result
        
        for monthly in self.monthly_details:
            if monthly.month < month:
                result["gross"] += flt(monthly.gross_pay)
                result["bpjs"] += flt(monthly.bpjs_deductions)
                result["pph21"] += flt(monthly.tax_amount)
        
        return result