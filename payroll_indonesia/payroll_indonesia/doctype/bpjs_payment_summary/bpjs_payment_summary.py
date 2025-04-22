# -*- coding: utf-8 -*-
# Copyright (c) 2025, Danny Audian and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, flt, get_formatted_currency

class BPJSPaymentSummary(Document):
    def validate(self):
        self.validate_company()
        self.validate_components()
        self.calculate_total()
        self.validate_total()
        self.validate_supplier()
    
    def validate_company(self):
        """Validate company and its default accounts"""
        if not self.company:
            frappe.throw(_("Company is mandatory"))
            
        # Check default accounts
        company_doc = frappe.get_doc("Company", self.company)
        if not company_doc.default_bank_account:
            frappe.throw(_("Default Bank Account not set for Company {0}").format(self.company))
        if not company_doc.default_payable_account:
            frappe.throw(_("Default Payable Account not set for Company {0}").format(self.company))
    
    def validate_components(self):
        """Validate BPJS components"""
        if not self.komponen:
            frappe.throw(_("At least one BPJS component is required"))
            
        for d in self.komponen:
            if not d.amount or d.amount <= 0:
                frappe.throw(_("Amount must be greater than 0 for component {0}").format(d.idx))
    
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
            from .bpjs_payment_validation import create_bpjs_supplier
            create_bpjs_supplier()
    
    def on_submit(self):
        """Set status to Submitted"""
        self.status = "Submitted"
    
    def on_cancel(self):
        """Reset status to Draft"""
        if self.payment_entry:
            pe_status = frappe.db.get_value("Payment Entry", self.payment_entry, "docstatus")
            if pe_status and int(pe_status) == 1:
                frappe.throw(_("Cannot cancel document with submitted Payment Entry"))
        self.status = "Draft"
    
    @frappe.whitelist()
    def generate_payment_entry(self):
        """Generate Payment Entry for BPJS payment"""
        if self.payment_entry:
            frappe.throw(_("Payment Entry already exists"))
            
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
            
            # Add custom remarks with components
            components_text = "\n".join([
                f"- {d.component}: {get_formatted_currency(d.amount, pe.company)}"
                for d in self.komponen
            ])
            pe.remarks = (
                f"BPJS Payment for {self.name}\n"
                f"Components:\n{components_text}"
            )
            
            # Save and submit
            pe.insert()
            pe.submit()
            
            # Update this document
            self.db_set('payment_entry', pe.name)
            self.db_set('status', 'Paid')
            
            return pe.name
            
        except Exception as e:
            frappe.msgprint(_("Error creating Payment Entry"))
            frappe.throw(str(e))
