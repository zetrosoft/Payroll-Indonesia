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
        error_msg = str(e)[:100]
        frappe.log_error(f"Error loading BPJS defaults: {error_msg}", "BPJS Setup")
    
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
    try:
        frappe.logger().info("Starting BPJS setup after sync", "BPJS Setup")
        # Create required accounts and mappings
        create_bpjs_accounts()
    except Exception as e:
        # Limit error message length
        error_msg = str(e)[:100]
        frappe.log_error(f"After Sync Error: {error_msg}", "BPJS Setup")

def create_bpjs_accounts():
    """Create BPJS accounts for all companies"""
    try:
        # Get all companies
        companies = frappe.get_all("Company", pluck="name")
        
        if not companies:
            frappe.logger().warning("No companies found. Skipping BPJS account creation.", "BPJS Setup")
            return
        
        # Check if BPJS Settings exists, create if not
        bpjs_settings = None
        if not frappe.db.exists("BPJS Settings", "BPJS Settings"):
            # Create new BPJS Settings
            bpjs_settings = create_new_bpjs_settings()
        else:
            bpjs_settings = frappe.get_doc("BPJS Settings", "BPJS Settings")
        
        if not bpjs_settings:
            frappe.logger().error("Failed to get or create BPJS Settings", "BPJS Setup")
            return
            
        # Setup accounts after BPJS Settings is created
        setup_bpjs_accounts(bpjs_settings)
            
        # Create Account Mapping for each company
        create_company_mappings(companies)
        
        frappe.db.commit()
        frappe.logger().info("BPJS accounts and mappings created successfully", "BPJS Setup")
        
    except Exception as e:
        frappe.db.rollback()
        # Limit error message length
        error_msg = str(e)[:100]
        frappe.log_error(f"Error creating BPJS accounts: {error_msg}", "BPJS Setup")

def setup_bpjs_accounts(bpjs_settings):
    """Setup BPJS accounts using the settings document"""
    try:
        # Skip validation during initial setup
        original_flags = getattr(bpjs_settings, "flags", {})
        bpjs_settings.flags.ignore_validate = True
        
        # Call setup_accounts method
        bpjs_settings.setup_accounts()
        
        # Restore original flags
        bpjs_settings.flags = original_flags
        
        frappe.logger().info("BPJS accounts setup completed", "BPJS Setup")
    except Exception as e:
        # Limit error message length
        error_msg = str(e)[:100]
        frappe.log_error(f"Error in setup_accounts: {error_msg}", "BPJS Setup")

def create_company_mappings(companies):
    """Create BPJS account mappings for all companies"""
    failed_companies = []
    
    for company in companies:
        mapping_created = check_or_create_bpjs_mapping(company)
        if not mapping_created:
            failed_companies.append(company)
    
    if failed_companies:
        frappe.logger().warning(
            f"Failed to create BPJS mappings for {len(failed_companies)} companies", 
            "BPJS Setup"
        )
        # Schedule retry for failed companies
        schedule_mapping_retry(failed_companies)

def schedule_mapping_retry(companies):
    """Schedule background job to retry mapping creation"""
    if not companies:
        return
        
    try:
        frappe.enqueue(
            "payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.bpjs_settings.retry_bpjs_mapping",
            companies=companies,
            queue="long",
            timeout=1500
        )
        frappe.logger().info(f"Scheduled retry for {len(companies)} companies", "BPJS Setup")
    except Exception as e:
        # Limit error message length
        error_msg = str(e)[:100]
        frappe.log_error(
            f"Failed to schedule retry for BPJS mappings: {error_msg}", 
            "BPJS Setup"
        )

def create_new_bpjs_settings():
    """Create default BPJS Settings if not exists"""
    try:
        if frappe.db.exists("BPJS Settings", "BPJS Settings"):
            return frappe.get_doc("BPJS Settings", "BPJS Settings")
            
        # Get default values
        defaults = get_default_bpjs_values()
        
        # Create new document
        settings = frappe.new_doc("BPJS Settings")
        
        # Set values from defaults
        for key, value in defaults.items():
            if hasattr(settings, key):
                settings.set(key, value)
        
        # Set flags for bypass validation during setup
        settings.flags.ignore_validate = True
        settings.flags.ignore_mandatory = True
        settings.insert(ignore_permissions=True)
        frappe.db.commit()
        
        frappe.logger().info("Created default BPJS Settings", "BPJS Setup")
        return settings
        
    except Exception as e:
        # Limit error message length
        error_msg = str(e)[:100]
        frappe.log_error(f"BPJS Settings Setup Error: {error_msg}", "BPJS Setup")
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
                    frappe.logger().info(f"Created BPJS Account Mapping for {company}", "BPJS Setup")
                    return True
                else:
                    frappe.logger().warning(f"Failed to create BPJS Account Mapping for {company}", "BPJS Setup")
                    return False
            except ImportError:
                frappe.log_error("Could not import create_default_mapping", "BPJS Setup")
                return False
            except Exception as e:
                # Limit error message length
                error_msg = str(e)[:100]
                frappe.log_error(f"Error creating mapping for {company}: {error_msg}", "BPJS Setup")
                return False
        return True
                
    except Exception as e:
        # Limit error message length
        error_msg = str(e)[:100]
        frappe.log_error(f"Error checking mapping for {company}: {error_msg}", "BPJS Setup")
        return False