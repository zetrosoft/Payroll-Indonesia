# Copyright (c) 2023, Danny Audian and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class PPHTERTable(Document):
    def validate(self):
        # Ensure from_income < to_income if both are provided
        if self.from_income and self.to_income and self.from_income > self.to_income:
            frappe.throw("Penghasilan Dari harus lebih kecil dari Penghasilan Sampai")