# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 08:11:50 by dannyaudian

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

@frappe.whitelist(allow_guest=False)
def get_employee(name=None, filters=None):
    """API to get employee data"""
    if name:
        return frappe.get_doc("Employee", name)
    
    filters = filters or {}
    return frappe.get_all("Employee", filters=filters, fields=["*"])

@frappe.whitelist(allow_guest=False)
def create_employee(data):
    """API to create an employee"""
    if not frappe.has_permission("Employee", "create"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
        
    try:
        doc = frappe.new_doc("Employee")
        for key, value in data.items():
            if hasattr(doc, key):
                doc.set(key, value)
        
        doc.insert()
        return doc
    except Exception as e:
        frappe.throw(_("Error creating Employee: {0}").format(str(e)))

@frappe.whitelist(allow_guest=False)
def get_salary_slip(name=None, filters=None):
    """API to get salary slip data"""
    if name:
        return frappe.get_doc("Salary Slip", name)
    
    filters = filters or {}
    return frappe.get_all("Salary Slip", filters=filters, fields=["*"])

@frappe.whitelist(allow_guest=False)
def create_salary_slip(data):
    """API to create a salary slip"""
    if not frappe.has_permission("Salary Slip", "create"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
        
    try:
        doc = frappe.new_doc("Salary Slip")
        for key, value in data.items():
            if hasattr(doc, key):
                doc.set(key, value)
        
        doc.insert()
        return doc
    except Exception as e:
        frappe.throw(_("Error creating Salary Slip: {0}").format(str(e)))

@frappe.whitelist(allow_guest=False)
def get_bpjs_summary(name=None, filters=None):
    """API to get BPJS Payment Summary data"""
    if name:
        return frappe.get_doc("BPJS Payment Summary", name)
    
    filters = filters or {}
    return frappe.get_all("BPJS Payment Summary", filters=filters, fields=["*"])

@frappe.whitelist(allow_guest=False)
def create_bpjs_summary(data):
    """API to create a BPJS Payment Summary"""
    if not frappe.has_permission("BPJS Payment Summary", "create"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
        
    try:
        doc = frappe.new_doc("BPJS Payment Summary")
        for key, value in data.items():
            if hasattr(doc, key):
                doc.set(key, value)
        
        doc.insert()
        return doc
    except Exception as e:
        frappe.throw(_("Error creating BPJS Payment Summary: {0}").format(str(e)))

@frappe.whitelist(allow_guest=False)
def get_tax_summary(name=None, filters=None):
    """API to get Employee Tax Summary data"""
    if name:
        return frappe.get_doc("Employee Tax Summary", name)
    
    filters = filters or {}
    return frappe.get_all("Employee Tax Summary", filters=filters, fields=["*"])