import frappe
import os
import json

def before_fixtures():
    """Get current state of Salary Structure to restore after fixtures load"""
    # Check if Salary Structure exists
    if frappe.db.exists("Salary Structure", "Struktur Gaji Tetap G1"):
        ss = frappe.get_doc("Salary Structure", "Struktur Gaji Tetap G1")
        
        # Store current state in a JSON file
        state = {
            "name": ss.name,
            "docstatus": ss.docstatus,
            "company": ss.company,
            "income_tax_slab": ss.income_tax_slab if hasattr(ss, "income_tax_slab") else None,
            "tax_calculation_method": ss.tax_calculation_method
        }
        
        # Make sure directory exists
        os.makedirs(os.path.join(frappe.get_site_path("private", "fixtures")), exist_ok=True)
        
        # Save state to file
        with open(os.path.join(frappe.get_site_path("private", "fixtures"), "salary_structure_state.json"), "w") as f:
            json.dump(state, f, indent=4)
            
        frappe.log_error(f"Saved Salary Structure state: {state}", "Before Fixtures")