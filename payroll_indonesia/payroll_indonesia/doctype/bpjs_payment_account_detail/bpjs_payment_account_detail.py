# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class BPJSPaymentAccountDetail(Document):
    def validate(self):
        """Validate account detail"""
        if self.amount and self.amount <= 0:
            frappe.throw("Amount must be greater than 0")