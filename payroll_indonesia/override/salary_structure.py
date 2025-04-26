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
                
        # Periksa apakah field income_tax_slab ada dalam doctype
        field_exists = False
        try:
            # Cek apakah attribut ada atau bisa diakses dari db
            if hasattr(self, 'income_tax_slab'):
                field_exists = True
            else:
                # Coba ambil dari database
                tax_slab_value = frappe.db.get_value("Salary Structure", self.name, "income_tax_slab")
                if tax_slab_value is not None:
                    field_exists = True
        except Exception:
            field_exists = False
                
        # Jika ada komponen PPh 21 dan field income_tax_slab ada, tapi nilainya kosong
        if has_tax_component and field_exists:
            tax_slab_value = getattr(self, 'income_tax_slab', None) or frappe.db.get_value("Salary Structure", self.name, "income_tax_slab")
            
            if not tax_slab_value:
                # Cek apakah ada Income Tax Slab default
                tax_slab = frappe.db.get_value("Income Tax Slab", {"currency": self.currency, "is_default": 1}, "name")
                
                if tax_slab:
                    try:
                        # Update langsung ke DB untuk menghindari error
                        update_dict = {"tax_calculation_method": "Manual"}
                        
                        # Tambahkan income_tax_slab jika field ada di DocType
                        if field_exists:
                            update_dict["income_tax_slab"] = tax_slab
                            
                        frappe.db.set_value("Salary Structure", self.name, update_dict)
                        frappe.db.commit()
                    except Exception as e:
                        # Log error tapi jangan crash
                        frappe.log_error(f"Failed to update income_tax_slab: {str(e)}", "CustomSalaryStructure")