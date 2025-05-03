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
        
        if not companies:
            frappe.logger().warning("No companies found. Skipping BPJS account creation.")
            return
        
        # Cek BPJS Settings, buat jika belum ada
        bpjs_settings = None
        if not frappe.db.exists("BPJS Settings", None):
            # Buat BPJS Settings baru
            try:
                bpjs_settings = frappe.new_doc("BPJS Settings")
                bpjs_settings.kesehatan_employee_percent = 1.0
                bpjs_settings.kesehatan_employer_percent = 4.0
                bpjs_settings.kesehatan_max_salary = 12000000
                bpjs_settings.jht_employee_percent = 2.0
                bpjs_settings.jht_employer_percent = 3.7
                bpjs_settings.jp_employee_percent = 1.0
                bpjs_settings.jp_employer_percent = 2.0
                bpjs_settings.jp_max_salary = 9077600
                bpjs_settings.jkk_percent = 0.24
                bpjs_settings.jkm_percent = 0.3
                bpjs_settings.insert(ignore_permissions=True)
                frappe.logger().info("Created default BPJS Settings")
            except Exception as e:
                frappe.log_error(f"Failed to create BPJS Settings: {str(e)}", "BPJS Setup Error")
        else:
            bpjs_settings = frappe.get_doc("BPJS Settings")
        
        # Jalankan setup_accounts setelah BPJS Settings dibuat
        if bpjs_settings:
            bpjs_settings.setup_accounts()
            
        # Buat Account Mapping untuk setiap company
        for company in companies:
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