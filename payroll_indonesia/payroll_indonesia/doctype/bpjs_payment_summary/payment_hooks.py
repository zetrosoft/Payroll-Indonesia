# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 10:40:53 by dannyaudian

import frappe
from frappe.utils import flt

def payment_entry_on_submit(doc, method):
    """Update BPJS Payment Summary status when Payment Entry is submitted"""
    update_bpjs_payment_status(doc)

def payment_entry_on_cancel(doc, method):
    """Update BPJS Payment Summary status when Payment Entry is cancelled"""
    update_bpjs_payment_status(doc, cancel=True)

def update_bpjs_payment_status(doc, cancel=False):
    """Update the status of linked BPJS Payment Summary"""
    # Check if this payment entry is linked to a BPJS Payment Summary
    bpjs_summary = None
    
    # Check references
    if hasattr(doc, 'references') and doc.references:
        for ref in doc.references:
            if ref.reference_doctype == "BPJS Payment Summary":
                bpjs_summary = ref.reference_name
                break
    
    # Exit if no BPJS summary found
    if not bpjs_summary:
        return
        
    # Get the BPJS Payment Summary
    bpjs_doc = frappe.get_doc("BPJS Payment Summary", bpjs_summary)
    
    # Update status based on payment entry action
    if cancel:
        if bpjs_doc.docstatus == 1:  # Only update if still submitted
            bpjs_doc.db_set('status', 'Submitted')
            bpjs_doc.db_set('payment_entry', None)
            frappe.msgprint(f"BPJS Payment Summary {bpjs_summary} status updated to 'Submitted'")
    else:
        bpjs_doc.db_set('status', 'Paid')
        frappe.msgprint(f"BPJS Payment Summary {bpjs_summary} status updated to 'Paid'")