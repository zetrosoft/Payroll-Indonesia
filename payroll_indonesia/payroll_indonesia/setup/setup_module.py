import frappe
from frappe import _

def after_sync():
    """Run after app sync/migration"""
    # Create required accounts and mappings
    create_bpjs_accounts()

def create_bpjs_accounts():
    """Create BPJS accounts for all companies"""
    try:
        # Get all companies
        companies = frappe.get_all("Company", pluck="name")
        
        for company in companies:
            # Check BPJS Settings
            if not frappe.db.exists("BPJS Settings", None):
                create_default_bpjs_settings()
            
            # Create/check BPJS Account Mapping
            check_or_create_bpjs_mapping(company)
            
        frappe.db.commit()
        frappe.logger().info("BPJS accounts and mappings created successfully")
        
    except Exception as e:
        frappe.log_error(f"Error creating BPJS accounts: {str(e)}", "BPJS Setup Error")

def create_default_bpjs_settings():
    """Create default BPJS Settings if not exists"""
    try:
        settings = frappe.new_doc("BPJS Settings")
        settings.kesehatan_employee_percent = 1.0
        settings.kesehatan_employer_percent = 4.0
        settings.kesehatan_max_salary = 12000000
        settings.jht_employee_percent = 2.0
        settings.jht_employer_percent = 3.7
        settings.jp_employee_percent = 1.0
        settings.jp_employer_percent = 2.0
        settings.jp_max_salary = 9077600
        settings.jkk_percent = 0.24
        settings.jkm_percent = 0.3
        settings.insert(ignore_permissions=True)
        settings.setup_accounts()
        
        frappe.logger().info("Created default BPJS Settings")
        
    except Exception as e:
        frappe.log_error(f"Error creating default BPJS Settings: {str(e)}", "BPJS Setup Error")

def check_or_create_bpjs_mapping(company):
    """Create BPJS Account Mapping for company if not exists"""
    try:
        mapping_exists = frappe.db.exists("BPJS Account Mapping", {"company": company})
        
        if not mapping_exists:
            from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import create_default_mapping
            
            mapping_name = create_default_mapping(company)
            if mapping_name:
                frappe.logger().info(f"Created BPJS Account Mapping for {company}: {mapping_name}")
            else:
                frappe.logger().warning(f"Failed to create BPJS Account Mapping for {company}")
                
    except Exception as e:
        frappe.log_error(f"Error checking/creating BPJS mapping for {company}: {str(e)}", "BPJS Setup Error")