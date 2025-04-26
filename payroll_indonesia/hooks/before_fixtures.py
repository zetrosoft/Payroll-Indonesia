import frappe
import os
import json
from frappe.utils import cstr

def before_fixtures():
    """Get current state of Salary Structure to restore after fixtures load"""
    try:
        # Check if Salary Structure exists
        if frappe.db.exists("Salary Structure", "Struktur Gaji Tetap G1"):
            ss = frappe.get_doc("Salary Structure", "Struktur Gaji Tetap G1")
            
            # Get the actual Income Tax Slab that should be used
            tax_slab = frappe.db.get_value("Income Tax Slab", 
                                           {"currency": "IDR", "is_default": 1},
                                           "name")
            
            # Store current state in a JSON file
            state = {
                "name": ss.name,
                "docstatus": ss.docstatus,
                "company": ss.company if ss.company else "%",
                "income_tax_slab": tax_slab or getattr(ss, "income_tax_slab", None),
                "tax_calculation_method": getattr(ss, "tax_calculation_method", "Manual")
            }
            
            # Make sure directory exists
            os.makedirs(os.path.join(frappe.get_site_path("private", "fixtures")), exist_ok=True)
            
            # Save state to file
            with open(os.path.join(frappe.get_site_path("private", "fixtures"), "salary_structure_state.json"), "w") as f:
                json.dump(state, f, indent=4)
                
            frappe.log_error(f"Saved Salary Structure state: {state}", "Before Fixtures")
            
            # Print confirmation
            print(f"Saved Salary Structure state: {state}")
    except Exception as e:
        frappe.log_error(f"Error in before_fixtures: {cstr(e)}", "Fixture Error")