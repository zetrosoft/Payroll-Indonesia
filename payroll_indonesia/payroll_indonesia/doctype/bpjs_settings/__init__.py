# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import flt

def create_account(company, account_name, account_type, parent):
    """Create GL Account if not exists - Module level function"""
    abbr = frappe.get_cached_value('Company',  company,  'abbr')
    account_name = f"{account_name} - {abbr}"
    
    if not frappe.db.exists("Account", account_name):
        doc = frappe.get_doc({
            "doctype": "Account",
            "account_name": account_name.replace(f" - {abbr}", ""),
            "company": company,
            "parent_account": parent,
            "account_type": account_type,
            "account_currency": frappe.get_cached_value('Company', company, 'default_currency'),
            "is_group": 0
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        frappe.msgprint(f"Created account: {account_name}")
    
    return account_name

def create_parent_account(company):
    """Create or get parent account for BPJS accounts - Module level function"""
    parent_account = "Duties and Taxes - " + frappe.get_cached_value('Company',  company,  'abbr')
    parent_name = "BPJS Payable - " + frappe.get_cached_value('Company',  company,  'abbr')
    
    if not frappe.db.exists("Account", parent_name):
        frappe.get_doc({
            "doctype": "Account",
            "account_name": "BPJS Payable",
            "parent_account": parent_account,
            "company": company,
            "account_type": "Payable",
            "account_currency": frappe.get_cached_value('Company', company, 'default_currency'),
            "is_group": 1
        }).insert(ignore_permissions=True)
    
    return parent_name