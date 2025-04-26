# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _

def process_fixtures():
    """
    Function to process fixtures after migration
    This should be called in after_migrate hook
    """
    fix_salary_structure_submit_status()
    
def fix_salary_structure_submit_status():
    """
    Fix Salary Structure submit status after migration
    This handles the case where fixtures reset a submitted Salary Structure to draft
    """
    frappe.log_error("Fixing Salary Structure submit status", "Fixture Handling")
    
    # Define structures that should be in submit status
    structures_to_submit = [
        {
            "name": "Struktur Gaji Tetap G1",
            "company": frappe.defaults.get_global_default("company") or "%",
            "update_fields": {
                "income_tax_slab": frappe.db.get_value("Income Tax Slab", {"currency": "IDR", "is_default": 1}, "name"),
                "tax_calculation_method": "Manual"
            }
        }
        # Add more structures here if needed
    ]
    
    for structure in structures_to_submit:
        if frappe.db.exists("Salary Structure", structure["name"]):
            ss = frappe.get_doc("Salary Structure", structure["name"])
            
            needs_update = False
            
            # Check if company needs to be updated
            if ss.company != structure["company"] and structure["company"] != "%":
                frappe.db.set_value("Salary Structure", structure["name"], "company", structure["company"])
                needs_update = True
                frappe.log_error(f"Updated company for {structure['name']}", "Fixture Fix")
            
            # Update additional fields if needed
            if "update_fields" in structure:
                for field, value in structure["update_fields"].items():
                    if value and getattr(ss, field, None) != value:
                        frappe.db.set_value("Salary Structure", structure["name"], field, value)
                        needs_update = True
                        frappe.log_error(f"Updated {field} for {structure['name']}", "Fixture Fix")
            
            # Check docstatus and submit if needed
            if ss.docstatus == 0:  # If in draft state
                try:
                    # Submit the document directly in database
                    frappe.db.set_value("Salary Structure", structure["name"], "docstatus", 1)
                    frappe.log_error(f"Submitted {structure['name']}", "Fixture Fix")
                    
                    # If the document has any amended_from, clear it to avoid confusion
                    if ss.amended_from:
                        frappe.db.set_value("Salary Structure", structure["name"], "amended_from", None)
                        
                except Exception as e:
                    frappe.log_error(f"Error submitting {structure['name']}: {str(e)}", "Fixture Fix Error")
    
    frappe.db.commit()
    frappe.log_error("Completed fixing Salary Structure submit status", "Fixture Handling")