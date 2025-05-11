# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
import json
import os
from frappe.model.document import Document

class PayrollIndonesiaSettings(Document):
    def validate(self):
        """Validate settings on save"""
        self.validate_tax_settings()
        self.validate_bpjs_settings()
        self.set_app_info()
        
    def set_app_info(self):
        """Update app info fields"""
        if not self.app_last_updated:
            self.app_last_updated = frappe.utils.now()
        
        if not self.app_updated_by:
            self.app_updated_by = frappe.session.user
    
    def validate_tax_settings(self):
        """Validate tax-related settings"""
        if not self.ptkp_table:
            frappe.msgprint(
                _("PTKP values must be defined for tax calculation"),
                indicator="orange"
            )
            
        if self.use_ter and not self.ptkp_ter_mapping_table:
            frappe.msgprint(
                _("PTKP to TER mappings should be defined when using TER calculation method"),
                indicator="orange"
            )
            
        # Validate tax brackets
        if not self.tax_brackets_table:
            frappe.msgprint(
                _("Tax brackets should be defined for tax calculation"),
                indicator="orange"
            )
    
    def validate_bpjs_settings(self):
        """Validate BPJS-related settings"""
        # Validate BPJS percentages
        if hasattr(self, 'kesehatan_employee_percent') and (self.kesehatan_employee_percent < 0 or self.kesehatan_employee_percent > 5):
            frappe.msgprint(_("BPJS Kesehatan employee percentage must be between 0 and 5%"), indicator="orange")
            
        if hasattr(self, 'kesehatan_employer_percent') and (self.kesehatan_employer_percent < 0 or self.kesehatan_employer_percent > 10):
            frappe.msgprint(_("BPJS Kesehatan employer percentage must be between 0 and 10%"), indicator="orange")
    
    def get_ptkp_value(self, status_pajak):
        """Get PTKP value for a specific tax status"""
        if not self.ptkp_table:
            return 0
            
        for row in self.ptkp_table:
            if row.status_pajak == status_pajak:
                return row.ptkp_amount
                
        return 0
    
    def get_ptkp_values_dict(self):
        """Return PTKP values as a dictionary"""
        ptkp_dict = {}
        for row in self.ptkp_table:
            ptkp_dict[row.status_pajak] = row.ptkp_amount
            
        return ptkp_dict
    
    def get_ptkp_ter_mapping_dict(self):
        """Return PTKP to TER mapping as a dictionary"""
        mapping_dict = {}
        for row in self.ptkp_ter_mapping_table:
            mapping_dict[row.ptkp_status] = row.ter_category
            
        return mapping_dict
    
    def get_tax_brackets_list(self):
        """Return tax brackets as a list of dictionaries"""
        brackets = []
        for row in self.tax_brackets_table:
            brackets.append({
                "income_from": row.income_from,
                "income_to": row.income_to,
                "tax_rate": row.tax_rate
            })
            
        return brackets
    
    def get_tipe_karyawan_list(self):
        """Return employee types as a list"""
        types = []
        for row in self.tipe_karyawan:
            types.append(row.tipe_karyawan)
            
        return types
    
    def get_ter_category(self, ptkp_status):
        """Get TER category for a specific PTKP status"""
        if not self.ptkp_ter_mapping_table:
            return "TER A"  # Default
            
        for row in self.ptkp_ter_mapping_table:
            if row.ptkp_status == ptkp_status:
                return row.ter_category
                
        return "TER A"  # Default if not found
    
    def get_ter_rate(self, ter_category, income):
        """Get TER rate based on TER category and income"""
        if not self.use_ter:
            return 0
            
        # This method requires querying the TER Table, which is stored in a separate DocType
        ter_entries = frappe.get_all(
            "PPh 21 TER Table", 
            filters={
                "status_pajak": ter_category
            },
            fields=["income_from", "income_to", "rate", "is_highest_bracket"],
            order_by="income_from"
        )
        
        for entry in ter_entries:
            # Check if income falls in range
            if entry.is_highest_bracket and income >= entry.income_from:
                return entry.rate
            elif income >= entry.income_from and income < entry.income_to:
                return entry.rate
                
        return 0  # Default if not found