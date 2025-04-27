# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 09:42:17 by dannyaudian

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, cstr

class BPJSAccountMapping(Document):
    def validate(self):
        """Validate required fields and account types"""
        self.validate_duplicate_mapping()
        self.validate_account_types()
    
    def validate_duplicate_mapping(self):
        """Ensure no duplicate mapping exists for the same company"""
        if not self.is_new():
            # Skip validation when updating the same document
            return
            
        existing = frappe.db.get_value(
            "BPJS Account Mapping",
            {
                "company": self.company,
                "name": ["!=", self.name]
            },
            "mapping_name"
        )
        
        if existing:
            frappe.throw(_("BPJS Account Mapping '{0}' already exists for company {1}").format(
                existing, self.company
            ))
    
    def validate_account_types(self):
        """Validate that all accounts are of the correct type"""
        # Employee contribution accounts should be liability accounts
        self.validate_account_type(self.kesehatan_employee_account, ["Liability"], "BPJS Kesehatan Employee")
        self.validate_account_type(self.jht_employee_account, ["Liability"], "BPJS JHT Employee")
        self.validate_account_type(self.jp_employee_account, ["Liability"], "BPJS JP Employee")
        
        # Employer expense accounts should be expense accounts
        self.validate_account_type(self.kesehatan_employer_debit_account, ["Expense"], "BPJS Kesehatan Employer Expense")
        self.validate_account_type(self.jht_employer_debit_account, ["Expense"], "BPJS JHT Employer Expense")
        self.validate_account_type(self.jp_employer_debit_account, ["Expense"], "BPJS JP Employer Expense")
        self.validate_account_type(self.jkk_employer_debit_account, ["Expense"], "BPJS JKK Employer Expense")
        self.validate_account_type(self.jkm_employer_debit_account, ["Expense"], "BPJS JKM Employer Expense")
        
        # Employer liability accounts should be liability accounts
        self.validate_account_type(self.kesehatan_employer_credit_account, ["Liability"], "BPJS Kesehatan Employer Liability")
        self.validate_account_type(self.jht_employer_credit_account, ["Liability"], "BPJS JHT Employer Liability")
        self.validate_account_type(self.jp_employer_credit_account, ["Liability"], "BPJS JP Employer Liability")
        self.validate_account_type(self.jkk_employer_credit_account, ["Liability"], "BPJS JKK Employer Liability")
        self.validate_account_type(self.jkm_employer_credit_account, ["Liability"], "BPJS JKM Employer Liability")
    
    def validate_account_type(self, account, allowed_types, account_description):
        """Validate that an account is of the correct type"""
        if not account:
            # Skip validation if account is not provided
            return
            
        account_type = frappe.db.get_value("Account", account, "account_type")
        root_type = frappe.db.get_value("Account", account, "root_type")
        
        if root_type not in allowed_types:
            frappe.throw(_("{0} account {1} must be a {2} account").format(
                account_description, account, " or ".join(allowed_types)
            ))
    
    def get_accounts_for_component(self, component_type):
        """
        Get the accounts to use for a specific BPJS component
        
        Args:
            component_type (str): One of 'kesehatan', 'jht', 'jp', 'jkk', 'jkm'
            
        Returns:
            dict: Dictionary with employee_account, employer_debit, employer_credit keys
        """
        accounts = {
            "employee_account": None,
            "employer_debit": None,
            "employer_credit": None
        }
        
        # Set employee account
        employee_field = f"{component_type}_employee_account"
        if hasattr(self, employee_field):
            accounts["employee_account"] = getattr(self, employee_field)
            
        # Set employer debit (expense) account
        employer_debit_field = f"{component_type}_employer_debit_account"
        if hasattr(self, employer_debit_field):
            accounts["employer_debit"] = getattr(self, employer_debit_field)
            
        # Set employer credit (liability) account
        employer_credit_field = f"{component_type}_employer_credit_account"
        if hasattr(self, employer_credit_field):
            accounts["employer_credit"] = getattr(self, employer_credit_field)
            
        return accounts
        
    @staticmethod
    def get_mapping_for_company(company):
        """
        Get the BPJS Account Mapping for a company
        
        Args:
            company (str): Company name
            
        Returns:
            BPJSAccountMapping: The mapping document for the company or None if not found
        """
        mapping_name = frappe.db.get_value(
            "BPJS Account Mapping", 
            {"company": company},
            "name"
        )
        
        if mapping_name:
            return frappe.get_doc("BPJS Account Mapping", mapping_name)
        
        return None
    
    def create_journal_entry(self, bpjs_component, posting_date=None):
        """
        Create a Journal Entry for the BPJS component
        
        Args:
            bpjs_component (Document): BPJS Payment Component document
            posting_date (str, optional): Posting date for the journal entry
            
        Returns:
            str: Name of the created journal entry
        """
        try:
            if not bpjs_component:
                frappe.throw(_("BPJS Payment Component is required to create a journal entry"))
                
            if not posting_date:
                posting_date = bpjs_component.posting_date
                
            # Initialize accounts dictionary
            accounts = []
            
            # Process employee contributions if they exist
            if flt(bpjs_component.jht_employee) > 0 and self.jht_employee_account:
                accounts.append({
                    "account": self.jht_employee_account,
                    "credit_in_account_currency": flt(bpjs_component.jht_employee),
                    "reference_type": "BPJS Payment Component",
                    "reference_name": bpjs_component.name,
                    "user_remark": f"JHT Employee Contribution for {bpjs_component.employee_name}"
                })
                
            if flt(bpjs_component.jp_employee) > 0 and self.jp_employee_account:
                accounts.append({
                    "account": self.jp_employee_account,
                    "credit_in_account_currency": flt(bpjs_component.jp_employee),
                    "reference_type": "BPJS Payment Component",
                    "reference_name": bpjs_component.name,
                    "user_remark": f"JP Employee Contribution for {bpjs_component.employee_name}"
                })
                
            if flt(bpjs_component.kesehatan_employee) > 0 and self.kesehatan_employee_account:
                accounts.append({
                    "account": self.kesehatan_employee_account,
                    "credit_in_account_currency": flt(bpjs_component.kesehatan_employee),
                    "reference_type": "BPJS Payment Component",
                    "reference_name": bpjs_component.name,
                    "user_remark": f"Kesehatan Employee Contribution for {bpjs_component.employee_name}"
                })
                
            # Process employer contributions if they exist
            
            # JHT Employer
            if flt(bpjs_component.jht_employer) > 0:
                if self.jht_employer_debit_account:
                    accounts.append({
                        "account": self.jht_employer_debit_account,
                        "debit_in_account_currency": flt(bpjs_component.jht_employer),
                        "reference_type": "BPJS Payment Component",
                        "reference_name": bpjs_component.name,
                        "user_remark": f"JHT Employer Expense for {bpjs_component.employee_name}"
                    })
                    
                if self.jht_employer_credit_account:
                    accounts.append({
                        "account": self.jht_employer_credit_account,
                        "credit_in_account_currency": flt(bpjs_component.jht_employer),
                        "reference_type": "BPJS Payment Component",
                        "reference_name": bpjs_component.name,
                        "user_remark": f"JHT Employer Liability for {bpjs_component.employee_name}"
                    })
            
            # JP Employer
            if flt(bpjs_component.jp_employer) > 0:
                if self.jp_employer_debit_account:
                    accounts.append({
                        "account": self.jp_employer_debit_account,
                        "debit_in_account_currency": flt(bpjs_component.jp_employer),
                        "reference_type": "BPJS Payment Component",
                        "reference_name": bpjs_component.name,
                        "user_remark": f"JP Employer Expense for {bpjs_component.employee_name}"
                    })
                    
                if self.jp_employer_credit_account:
                    accounts.append({
                        "account": self.jp_employer_credit_account,
                        "credit_in_account_currency": flt(bpjs_component.jp_employer),
                        "reference_type": "BPJS Payment Component",
                        "reference_name": bpjs_component.name,
                        "user_remark": f"JP Employer Liability for {bpjs_component.employee_name}"
                    })
            
            # JKK Employer
            if flt(bpjs_component.jkk) > 0:
                if self.jkk_employer_debit_account:
                    accounts.append({
                        "account": self.jkk_employer_debit_account,
                        "debit_in_account_currency": flt(bpjs_component.jkk),
                        "reference_type": "BPJS Payment Component",
                        "reference_name": bpjs_component.name,
                        "user_remark": f"JKK Expense for {bpjs_component.employee_name}"
                    })
                    
                if self.jkk_employer_credit_account:
                    accounts.append({
                        "account": self.jkk_employer_credit_account,
                        "credit_in_account_currency": flt(bpjs_component.jkk),
                        "reference_type": "BPJS Payment Component",
                        "reference_name": bpjs_component.name,
                        "user_remark": f"JKK Liability for {bpjs_component.employee_name}"
                    })
            
            # JKM Employer
            if flt(bpjs_component.jkm) > 0:
                if self.jkm_employer_debit_account:
                    accounts.append({
                        "account": self.jkm_employer_debit_account,
                        "debit_in_account_currency": flt(bpjs_component.jkm),
                        "reference_type": "BPJS Payment Component",
                        "reference_name": bpjs_component.name,
                        "user_remark": f"JKM Expense for {bpjs_component.employee_name}"
                    })
                    
                if self.jkm_employer_credit_account:
                    accounts.append({
                        "account": self.jkm_employer_credit_account,
                        "credit_in_account_currency": flt(bpjs_component.jkm),
                        "reference_type": "BPJS Payment Component",
                        "reference_name": bpjs_component.name,
                        "user_remark": f"JKM Liability for {bpjs_component.employee_name}"
                    })
            
            # Kesehatan Employer
            if flt(bpjs_component.kesehatan_employer) > 0:
                if self.kesehatan_employer_debit_account:
                    accounts.append({
                        "account": self.kesehatan_employer_debit_account,
                        "debit_in_account_currency": flt(bpjs_component.kesehatan_employer),
                        "reference_type": "BPJS Payment Component",
                        "reference_name": bpjs_component.name,
                        "user_remark": f"Kesehatan Employer Expense for {bpjs_component.employee_name}"
                    })
                    
                if self.kesehatan_employer_credit_account:
                    accounts.append({
                        "account": self.kesehatan_employer_credit_account,
                        "credit_in_account_currency": flt(bpjs_component.kesehatan_employer),
                        "reference_type": "BPJS Payment Component",
                        "reference_name": bpjs_component.name,
                        "user_remark": f"Kesehatan Employer Liability for {bpjs_component.employee_name}"
                    })
            
            # Verify we have accounts to create a journal entry
            if not accounts:
                frappe.msgprint(
                    _("No valid accounts found to create journal entry for BPJS component {0}").format(
                        bpjs_component.name
                    )
                )
                return None
            
            # Create the journal entry
            je = frappe.new_doc("Journal Entry")
            je.company = self.company
            je.posting_date = posting_date
            je.user_remark = f"BPJS payment for {bpjs_component.employee_name}"
            je.reference_type = "BPJS Payment Component"
            je.reference_name = bpjs_component.name
            
            for account in accounts:
                je.append("accounts", account)
            
            je.insert(ignore_permissions=True)
            
            # Link journal entry to BPJS component if field exists
            if hasattr(bpjs_component, 'journal_entry'):
                bpjs_component.journal_entry = je.name
                bpjs_component.save(ignore_permissions=True)
            
            return je.name
            
        except Exception as e:
            frappe.log_error(
                f"Error creating journal entry for BPJS component {bpjs_component.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Journal Entry Creation Error"
            )
            frappe.msgprint(_("Error creating journal entry: {0}").format(str(e)))
            return None