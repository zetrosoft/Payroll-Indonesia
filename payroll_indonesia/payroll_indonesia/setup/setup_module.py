import frappe
from frappe import _
import json
import os
from frappe.utils import flt

# Constants for default values
DEFAULT_CONFIG_PATH = "payroll_indonesia/payroll_indonesia/config/bpjs_defaults.json"
DEFAULT_BPJS_VALUES = {
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

def get_default_bpjs_values():
    """
    Load default BPJS values from config file or use fallback defaults
    Returns dict of default values
    """
    try:
        config_path = frappe.get_app_path("payroll_indonesia", DEFAULT_CONFIG_PATH)
        if os.path.exists(config_path):
            with open(config_path) as f:
                values = json.load(f)
                # Validate loaded values
                for key in DEFAULT_BPJS_VALUES:
                    if key not in values:
                        values[key] = DEFAULT_BPJS_VALUES[key]
                return values
    except Exception as e:
        frappe.log_error(f"Error loading BPJS defaults: {str(e)[:100]}", "BPJS Setup")
    
    # Return hardcoded defaults if config file missing/invalid
    return DEFAULT_BPJS_VALUES

def after_sync():
    """
    Run after app sync/migration
    Registered in hooks.py under after_migrate
    """
    try:
        frappe.logger().info("Starting BPJS post-migration setup", tag="BPJS Setup")
        success = create_bpjs_accounts()
        if success:
            frappe.logger().info("BPJS setup completed successfully", tag="BPJS Setup")
        else:
            frappe.logger().warning("BPJS setup completed with warnings", tag="BPJS Setup")
    except Exception as e:
        frappe.log_error(f"BPJS Setup Error: {str(e)[:100]}", "BPJS Setup")
        raise

def create_bpjs_accounts():
    """
    Create BPJS accounts for all companies
    Returns bool indicating complete success
    """
    try:
        # Get all companies
        companies = frappe.get_all("Company", pluck="name")
        if not companies:
            frappe.logger().warning("No companies found, skipping BPJS setup", tag="BPJS Setup")
            return False

        # Create/get BPJS Settings
        bpjs_settings = create_new_bpjs_settings()
        if not bpjs_settings:
            frappe.logger().error("Failed to create BPJS Settings", tag="BPJS Setup")
            return False

        # Setup accounts and mappings
        success = True
        for company in companies:
            if not setup_company_bpjs(company, bpjs_settings):
                success = False

        frappe.db.commit()
        return success

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error in create_bpjs_accounts: {str(e)[:100]}", "BPJS Setup")
        return False

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

def create_company_mapping(company):
    """
    Create BPJS Account Mapping for company
    Returns bool indicating success
    """
    try:
        if frappe.db.exists("BPJS Account Mapping", {"company": company}):
            return True

        try:
            # Import here to avoid circular imports
            from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import create_default_mapping
        except ImportError:
            frappe.log_error("Could not import create_default_mapping", "BPJS Setup")
            return False

        mapping_name = create_default_mapping(company)
        if mapping_name:
            frappe.logger().info(f"Created BPJS mapping for {company}", tag="BPJS Setup")
            return True
        else:
            frappe.logger().warning(f"Failed to create BPJS mapping for {company}", tag="BPJS Setup")
            return False

    except Exception as e:
        frappe.log_error(f"Error creating mapping for {company}: {str(e)[:100]}", "BPJS Setup")
        return False

def schedule_mapping_retry(companies):
    """Schedule background job to retry failed mappings"""
    if not companies:
        return
        
    try:
        frappe.enqueue(
            "payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.bpjs_settings.retry_bpjs_mapping",
            companies=companies,
            queue="long",
            timeout=1500
        )
        frappe.logger().info(f"Scheduled mapping retry for: {', '.join(companies)}", tag="BPJS Setup")
    except Exception as e:
        frappe.log_error(f"Failed to schedule mapping retry: {str(e)[:100]}", "BPJS Setup")

def create_new_bpjs_settings():
    """
    Create default BPJS Settings if not exists
    Returns BPJS Settings doc or None if failed
    """
    try:
        # Check if settings already exist
        if frappe.db.exists("BPJS Settings", "BPJS Settings"):
            settings = frappe.get_doc("BPJS Settings", "BPJS Settings")
            frappe.logger().info("Using existing BPJS Settings", tag="BPJS Setup")
            return settings

        # Create new settings
        defaults = get_default_bpjs_values()
        settings = frappe.new_doc("BPJS Settings")
        
        # Set values from defaults
        for key, value in defaults.items():
            if hasattr(settings, key):
                settings.set(key, flt(value))

        # Bypass validation during setup
        settings.flags.ignore_validate = True
        settings.flags.ignore_mandatory = True
        settings.insert(ignore_permissions=True)
        
        frappe.db.commit()
        frappe.logger().info("Created new BPJS Settings", tag="BPJS Setup")
        return settings

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error creating BPJS Settings: {str(e)[:100]}", "BPJS Setup")
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

def setup_company_bpjs(company, bpjs_settings):
    """
    Setup BPJS accounts and mapping for a single company
    Returns bool indicating success
    """
    try:
        # Setup accounts
        if hasattr(bpjs_settings, "setup_accounts"):
            try:
                original_flags = getattr(bpjs_settings, "flags", {})
                bpjs_settings.flags.ignore_validate = True
                bpjs_settings.setup_accounts()
                bpjs_settings.flags = original_flags
            except Exception as e:
                frappe.log_error(f"Error setting up accounts for {company}: {str(e)[:100]}", "BPJS Setup")
                return False

        # Create mapping
        mapping_created = create_company_mapping(company)
        if not mapping_created:
            schedule_mapping_retry([company])
            return False

        return True

    except Exception as e:
        frappe.log_error(f"Error in setup_company_bpjs for {company}: {str(e)[:100]}", "BPJS Setup")
        return False