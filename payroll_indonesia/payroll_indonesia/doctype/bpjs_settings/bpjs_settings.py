# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import flt

class BPJSSettings(Document):
    def validate(self):
        """Validate BPJS settings"""
        # Validate percentages are within acceptable ranges
        if flt(self.kesehatan_employee_percent) <= 0 or flt(self.kesehatan_employee_percent) > 5:
            frappe.throw("Persentase BPJS Kesehatan karyawan harus antara 0 dan 5%")
        
        if flt(self.kesehatan_employer_percent) <= 0 or flt(self.kesehatan_employer_percent) > 10:
            frappe.throw("Persentase BPJS Kesehatan perusahaan harus antara 0 dan 10%")
        
        if flt(self.jht_employee_percent) < 0 or flt(self.jht_employee_percent) > 5:
            frappe.throw("Persentase JHT karyawan harus antara 0 dan 5%")
        
        if flt(self.jht_employer_percent) < 0 or flt(self.jht_employer_percent) > 10:
            frappe.throw("Persentase JHT perusahaan harus antara 0 dan 10%")
        
        if flt(self.jp_employee_percent) < 0 or flt(self.jp_employee_percent) > 5:
            frappe.throw("Persentase JP karyawan harus antara 0 dan 5%")
        
        if flt(self.jp_employer_percent) < 0 or flt(self.jp_employer_percent) > 5:
            frappe.throw("Persentase JP perusahaan harus antara 0 dan 5%")
        
        if flt(self.jkk_percent) < 0 or flt(self.jkk_percent) > 5:
            frappe.throw("Persentase JKK harus antara 0 dan 5%")
        
        if flt(self.jkm_percent) < 0 or flt(self.jkm_percent) > 5:
            frappe.throw("Persentase JKM harus antara 0 dan 5%")
        
        # Validate maximum salary values
        if flt(self.kesehatan_max_salary) <= 0:
            frappe.throw("Batas maksimal gaji BPJS Kesehatan harus lebih dari 0")
        
        if flt(self.jp_max_salary) <= 0:
            frappe.throw("Batas maksimal gaji JP harus lebih dari 0")