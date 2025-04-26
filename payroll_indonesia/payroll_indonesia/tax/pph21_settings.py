# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from payroll_indonesia.payroll_indonesia.utils import get_ptkp_settings

def on_update(doc, method):
    """Handler untuk event on_update pada PPh 21 Settings"""
    validate_brackets(doc)
    validate_ptkp_entries(doc)
    if doc.calculation_method == "TER":
        validate_ter_table()
        
def validate_brackets(doc):
    """Ensure tax brackets are continuous and non-overlapping"""
    if not doc.bracket_table:
        frappe.msgprint("At least one tax bracket should be defined")
        return
    
    # Sort by income_from
    sorted_brackets = sorted(doc.bracket_table, key=lambda x: x.income_from)
    
    # Check for gaps or overlaps
    for i in range(len(sorted_brackets) - 1):
        current = sorted_brackets[i]
        next_bracket = sorted_brackets[i + 1]
        
        if current.income_to != next_bracket.income_from:
            frappe.msgprint(f"Warning: Tax brackets should be continuous. Gap found between {current.income_to} and {next_bracket.income_from}")

def validate_ptkp_entries(doc):
    """Validate PTKP entries against required values"""
    required_status = ["TK0", "K0", "K1", "K2", "K3"]
    
    if not doc.ptkp_table:
        frappe.msgprint("PTKP values should be defined")
        return
    
    defined_status = [p.status_pajak for p in doc.ptkp_table]
    
    for status in required_status:
        if status not in defined_status:
            frappe.msgprint(f"Warning: Missing PTKP definition for status: {status}")

def validate_ter_table():
    """Validate TER table if TER method is selected"""
    count = frappe.db.count("PPh 21 TER Table")
    if count == 0:
        frappe.msgprint(
            _("Tarif Efektif Rata-rata (TER) belum didefinisikan di PPh 21 TER Table. "
              "Silakan isi tabel tersebut sebelum menggunakan metode ini."),
            indicator="yellow"
        )