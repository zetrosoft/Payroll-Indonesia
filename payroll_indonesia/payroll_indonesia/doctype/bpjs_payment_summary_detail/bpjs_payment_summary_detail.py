# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-23 11:46:47 by dannyaudian

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class BPJSPaymentSummaryDetail(Document):
    def validate(self):
        """Validate payment details"""
        if self.amount and self.amount <= 0:
            frappe.throw("Amount must be greater than 0")