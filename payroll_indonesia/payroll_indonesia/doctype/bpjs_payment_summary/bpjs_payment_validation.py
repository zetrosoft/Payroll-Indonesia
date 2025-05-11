# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def create_bpjs_supplier():
    """Create BPJS supplier with correct configuration"""
    if not frappe.db.exists("Supplier", "BPJS"):
        try:
            supplier = frappe.new_doc("Supplier")
            supplier.supplier_name = "BPJS"
            supplier.supplier_group = "Government"
            supplier.supplier_type = "Government"
            supplier.country = "Indonesia"
            supplier.default_currency = "IDR"

            # Set tax category if exists
            if frappe.db.exists("Tax Category", "Government"):
                supplier.tax_category = "Government"

            supplier.insert()

            frappe.db.commit()

            frappe.msgprint(_("Created default BPJS supplier"))

        except Exception as e:
            frappe.log_error("Error creating BPJS supplier", str(e))
            frappe.throw(_("Failed to create BPJS supplier: {0}").format(str(e)))
