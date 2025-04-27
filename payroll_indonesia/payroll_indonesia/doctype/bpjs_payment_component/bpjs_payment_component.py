# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 08:56:06 by dannyaudian

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class BPJSPaymentComponent(Document):
    def validate(self):
        if not self.amount or self.amount <= 0:
            frappe.throw("Amount must be greater than 0")
        
        # Validasi komponen
        valid_components = ["BPJS Kesehatan", "BPJS JHT", "BPJS JP", "BPJS JKK", "BPJS JKM", "Lainnya"]
        if self.component not in valid_components:
            frappe.throw(f"Component harus salah satu dari: {', '.join(valid_components)}")