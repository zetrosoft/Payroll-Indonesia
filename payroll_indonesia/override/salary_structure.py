# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from hrms.payroll.doctype.salary_structure.salary_structure import SalaryStructure

class CustomSalaryStructure(SalaryStructure):
    def validate(self):
        """Override validasi Salary Structure untuk mengizinkan company='%'"""
        # Simpan nilai company original
        original_company = self.company
        
        # Jika company adalah wildcard '%', gunakan company default untuk validasi saja
        if self.company == "%":
            default_company = frappe.defaults.get_global_default("company")
            self.company = default_company
            
        # Jalankan validasi standard
        super().validate()
        
        # Kembalikan nilai company ke wildcard jika itu nilai aslinya
        if original_company == "%":
            self.company = original_company
            
    def on_update(self):
        """Pastikan income_tax_slab terisi jika ada component PPh 21"""
        super().on_update()
        
        # Cek apakah ada komponen PPh 21
        has_tax_component = False
        for d in self.deductions:
            if d.salary_component == "PPh 21":
                has_tax_component = True
                break
                
        # Jika ada komponen PPh 21 tapi tidak ada income_tax_slab, coba isi
        if has_tax_component and not self.income_tax_slab:
            # Cek apakah ada Income Tax Slab default
            tax_slab = frappe.db.get_value("Income Tax Slab", {"currency": self.currency, "is_default": 1}, "name")
            if tax_slab:
                self.income_tax_slab = tax_slab
                self.tax_calculation_method = "Manual"  # Untuk PPh 21 Indonesia
                
                # Save langsung ke DB untuk menghindari trigger validasi lagi
                frappe.db.set_value("Salary Structure", self.name, {
                    "income_tax_slab": tax_slab,
                    "tax_calculation_method": "Manual"
                })
                frappe.db.commit()