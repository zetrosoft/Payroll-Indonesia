import frappe
from frappe import _

def validate_bpjs_supplier():
    """Ensure BPJS supplier exists with correct configuration"""
    if not frappe.db.exists("Supplier", "BPJS"):
        # Create BPJS supplier if it doesn't exist
        supplier = frappe.new_doc("Supplier")
        supplier.supplier_name = "BPJS"
        supplier.supplier_group = "Services"  # Adjust as needed
        supplier.supplier_type = "Company"
        supplier.insert()
        
        frappe.msgprint(_("Created default BPJS supplier"))