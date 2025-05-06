import frappe
from frappe import _
import json
import os
from frappe.utils import flt

# Constants for default values
DEFAULT_CONFIG_PATH = "payroll_indonesia/config/defaults.json"
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
    Load default BPJS values from defaults.json config file or use fallback defaults
    Returns dict of default values
    """
    try:
        config_path = frappe.get_app_path("payroll_indonesia", DEFAULT_CONFIG_PATH)
        if os.path.exists(config_path):
            with open(config_path) as f:
                config = json.load(f)
                bpjs_values = config.get("bpjs", {})
                if bpjs_values:
                    frappe.logger().info("Loaded BPJS values from defaults.json", tag="BPJS Setup")
                    return bpjs_values
                
                # Fallback to hardcoded defaults if bpjs section not found
                frappe.logger().warning("No BPJS section found in defaults.json", tag="BPJS Setup")
    except Exception as e:
        frappe.log_error(f"Error loading BPJS defaults: {str(e)}", "BPJS Setup")
    
    # Return hardcoded defaults if config file missing/invalid
    frappe.logger().warning("Using hardcoded BPJS default values", tag="BPJS Setup")
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
        frappe.log_error(f"BPJS Setup Error: {str(e)}", "BPJS Setup")
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
        frappe.log_error(f"Error in create_bpjs_accounts: {str(e)}", "BPJS Setup")
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
        
        frappe.logger().info("BPJS accounts setup completed", tag="BPJS Setup")
    except Exception as e:
        frappe.log_error(f"Error in setup_accounts: {str(e)}", "BPJS Setup")

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

        # Get account mapping from defaults.json
        account_mapping = get_account_mapping_config()
        
        # Create mapping with account configuration
        mapping_name = create_default_mapping(company, account_mapping)
        if mapping_name:
            frappe.logger().info(f"Created BPJS mapping for {company}", tag="BPJS Setup")
            return True
        else:
            frappe.logger().warning(f"Failed to create BPJS mapping for {company}", tag="BPJS Setup")
            return False

    except Exception as e:
        frappe.log_error(f"Error creating mapping for {company}: {str(e)}", "BPJS Setup")
        return False

def get_account_mapping_config():
    """
    Get account mapping configuration from defaults.json
    Returns account mapping dictionary
    """
    try:
        config_path = frappe.get_app_path("payroll_indonesia", DEFAULT_CONFIG_PATH)
        if os.path.exists(config_path):
            with open(config_path) as f:
                config = json.load(f)
                account_mapping = config.get("gl_accounts", {}).get("bpjs_account_mapping", {})
                if account_mapping:
                    return account_mapping
    except Exception as e:
        frappe.log_error(f"Error loading account mapping config: {str(e)}", "BPJS Setup")
    
    # Return empty dict if no config found
    return {}

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
        frappe.log_error(f"Failed to schedule mapping retry: {str(e)}", "BPJS Setup")

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

        # Apply validation rules if available
        apply_validation_rules(settings)

        # Bypass validation during setup
        settings.flags.ignore_validate = True
        settings.flags.ignore_mandatory = True
        settings.insert(ignore_permissions=True)
        
        frappe.db.commit()
        frappe.logger().info("Created new BPJS Settings", tag="BPJS Setup")
        return settings

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error creating BPJS Settings: {str(e)}", "BPJS Setup")
        return None

def apply_validation_rules(settings):
    """
    Apply validation rules from defaults.json
    """
    try:
        config_path = frappe.get_app_path("payroll_indonesia", DEFAULT_CONFIG_PATH)
        if os.path.exists(config_path):
            with open(config_path) as f:
                config = json.load(f)
                validation_rules = config.get("bpjs_settings", {}).get("validation_rules", {})
                
                # Apply percentage range validations
                for rule in validation_rules.get("percentage_ranges", []):
                    field = rule.get("field")
                    if hasattr(settings, field):
                        value = getattr(settings, field)
                        min_val = rule.get("min", 0)
                        max_val = rule.get("max", 100)
                        
                        # Adjust value if outside valid range
                        if value < min_val:
                            setattr(settings, field, min_val)
                            frappe.logger().warning(f"Adjusted {field} from {value} to minimum {min_val}", tag="BPJS Setup")
                        elif value > max_val:
                            setattr(settings, field, max_val)
                            frappe.logger().warning(f"Adjusted {field} from {value} to maximum {max_val}", tag="BPJS Setup")
                
                # Apply salary threshold validations
                for rule in validation_rules.get("salary_thresholds", []):
                    field = rule.get("field")
                    if hasattr(settings, field):
                        value = getattr(settings, field)
                        min_val = rule.get("min", 0)
                        
                        # Adjust value if below minimum
                        if value < min_val:
                            setattr(settings, field, min_val)
                            frappe.logger().warning(f"Adjusted {field} from {value} to minimum {min_val}", tag="BPJS Setup")
    except Exception as e:
        frappe.log_error(f"Error applying validation rules: {str(e)}", "BPJS Setup")

def check_or_create_bpjs_mapping(company):
    """Create BPJS Account Mapping for company if not exists"""
    try:
        mapping_exists = frappe.db.exists("BPJS Account Mapping", {"company": company})
        
        if not mapping_exists:
            try:
                from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import create_default_mapping
                
                # Get account mapping from defaults.json
                account_mapping = get_account_mapping_config()
                
                # Create mapping with account configuration
                mapping_name = create_default_mapping(company, account_mapping)
                if mapping_name:
                    frappe.logger().info(f"Created BPJS Account Mapping for {company}", tag="BPJS Setup")
                    return True
                else:
                    frappe.logger().warning(f"Failed to create BPJS Account Mapping for {company}", tag="BPJS Setup")
                    return False
            except ImportError:
                frappe.log_error("Could not import create_default_mapping", "BPJS Setup")
                return False
            except Exception as e:
                frappe.log_error(f"Error creating mapping for {company}: {str(e)}", "BPJS Setup")
                return False
        return True
                
    except Exception as e:
        frappe.log_error(f"Error checking mapping for {company}: {str(e)}", "BPJS Setup")
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
                frappe.log_error(f"Error setting up accounts for {company}: {str(e)}", "BPJS Setup")
                return False

        # Create mapping
        mapping_created = create_company_mapping(company)
        if not mapping_created:
            schedule_mapping_retry([company])
            return False

        return True

    except Exception as e:
        frappe.log_error(f"Error in setup_company_bpjs for {company}: {str(e)}", "BPJS Setup")
        return False