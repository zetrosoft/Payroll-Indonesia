# -*- coding: utf-8 -*-
# Copyright (c) 2025, Danny Audian and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class PPh21Settings(Document):
    def validate(self):
        """Validate PPh 21 settings"""
        self.validate_bracket_table()
        self.validate_ptkp_table()
        
    def validate_bracket_table(self):
        """Ensure tax brackets are continuous and non-overlapping"""
        if not self.bracket_table:
            frappe.throw("At least one tax bracket must be defined")
        
        # Sort by income_from
        sorted_brackets = sorted(self.bracket_table, key=lambda x: x.income_from)
        
        # Check for gaps or overlaps
        for i in range(len(sorted_brackets) - 1):
            current = sorted_brackets[i]
            next_bracket = sorted_brackets[i + 1]
            
            if current.income_to != next_bracket.income_from:
                frappe.throw(f"Tax brackets must be continuous. Gap found between {current.income_to} and {next_bracket.income_from}")
    
    def validate_ptkp_table(self):
        """Ensure all PTKP status types are defined"""
        required_status = ["TK0", "K0", "K1", "K2", "K3"]
        
        if not self.ptkp_table:
            frappe.throw("PTKP values must be defined")
        
        defined_status = [p.status_pajak for p in self.ptkp_table]
        
        for status in required_status:
            if status not in defined_status:
                frappe.throw(f"Missing PTKP definition for status: {status}")
    
    def get_ptkp_amount(self, status_pajak):
        """Get PTKP amount for a given tax status
        
        Args:
            status_pajak (str): Tax status (TK0, K0, K1, etc.)
            
        Returns:
            float: PTKP amount for the tax status
        """
        # Default value if not found
        default_ptkp = 54000000  # TK0 value
        
        for row in self.ptkp_table:
            if row.status_pajak == status_pajak:
                return float(row.ptkp_amount)
        
        # If status not found, return default TK0 value
        return default_ptkp