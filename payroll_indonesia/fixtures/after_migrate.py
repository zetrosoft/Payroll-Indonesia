# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
import os
import json
from frappe import _
from frappe.utils import cstr
from payroll_indonesia.utilities.tax_slab import get_default_tax_slab

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
    
    try:
        # First, try to restore from saved state
        restore_from_saved_state()
        
        # If no saved state or restore failed, fix using predefined values
        fix_using_defaults()
        
        frappe.db.commit()
        frappe.log_error("Completed fixing Salary Structure submit status", "Fixture Handling")
        
    except Exception as e:
        frappe.log_error(f"Error in fix_salary_structure_submit_status: {cstr(e)}", "Fixture Error")

def restore_from_saved_state():
    """Restore Salary Structure from previously saved state"""
    state_file_path = os.path.join(frappe.get_site_path("private", "fixtures"), "salary_structure_state.json")
    
    if os.path.exists(state_file_path):
        try:
            # Load saved state
            with open(state_file_path, "r") as f:
                state = json.load(f)
            
            frappe.log_error(f"Loaded saved state: {state}", "Fixture Handling")
            
            # Update document if it exists
            if frappe.db.exists("Salary Structure", state["name"]):
                # Get actual Income Tax Slab if needed
                if not state.get("income_tax_slab"):
                    state["income_tax_slab"] = get_default_tax_slab()
                
                # Update fields
                frappe.db.set_value("Salary Structure", state["name"], {
                    "company": state.get("company", "%"),
                    "income_tax_slab": state.get("income_tax_slab"),
                    "tax_calculation_method": state.get("tax_calculation_method", "Manual"),
                    "docstatus": state.get("docstatus", 1)  # Default to submitted if not specified
                })
                
                frappe.log_error(f"Restored {state['name']} from saved state", "Fixture Handling")
                return True
        except Exception as e:
            frappe.log_error(f"Error restoring from saved state: {cstr(e)}", "Fixture Error")
    
    return False

def fix_using_defaults():
    """Fix Salary Structure using default values"""
    # Get default Income Tax Slab
    tax_slab = get_default_tax_slab()
    
    # Define structures that should be in submit status
    structures_to_submit = [
        {
            "name": "Struktur Gaji Tetap G1",
            "company": "%",  # Keep as % for universal usage
            "update_fields": {
                "income_tax_slab": tax_slab,
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
            if ss.company != structure["company"]:
                frappe.db.set_value("Salary Structure", structure["name"], "company", structure["company"])
                needs_update = True
                frappe.log_error(f"Updated company for {structure['name']} to {structure['company']}", "Fixture Fix")
            
            # Update additional fields if needed
            if "update_fields" in structure:
                for field, value in structure["update_fields"].items():
                    if value and getattr(ss, field, None) != value:
                        frappe.db.set_value("Salary Structure", structure["name"], field, value)
                        needs_update = True
                        frappe.log_error(f"Updated {field} for {structure['name']} to {value}", "Fixture Fix")
            
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
                    frappe.log_error(f"Error submitting {structure['name']}: {cstr(e)}", "Fixture Fix Error")