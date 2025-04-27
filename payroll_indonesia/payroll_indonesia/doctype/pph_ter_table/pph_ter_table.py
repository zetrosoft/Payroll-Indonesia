# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 07:16:40 by dannyaudian

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, flt, fmt_money

def get_formatted_currency(value, company=None):
    """Format currency value based on company settings"""
    if company:
        currency = frappe.get_cached_value('Company', company, 'default_currency')
    else:
        currency = frappe.db.get_default("currency")
    return fmt_money(value, currency=currency)

class PPhTERTable(Document):
    def validate(self):
        self.validate_company()
        self.validate_details()
        self.calculate_total()
        self.validate_total()
        self.sync_month_period()
    
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
    
    def validate_details(self):
        """Validate PPh TER details"""
        if not self.details:
            frappe.throw(_("At least one employee record is required for PPh TER"))
            
        for d in self.details:
            if not d.amount or d.amount <= 0:
                frappe.throw(_("PPh amount must be greater than 0 for employee {0}").format(d.employee_name))
    
    def calculate_total(self):
        """Calculate total from details"""
        self.total = sum(flt(d.amount) for d in self.details)
    
    def validate_total(self):
        """Validate total amount is greater than 0"""
        if not self.total or self.total <= 0:
            frappe.throw(_("Total amount must be greater than 0"))
    
    def sync_month_period(self):
        """Sync month and period fields, update month_year_title"""
        period_to_month = {
            "January": 1, "February": 2, "March": 3, "April": 4,
            "May": 5, "June": 6, "July": 7, "August": 8,
            "September": 9, "October": 10, "November": 11, "December": 12
        }
        
        month_to_period = {v: k for k, v in period_to_month.items()}
        
        # Sync fields
        if self.period and (not self.month or self.month <= 0 or self.month > 12):
            self.month = period_to_month.get(self.period, 0)
        elif self.month and not self.period and 1 <= self.month <= 12:
            self.period = month_to_period.get(self.month, "")
        
        # Update title
        if self.period and self.year:
            self.month_year_title = f"{self.period} {self.year}"
    
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
        """Generate Payment Entry for PPh TER payment to tax office"""
        if self.payment_entry:
            frappe.throw(_("Payment Entry already exists"))
            
        if self.docstatus != 1:
            frappe.throw(_("Document must be submitted first"))
            
        try:
            # Create payment entry
            pe = frappe.new_doc("Payment Entry")
            pe.payment_type = "Pay"
            pe.party_type = "Supplier"
            pe.party = "Kantor Pajak"  # Tax Office
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
            
            # Add custom remarks with period
            period_text = f"{self.period} {self.year}"
            pe.remarks = (
                f"PPh 21 Payment for {period_text}\n"
                f"Total Amount: {get_formatted_currency(self.total, pe.company)}"
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