# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-23 11:40:25 by dannyaudian

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class EmployeeTaxSummary(Document):
    def validate(self):
        """Validate the employee tax summary"""
        self.validate_duplicate()
        self.set_title()
    
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
            frappe.throw(f"Tax summary for employee {self.employee_name} for year {self.year} already exists")
    
    def set_title(self):
        """Set the document title"""
        self.title = f"{self.employee_name} - {self.year}"