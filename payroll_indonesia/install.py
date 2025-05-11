# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and Contributors
# See license.txt

import frappe
from frappe import _

def after_install():
    """Run after app installation"""
    setup_payroll_components()
    
def after_update():
    """Run after app update"""
    # Apply our salary slip enhancements
    from payroll_indonesia.override.salary_slip import extend_salary_slip_functionality
    extend_salary_slip_functionality()
    
def setup_payroll_components():
    """Set up required payroll components if missing"""
    # Create required salary components if they don't exist
    components = [
        # Earnings
        {"name": "Gaji Pokok", "type": "Earning", "abbr": "GP"},
        # Deductions
        {"name": "BPJS Kesehatan Employee", "type": "Deduction", "abbr": "BKE"},
        {"name": "BPJS JHT Employee", "type": "Deduction", "abbr": "BJE"},
        {"name": "BPJS JP Employee", "type": "Deduction", "abbr": "BPE"},
        {"name": "PPh 21", "type": "Deduction", "abbr": "PPh"}
    ]
    
    for comp in components:
        if not frappe.db.exists("Salary Component", comp["name"]):
            doc = frappe.new_doc("Salary Component")
            doc.salary_component = comp["name"]
            doc.salary_component_abbr = comp["abbr"]
            doc.type = comp["type"]
            doc.insert()
            
    frappe.db.commit()
    
    # Log completion
    frappe.log_error("Payroll Indonesia components setup completed", "Install")