# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 10:03:12 by dannyaudian

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document

class BPJSPaymentComponent(Document):
    def validate(self):
        if not self.amount or self.amount <= 0:
            frappe.throw("Amount must be greater than 0")
        
        # Validasi komponen
        valid_components = ["BPJS Kesehatan", "BPJS JHT", "BPJS JP", "BPJS JKK", "BPJS JKM", "Lainnya"]
        if self.component not in valid_components:
            frappe.throw(f"Component harus salah satu dari: {', '.join(valid_components)}")
    
    def on_submit(self):
        """Create journal entries when the component is submitted"""
        create_journal_entries(self.name)


@frappe.whitelist()
def create_journal_entries(doc_name=None):
    """
    Create journal entries for BPJS payment components
    
    Args:
        doc_name (str): Name of the BPJS Payment Component
        
    Returns:
        str: Name of the created journal entry or None if failed
    """
    try:
        if not doc_name:
            frappe.throw(_("BPJS Payment Component is required to create a journal entry"))
            
        component = frappe.get_doc("BPJS Payment Component", doc_name)
        
        if component.docstatus != 1:
            frappe.throw(_("Only submitted BPJS Payment Components can create journal entries"))
        
        # Skip if already has journal entry
        if hasattr(component, 'journal_entry') and component.journal_entry:
            frappe.msgprint(_("Journal Entry {0} already exists").format(component.journal_entry))
            return component.journal_entry
            
        # Get BPJS Account Mapping
        mapping = get_bpjs_account_mapping(component.company)
        if not mapping:
            frappe.msgprint(_("BPJS Account Mapping not found for company {0}. Cannot create journal entry.").format(component.company))
            return None
        
        # Create journal entry
        je_name = mapping.create_journal_entry(component)
        
        if je_name:
            # Update journal_entry field
            component.db_set('journal_entry', je_name)
            frappe.msgprint(_("Created Journal Entry {0}").format(je_name))
            return je_name
        
        return None
    except Exception as e:
        frappe.log_error(
            f"Error creating journal entries: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Journal Entry Creation Error"
        )
        frappe.msgprint(_("Error creating journal entry: {0}").format(str(e)))
        return None


def get_bpjs_account_mapping(company):
    """Get BPJS Account Mapping for this company"""
    try:
        mapping = frappe.get_all(
            "BPJS Account Mapping",
            filters={"company": company},
            limit=1
        )
        
        if mapping:
            return frappe.get_doc("BPJS Account Mapping", mapping[0].name)
        
        return None
    except Exception as e:
        frappe.log_error(
            f"Error getting BPJS Account Mapping for company {company}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Account Mapping Error"
        )
        return None