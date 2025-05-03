import frappe
from frappe import _

def check_bpjs_settings():
    """Daily check for BPJS settings and mappings"""
    try:
        # Check if BPJS Settings exists
        if not frappe.db.exists("BPJS Settings", None):
            frappe.logger().warning("BPJS Settings not found")
            return
            
        # Get all companies
        companies = frappe.get_all("Company", pluck="name")
        
        for company in companies:
            # Check BPJS Account Mapping
            mapping = frappe.db.exists("BPJS Account Mapping", {"company": company})
            if not mapping:
                frappe.logger().warning(f"BPJS Account Mapping missing for company: {company}")
                
                # Try to create default mapping
                from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import create_default_mapping
                if create_default_mapping(company):
                    frappe.logger().info(f"Created default BPJS Account Mapping for company: {company}")
                    
        frappe.logger().info("Completed daily BPJS settings check")
                    
    except Exception as e:
        frappe.log_error(f"Error in daily BPJS settings check: {str(e)}", "BPJS Daily Task Error")