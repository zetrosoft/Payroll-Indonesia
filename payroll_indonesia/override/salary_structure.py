# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment import SalaryStructureAssignment

class CustomSalaryStructureAssignment(SalaryStructureAssignment):
    """
    Override Salary Structure Assignment untuk pengaturan pajak kustom Indonesia
    """
    
    def validate_income_tax_slab(self):
        """
        Override validasi wajib Income Tax Slab jika menggunakan PPh 21 kustom Indonesia
        """
        try:
            # Cek apakah kita menggunakan perhitungan pajak kustom dari Indonesia Payroll
            if frappe.db.exists("DocType", "PPh 21 Settings"):
                pph_settings = frappe.db.get_value("PPh 21 Settings", "PPh 21 Settings", 
                                                  ["enabled", "calculation_method"], as_dict=1)
                if pph_settings and pph_settings.get("enabled"):
                    # Kita menggunakan logika pajak kustom Indonesia, lewati validasi standar
                    
                    # Set income_tax_slab jika field ada di doctype
                    if hasattr(self, 'income_tax_slab') and not self.income_tax_slab:
                        # Coba dapatkan tax slab default
                        from payroll_indonesia.utilities.tax_slab import get_default_tax_slab
                        default_tax_slab = get_default_tax_slab()
                        if default_tax_slab:
                            self.income_tax_slab = default_tax_slab
                    
                    return
        except Exception as e:
            frappe.logger().warning(f"Error checking PPh 21 Settings: {str(e)}")
            
        # Jika kita sampai di sini, gunakan validasi standar
        super().validate_income_tax_slab()