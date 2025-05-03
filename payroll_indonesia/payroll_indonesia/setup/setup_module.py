import frappe
from frappe import _
import json
import os
from frappe.utils import flt

# Constants for default values
DEFAULT_CONFIG_PATH = "payroll_indonesia/payroll_indonesia/config/bpjs_defaults.json"

def get_default_bpjs_values():
    """Load default BPJS values from config file or use fallback defaults"""
    try:
        # Try to load from config file
        if os.path.exists(frappe.get_app_path("payroll_indonesia", DEFAULT_CONFIG_PATH)):
            with open(frappe.get_app_path("payroll_indonesia", DEFAULT_CONFIG_PATH)) as f:
                return json.load(f)
    except Exception as e:
        frappe.log_error(str(e), tag="BPJS Setup")
    
    # Fallback defaults if config file is missing or invalid
    return {
        "kesehatan_employee_percent": 1.0,
        "kesehatan_employer_percent": 4.0,
        "kesehatan_max_salary": 12000000.0,
        "jht_employee_percent": 2.0,
        "jht_employer_percent": 3.7,
        "jp_employee_percent": 1.0,
        "jp_employer_percent": 2.0,
        "jp_max_salary": 9077600.0,
        "jkk_percent": 0.24,
        "jkm_percent": 0.3
    }

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
            frappe.logger().warning("No companies found. Skipping BPJS account creation.", tag="BPJS Setup")
            return
        
        # Check if BPJS Settings exists, create if not
        bpjs_settings = None
        if not frappe.db.exists("BPJS Settings", None):
            # Create new BPJS Settings using helper function
            bpjs_settings = create_new_bpjs_settings()
        else:
            bpjs_settings = frappe.get_doc("BPJS Settings")
        
        # Setup accounts after BPJS Settings is created
        if bpjs_settings:
            try:
                bpjs_settings.setup_accounts()
                frappe.logger().info("BPJS accounts setup completed", tag="BPJS Setup")
            except Exception as setup_error:
                frappe.log_error(
                    f"Error in setup_accounts: {str(setup_error)}", 
                    "BPJS Accounts Setup Error"
                )
                raise
            
        # Create Account Mapping for each company
        failed_companies = []
        for company in companies:
            mapping_created = check_or_create_bpjs_mapping(company)
            if not mapping_created:
                failed_companies.append(company)
            
        if failed_companies:
            frappe.logger().warning(
                f"Failed to create BPJS mappings for companies: {', '.join(failed_companies)}", 
                tag="BPJS Setup"
            )
            # Schedule retry for failed companies
            try:
                frappe.enqueue(
                    "payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.bpjs_settings.retry_bpjs_mapping",
                    companies=failed_companies,
                    queue="long",
                    timeout=1500
                )
            except Exception as enqueue_error:
                frappe.log_error(
                    f"Failed to schedule retry for BPJS mappings: {str(enqueue_error)}", 
                    "BPJS Setup Error"
                )
        
        frappe.db.commit()
        frappe.logger().info("BPJS accounts and mappings created successfully", tag="BPJS Setup")
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error creating BPJS accounts: {str(e)}", "BPJS Setup Error")

def create_new_bpjs_settings():
    """Helper function to create new BPJS Settings with default values"""
    try:
        defaults = get_default_bpjs_values()
        
        settings = frappe.new_doc("BPJS Settings")
        settings.update(defaults)
        settings.insert(ignore_permissions=True)
        
        frappe.logger().info("Created default BPJS Settings", tag="BPJS Setup")
        return settings
        
    except Exception as e:
        frappe.log_error(f"Error creating default BPJS Settings: {str(e)}", "BPJS Setup Error")
        return None

def check_or_create_bpjs_mapping(company):
    """Create BPJS Account Mapping for company if not exists"""
    try:
        mapping_exists = frappe.db.exists("BPJS Account Mapping", {"company": company})
        
        if not mapping_exists:
            try:
                from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import create_default_mapping
                
                mapping_name = create_default_mapping(company)
                if mapping_name:
                    frappe.logger().info(f"Created BPJS Account Mapping for {company}: {mapping_name}", tag="BPJS Setup")
                    return True
                else:
                    frappe.logger().warning(f"Failed to create BPJS Account Mapping for {company}", tag="BPJS Setup")
                    return False
            except ImportError as import_error:
                frappe.log_error(
                    f"Could not import create_default_mapping: {str(import_error)}", 
                    "BPJS Mapping Import Error"
                )
                return False
        return True
                
    except Exception as e:
        frappe.log_error(f"Error checking/creating BPJS mapping for {company}: {str(e)}", "BPJS Setup Error")
        return False