# -*- coding: utf-8 -*-
# Copyright (c) 2025, Danny Audian and contributors
# For license information, please see license.txt
# Last modified: 2025-04-23 12:17:47 by dannyaudian

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class PPh21TERTable(Document):
    def validate(self):
        """Validate TER rate settings"""
        if self.rate and (self.rate < 0 or self.rate > 100):
            frappe.throw("Tax rate must be between 0 and 100 percent")
        
        self.validate_range()
        self.validate_duplicate()
    
    def validate_range(self):
        """Validate income range"""
        if self.income_from < 0:
            frappe.throw("Income From cannot be negative")
        
        if self.income_to > 0 and self.income_from >= self.income_to:
            frappe.throw("Income From must be less than Income To")
        
        # For highest bracket, income_to can be 0
        if self.income_to == 0 and not self.is_highest_bracket:
            frappe.throw("Income To can only be 0 for the highest bracket")
    
    def validate_duplicate(self):
        """Check for duplicate status+range combinations"""
        if frappe.db.exists(
            "PPh 21 TER Table",
            {
                "name": ["!=", self.name],
                "status_pajak": self.status_pajak,
                "income_from": self.income_from,
                "income_to": self.income_to
            }
        ):
            frappe.throw(f"Duplicate TER rate exists for status {self.status_pajak} with range {self.income_from} to {self.income_to}")
    
    def before_save(self):
        """Set the description automatically"""
        status_label = {
            "TK0": "Tidak Kawin 0 Tanggungan",
            "TK1": "Tidak Kawin 1 Tanggungan",
            "TK2": "Tidak Kawin 2 Tanggungan",
            "TK3": "Tidak Kawin 3 Tanggungan",
            "K0": "Kawin 0 Tanggungan",
            "K1": "Kawin 1 Tanggungan",
            "K2": "Kawin 2 Tanggungan",
            "K3": "Kawin 3 Tanggungan",
            "HB0": "Kawin Penghasilan Istri Digabung 0 Tanggungan",
            "HB1": "Kawin Penghasilan Istri Digabung 1 Tanggungan",
            "HB2": "Kawin Penghasilan Istri Digabung 2 Tanggungan",
            "HB3": "Kawin Penghasilan Istri Digabung 3 Tanggungan"
        }
        
        if self.income_to > 0:
            income_range = f"Rp {format_number(self.income_from)} - Rp {format_number(self.income_to)}"
        else:
            income_range = f"Lebih dari Rp {format_number(self.income_from)}"
            
        status_text = status_label.get(self.status_pajak, self.status_pajak)
        self.description = f"{status_text}, Penghasilan {income_range}, TER {self.rate}%"

def format_number(number):
    """Format number with thousand separator"""
    return f"{number:,.0f}".replace(",", ".")