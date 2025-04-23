# -*- coding: utf-8 -*-
# Copyright (c) 2025, Danny Audian and contributors
# For license information, please see license.txt
# Last modified: 2025-04-23 12:17:47 by dannyaudian

import frappe
from frappe import _

def get_ter_rate(employee_doc, monthly_income):
    """
    Get TER (Tarif Efektif Rata-rata) rate for employee based on status and income
    
    Args:
        employee_doc (Employee): Employee document or dict with status_pajak field
        monthly_income (float): Monthly gross income amount
    
    Returns:
        float: TER rate (as decimal, e.g. 0.05 for 5%)
    """
    if not employee_doc:
        frappe.throw(_("Employee document is required to calculate TER rate"))
    
    status_pajak = employee_doc.get('status_pajak')
    if not status_pajak:
        frappe.throw(_("Employee tax status (Status Pajak) is not set"))
    
    # Query the TER table for matching bracket
    ter = frappe.db.sql("""
        SELECT rate
        FROM `tabPPh 21 TER Table`
        WHERE status_pajak = %s
          AND %s >= income_from
          AND (%s <= income_to OR income_to = 0)
        LIMIT 1
    """, (status_pajak, monthly_income, monthly_income), as_dict=1)
    
    if not ter:
        frappe.throw(_(
            "No TER rate found for status {0} and income {1}. "
            "Please check PPh 21 TER Table settings."
        ).format(status_pajak, frappe.format(monthly_income, {"fieldtype": "Currency"})))
    
    # Convert percent to decimal (e.g., 5% to 0.05)
    return float(ter[0].rate) / 100.0

def calculate_pph21_with_ter(employee, monthly_income):
    """
    Calculate PPh 21 amount using TER method
    
    Args:
        employee (string or dict): Employee ID or document
        monthly_income (float): Monthly gross income amount
    
    Returns:
        float: PPh 21 amount to be deducted
    """
    # Ensure we have employee document
    if isinstance(employee, str):
        employee_doc = frappe.get_doc("Employee", employee)
    else:
        employee_doc = employee
    
    # Get TER rate for this employee and income
    ter_rate = get_ter_rate(employee_doc, monthly_income)
    
    # Simply multiply income by TER rate
    pph21_amount = monthly_income * ter_rate
    
    return pph21_amount

def setup_default_ter_rates():
    """Setup default TER rates based on PMK 168/2023"""
    # Sample rates based on PMK 168/2023
    default_rates = [
        # TK0 - Tidak Kawin 0 Tanggungan
        {"status_pajak": "TK0", "income_from": 0, "income_to": 5000000, "rate": 0.0},
        {"status_pajak": "TK0", "income_from": 5000000, "income_to": 10000000, "rate": 2.5},
        {"status_pajak": "TK0", "income_from": 10000000, "income_to": 20000000, "rate": 4.5},
        {"status_pajak": "TK0", "income_from": 20000000, "income_to": 0, "rate": 7.5, "is_highest_bracket": 1},
        
        # K0 - Kawin 0 Tanggungan
        {"status_pajak": "K0", "income_from": 0, "income_to": 5500000, "rate": 0.0},
        {"status_pajak": "K0", "income_from": 5500000, "income_to": 11000000, "rate": 2.0},
        {"status_pajak": "K0", "income_from": 11000000, "income_to": 22000000, "rate": 4.0},
        {"status_pajak": "K0", "income_from": 22000000, "income_to": 0, "rate": 7.0, "is_highest_bracket": 1},
        
        # Tambahkan status dan range lainnya sesuai PMK 168/2023
    ]
    
    # Create TER rate records if they don't exist
    for rate_data in default_rates:
        if not frappe.db.exists(
            "PPh 21 TER Table",
            {
                "status_pajak": rate_data["status_pajak"],
                "income_from": rate_data["income_from"],
                "income_to": rate_data["income_to"]
            }
        ):
            doc = frappe.new_doc("PPh 21 TER Table")
            doc.update(rate_data)
            doc.insert()
    
    frappe.msgprint(_("Default TER rates set up based on PMK 168/2023"))