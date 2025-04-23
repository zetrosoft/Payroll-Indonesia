# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _

def prepare_tax_report():
    """Prepare annual tax reports for employees
    
    This function should be called at the end of the tax year
    to prepare tax reports (form 1721-A1) for each employee
    """
    try:
        frappe.log_error("Tax report preparation triggered", "Yearly Tax Report")
    except Exception as e:
        frappe.log_error(f"Error preparing tax reports: {str(e)}", "Yearly Tax Error")