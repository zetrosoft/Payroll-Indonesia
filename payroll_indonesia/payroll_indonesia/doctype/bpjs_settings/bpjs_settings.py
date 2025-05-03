# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import flt
from . import create_account, create_parent_account

class BPJSSettings(Document):
    def validate(self):
        """Validate BPJS settings"""
        self.validate_percentages()
        self.validate_max_salary()
        self.setup_accounts()
    
    def validate_percentages(self):
        """Validate BPJS percentage ranges"""
        validations = [
            ("kesehatan_employee_percent", 0, 5, "Persentase BPJS Kesehatan karyawan harus antara 0 dan 5%"),
            ("kesehatan_employer_percent", 0, 10, "Persentase BPJS Kesehatan perusahaan harus antara 0 dan 10%"),
            ("jht_employee_percent", 0, 5, "Persentase JHT karyawan harus antara 0 dan 5%"),
            ("jht_employer_percent", 0, 10, "Persentase JHT perusahaan harus antara 0 dan 10%"),
            ("jp_employee_percent", 0, 5, "Persentase JP karyawan harus antara 0 dan 5%"),
            ("jp_employer_percent", 0, 5, "Persentase JP perusahaan harus antara 0 dan 5%"),
            ("jkk_percent", 0, 5, "Persentase JKK harus antara 0 dan 5%"),
            ("jkm_percent", 0, 5, "Persentase JKM harus antara 0 dan 5%")
        ]
        
        for field, min_val, max_val, message in validations:
            value = flt(self.get(field))
            if value < min_val or value > max_val:
                frappe.throw(message)
    
    def validate_max_salary(self):
        """Validate maximum salary thresholds"""
        if flt(self.kesehatan_max_salary) <= 0:
            frappe.throw("Batas maksimal gaji BPJS Kesehatan harus lebih dari 0")
            
        if flt(self.jp_max_salary) <= 0:
            frappe.throw("Batas maksimal gaji JP harus lebih dari 0")
    
    def setup_accounts(self):
        """Setup GL accounts for BPJS components"""
        company = frappe.defaults.get_defaults().company
        if not company:
            frappe.throw("Please set default company in Global Defaults")
            
        # Parent account where BPJS accounts will be created
        parent_name = create_parent_account(company)
        
        # Define BPJS accounts to be created
        bpjs_accounts = {
            "kesehatan_account": {
                "account_name": "BPJS Kesehatan Payable",
                "account_type": "Payable",
                "field": "kesehatan_account"
            },
            "jht_account": {
                "account_name": "BPJS JHT Payable",
                "account_type": "Payable",
                "field": "jht_account"
            },
            "jp_account": {
                "account_name": "BPJS JP Payable",
                "account_type": "Payable",
                "field": "jp_account"
            },
            "jkk_account": {
                "account_name": "BPJS JKK Payable",
                "account_type": "Payable",
                "field": "jkk_account"
            },
            "jkm_account": {
                "account_name": "BPJS JKM Payable",
                "account_type": "Payable",
                "field": "jkm_account"
            }
        }
        
        # Create accounts and update settings using module-level function
        for key, account_info in bpjs_accounts.items():
            account = self.get(account_info["field"])
            if not account:
                account = create_account(
                    company=company,
                    account_name=account_info["account_name"],
                    account_type=account_info["account_type"],
                    parent=parent_name
                )
                self.set(account_info["field"], account)
    
    def on_update(self):
        """Update related documents when settings change"""
        # Update salary structure assignments if needed
        self.update_salary_structures()
    
    def update_salary_structures(self):
        """Update BPJS components in active salary structures"""
        # Get list of active salary structures
        salary_structures = frappe.get_all(
            "Salary Structure",
            filters={"docstatus": 1, "is_active": "Yes"},
            pluck="name"
        )
        
        for ss in salary_structures:
            doc = frappe.get_doc("Salary Structure", ss)
            # Logic to update BPJS components in salary structure
            # This would depend on your salary structure setup
            doc.save()