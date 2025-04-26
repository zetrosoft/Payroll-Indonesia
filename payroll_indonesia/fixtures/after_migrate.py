# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
import os
import json
from frappe import _
from frappe.utils import cstr

def process_fixtures():
    """
    Function to process fixtures after migration
    This should be called in after_migrate hook
    """
    # Perbaiki struktur company, tax_slab, dan status submit
    fix_salary_structure()
    # Perbaiki file hooks.py jika perlu
    fix_hooks_file()
    
def fix_salary_structure():
    """
    Fix Salary Structure company, tax_slab, dan submit status
    Menggabungkan logika dari patches dan after_migrate
    """
    frappe.log_error("Fixing Salary Structure", "After Migrate")
    print("Fixing Salary Structure...")
    
    try:
        # First try to restore from saved state
        restored = restore_from_saved_state()
        
        # Whether restored or not, fix using defaults too
        fix_using_defaults()
        
        frappe.db.commit()
        print("Completed fixing Salary Structure")
        frappe.log_error("Completed fixing Salary Structure", "After Migrate")
        
    except Exception as e:
        frappe.log_error(f"Error in fix_salary_structure: {cstr(e)}", "After Migrate Error")
        print(f"Error: {str(e)}")

def restore_from_saved_state():
    """Restore Salary Structure from previously saved state"""
    state_file_path = os.path.join(frappe.get_site_path("private", "fixtures"), "salary_structure_state.json")
    
    if os.path.exists(state_file_path):
        try:
            # Load saved state
            with open(state_file_path, "r") as f:
                state = json.load(f)
            
            print(f"Restoring from saved state: {state}")
            
            # Update document if it exists
            if frappe.db.exists("Salary Structure", state["name"]):
                # Get default Income Tax Slab
                tax_slab = get_default_tax_slab()
                
                # Update fields
                frappe.db.set_value("Salary Structure", state["name"], {
                    "company": state.get("company", "%"),
                    "income_tax_slab": tax_slab,
                    "tax_calculation_method": "Manual",
                    "docstatus": state.get("docstatus", 1)  # Default to submitted if not specified
                })
                
                print(f"Restored {state['name']} from saved state")
                return True
        except Exception as e:
            frappe.log_error(f"Error restoring from saved state: {cstr(e)}", "After Migrate Error")
    
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
    ]
    
    for structure in structures_to_submit:
        if frappe.db.exists("Salary Structure", structure["name"]):
            ss = frappe.get_doc("Salary Structure", structure["name"])
            
            needs_update = False
            
            # Check if company needs to be updated
            if ss.company != structure["company"]:
                frappe.db.set_value("Salary Structure", structure["name"], "company", structure["company"])
                needs_update = True
                print(f"Updated company for {structure['name']} to {structure['company']}")
            
            # Update additional fields if needed
            if "update_fields" in structure:
                for field, value in structure["update_fields"].items():
                    if value and getattr(ss, field, None) != value:
                        frappe.db.set_value("Salary Structure", structure["name"], field, value)
                        needs_update = True
                        print(f"Updated {field} for {structure['name']} to {value}")
            
            # Check docstatus and submit if needed
            if ss.docstatus == 0:  # If in draft state
                try:
                    # Submit the document directly in database
                    frappe.db.set_value("Salary Structure", structure["name"], "docstatus", 1)
                    print(f"Submitted {structure['name']}")
                    
                    # If the document has any amended_from, clear it to avoid confusion
                    if ss.amended_from:
                        frappe.db.set_value("Salary Structure", structure["name"], "amended_from", None)
                        
                except Exception as e:
                    frappe.log_error(f"Error submitting {structure['name']}: {cstr(e)}", "After Migrate Error")

def get_default_tax_slab():
    """Get default Income Tax Slab for IDR"""
    try:
        # Try to check if is_default column exists
        has_is_default = check_column_exists("Income Tax Slab", "is_default")
        
        if has_is_default:
            # If is_default column exists, use it to find default slab
            tax_slab = frappe.db.get_value("Income Tax Slab", 
                                          {"currency": "IDR", "is_default": 1}, 
                                          "name")
            if tax_slab:
                return tax_slab
                
        # Otherwise, find any IDR tax slab
        tax_slabs = frappe.get_all("Income Tax Slab", 
                                  filters={"currency": "IDR"}, 
                                  fields=["name"])
        if tax_slabs:
            return tax_slabs[0].name
            
        # If no tax slab exists, return None but don't try to create one
        # Let the system handle this case
        return None
        
    except Exception as e:
        frappe.log_error(f"Error getting default tax slab: {cstr(e)}", "After Migrate Error")
        return None

def check_column_exists(doctype, column):
    """Check if column exists in DocType"""
    try:
        frappe.db.sql(f"SELECT `{column}` FROM `tab{doctype}` LIMIT 1")
        return True
    except Exception:
        return False

def fix_hooks_file():
    """Fix app_title in hooks.py if needed"""
    try:
        hooks_file = frappe.get_app_path("payroll_indonesia", "hooks.py")
        if os.path.exists(hooks_file):
            # Read content
            with open(hooks_file, "r") as f:
                content = f.read()
                
            # Check if app_title needs fixing
            if 'app_title = "Payroll Indonesia"' in content:
                # Fix it
                content = content.replace(
                    'app_title = "Payroll Indonesia"', 
                    'app_title = ["Payroll Indonesia"]'
                )
                
                # Write back
                with open(hooks_file, "w") as f:
                    f.write(content)
                    
                print("Fixed app_title in hooks.py")
    except Exception as e:
        frappe.log_error(f"Error fixing hooks file: {cstr(e)}", "After Migrate Error")