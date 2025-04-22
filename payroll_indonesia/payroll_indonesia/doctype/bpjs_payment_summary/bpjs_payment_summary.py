# -*- coding: utf-8 -*-
# Copyright (c) 2025, Danny Audian and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, flt

class BPJSPaymentSummary(Document):
    def validate(self):
        self.validate_total()
        self.validate_supplier()
        self.calculate_total()
    
    def calculate_total(self):
        """Calculate total from components"""
        self.total = sum(flt(d.amount) for d in self.komponen)
    
    def validate_total(self):
        """Validate total amount is greater than 0"""
        if not self.total or self.total <= 0:
            frappe.throw(_("Total amount must be greater than 0"))
    
    def validate_supplier(self):
        """Validate BPJS supplier exists"""
        if not frappe.db.exists("Supplier", "BPJS"):
            frappe.throw(
                _("Supplier 'BPJS' does not exist. Please create it first.")
            )
    
    def on_submit(self):
        """Set status to Submitted"""
        self.status = "Submitted"
    
    def on_cancel(self):
        """Reset status to Draft"""
        if self.payment_entry:
            frappe.throw(_("Cannot cancel document with linked Payment Entry"))
        self.status = "Draft"
    
    @frappe.whitelist()
    def generate_payment_entry(self):
        """Generate Payment Entry for BPJS payment"""
        if self.payment_entry:
            frappe.throw(_("Payment Entry already exists"))
            
        if not self.company:
            frappe.throw(_("Company is required"))
            
        if self.docstatus != 1:
            frappe.throw(_("Document must be submitted first"))
            
        try:
            # Create payment entry
            pe = frappe.new_doc("Payment Entry")
            pe.payment_type = "Pay"
            pe.party_type = "Supplier"
            pe.party = "BPJS"
            pe.posting_date = today()
            pe.paid_amount = self.total
            pe.received_amount = self.total
            
            # Set company and accounts
            pe.company = self.company
            pe.paid_from = frappe.get_cached_value('Company', self.company, 'default_bank_account')
            pe.paid_to = frappe.get_cached_value('Company', self.company, 'default_payable_account')
            
            # Set references
            pe.reference_doctype = self.doctype
            pe.reference_name = self.name
            
            # Add custom remarks
            pe.remarks = f"BPJS Payment for {self.name}"
            
            # Save and submit
            pe.insert()
            pe.submit()
            
            # Update this document
            self.payment_entry = pe.name
            self.status = "Paid"
            self.save()
            
            frappe.msgprint(
                _("Payment Entry {0} has been created").format(
                    frappe.bold(pe.name)
                )
            )
            
            return pe.name
            
        except Exception as e:
            frappe.throw(_("Error creating Payment Entry: {0}").format(str(e)))