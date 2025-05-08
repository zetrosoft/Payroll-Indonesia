# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-08 10:03:33 by dannyaudian

import frappe
from frappe import _
import json
import os
from frappe.utils import flt, getdate

# Import from centralized utils module
from payroll_indonesia.payroll_indonesia.utils import (
    get_default_config, 
    debug_log, 
    find_parent_account, 
    create_account, 
    create_parent_liability_account, 
    create_parent_expense_account,
    retry_bpjs_mapping
)

def after_sync():
    """
    Run after app sync/migration
    Registered in hooks.py under after_migrate
    """
    try:
        debug_log("Starting BPJS post-migration setup", "BPJS Setup")
        success = create_bpjs_accounts()
        if success:
            debug_log("BPJS setup completed successfully", "BPJS Setup")
        else:
            debug_log("BPJS setup completed with warnings", "BPJS Setup")
            
        # Setup PPh 21 with PMK 168/2023 TER categories
        debug_log("Starting PPh 21 TER setup for PMK 168/2023", "PPh 21 Setup")
        pph21_success = setup_pph21_ter_categories()
        if pph21_success:
            debug_log("PPh 21 TER setup completed successfully", "PPh 21 Setup")
        else:
            debug_log("PPh 21 TER setup completed with warnings", "PPh 21 Setup")
    except Exception as e:
        frappe.log_error(f"Setup Error: {str(e)}", "Module Setup")
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
            debug_log("No companies found, skipping BPJS setup", "BPJS Setup")
            return False

        # Create/get BPJS Settings
        bpjs_settings = create_new_bpjs_settings()
        if not bpjs_settings:
            debug_log("Failed to create BPJS Settings", "BPJS Setup Error")
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
        
        debug_log("BPJS accounts setup completed", "BPJS Setup")
    except Exception as e:
        frappe.log_error(f"Error in setup_accounts: {str(e)}", "BPJS Setup")
        debug_log(f"Error in setup_accounts: {str(e)}", "BPJS Setup", trace=True)

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
        account_mapping = get_default_config().get("gl_accounts", {}).get("bpjs_account_mapping", {})
        
        # Create mapping with account configuration
        mapping_name = create_default_mapping(company, account_mapping)
        if mapping_name:
            debug_log(f"Created BPJS mapping for {company}", "BPJS Setup")
            return True
        else:
            debug_log(f"Failed to create BPJS mapping for {company}", "BPJS Setup Error")
            return False

    except Exception as e:
        frappe.log_error(f"Error creating mapping for {company}: {str(e)}", "BPJS Setup")
        debug_log(f"Error creating mapping for {company}: {str(e)}", "BPJS Setup Error", trace=True)
        return False

def schedule_mapping_retry(companies):
    """Schedule background job to retry failed mappings"""
    if not companies:
        return
        
    try:
        frappe.enqueue(
            "payroll_indonesia.payroll_indonesia.utils.retry_bpjs_mapping",
            companies=companies,
            queue="long",
            timeout=1500
        )
        debug_log(f"Scheduled mapping retry for: {', '.join(companies)}", "BPJS Setup")
    except Exception as e:
        frappe.log_error(f"Failed to schedule mapping retry: {str(e)}", "BPJS Setup")
        debug_log(f"Failed to schedule mapping retry: {str(e)}", "BPJS Setup Error", trace=True)

def create_new_bpjs_settings():
    """
    Create default BPJS Settings if not exists
    Returns BPJS Settings doc or None if failed
    """
    try:
        # Check if settings already exist
        if frappe.db.exists("BPJS Settings", "BPJS Settings"):
            settings = frappe.get_doc("BPJS Settings", "BPJS Settings")
            debug_log("Using existing BPJS Settings", "BPJS Setup")
            return settings

        # Create new settings
        # Get BPJS configuration from central config
        bpjs_config = get_default_config("bpjs")
        if not bpjs_config:
            frappe.throw(_("Cannot create BPJS Settings: Missing configuration in defaults.json"))
        
        settings = frappe.new_doc("BPJS Settings")
        
        # Set values from defaults
        for key, value in bpjs_config.items():
            if hasattr(settings, key):
                settings.set(key, flt(value))

        # Apply validation rules if available
        apply_validation_rules(settings)

        # Bypass validation during setup
        settings.flags.ignore_validate = True
        settings.flags.ignore_mandatory = True
        settings.insert(ignore_permissions=True)
        
        frappe.db.commit()
        debug_log("Created new BPJS Settings", "BPJS Setup")
        return settings

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error creating BPJS Settings: {str(e)}", "BPJS Setup")
        debug_log(f"Error creating BPJS Settings: {str(e)}", "BPJS Setup Error", trace=True)
        return None

def apply_validation_rules(settings):
    """
    Apply validation rules from defaults.json
    """
    try:
        # Get validation rules from centralized config
        validation_rules = get_default_config().get("bpjs_settings", {}).get("validation_rules", {})
        if not validation_rules:
            return
            
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
                    debug_log(f"Adjusted {field} from {value} to minimum {min_val}", "BPJS Setup")
                elif value > max_val:
                    setattr(settings, field, max_val)
                    debug_log(f"Adjusted {field} from {value} to maximum {max_val}", "BPJS Setup")
        
        # Apply salary threshold validations
        for rule in validation_rules.get("salary_thresholds", []):
            field = rule.get("field")
            if hasattr(settings, field):
                value = getattr(settings, field)
                min_val = rule.get("min", 0)
                
                # Adjust value if below minimum
                if value < min_val:
                    setattr(settings, field, min_val)
                    debug_log(f"Adjusted {field} from {value} to minimum {min_val}", "BPJS Setup")
    except Exception as e:
        frappe.log_error(f"Error applying validation rules: {str(e)}", "BPJS Setup")
        debug_log(f"Error applying validation rules: {str(e)}", "BPJS Setup Error", trace=True)

def check_or_create_bpjs_mapping(company):
    """Create BPJS Account Mapping for company if not exists"""
    try:
        mapping_exists = frappe.db.exists("BPJS Account Mapping", {"company": company})
        
        if not mapping_exists:
            try:
                from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import create_default_mapping
                
                # Get account mapping from defaults.json using centralized utility
                account_mapping = get_default_config().get("gl_accounts", {}).get("bpjs_account_mapping", {})
                
                # Create mapping with account configuration
                mapping_name = create_default_mapping(company, account_mapping)
                if mapping_name:
                    debug_log(f"Created BPJS Account Mapping for {company}", "BPJS Setup")
                    return True
                else:
                    debug_log(f"Failed to create BPJS Account Mapping for {company}", "BPJS Setup Error")
                    return False
            except ImportError:
                frappe.log_error("Could not import create_default_mapping", "BPJS Setup")
                return False
            except Exception as e:
                frappe.log_error(f"Error creating mapping for {company}: {str(e)}", "BPJS Setup")
                debug_log(f"Error creating mapping for {company}: {str(e)}", "BPJS Setup Error", trace=True)
                return False
        return True
                
    except Exception as e:
        frappe.log_error(f"Error checking mapping for {company}: {str(e)}", "BPJS Setup")
        debug_log(f"Error checking mapping for {company}: {str(e)}", "BPJS Setup Error", trace=True)
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
                debug_log(f"Error setting up accounts for {company}: {str(e)}", "BPJS Setup Error", trace=True)
                return False

        # Create mapping
        mapping_created = create_company_mapping(company)
        if not mapping_created:
            schedule_mapping_retry([company])
            return False

        return True

    except Exception as e:
        frappe.log_error(f"Error in setup_company_bpjs for {company}: {str(e)}", "BPJS Setup")
        debug_log(f"Error in setup_company_bpjs for {company}: {str(e)}", "BPJS Setup Error", trace=True)
        return False

def setup_pph21_ter_categories():
    """
    Setup or update PPh 21 TER categories based on PMK 168/2023
    
    Updates TER settings with new TER A, B, C categories
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        debug_log("Setting up PMK 168/2023 TER categories", "PPh 21 Setup")
        
        # Check if PMK 168 implementation is needed
        has_ter_a = frappe.db.exists("PPh 21 TER Table", {"status_pajak": "TER A"})
        has_ter_b = frappe.db.exists("PPh 21 TER Table", {"status_pajak": "TER B"})
        has_ter_c = frappe.db.exists("PPh 21 TER Table", {"status_pajak": "TER C"})
        
        if has_ter_a and has_ter_b and has_ter_c:
            debug_log("PMK 168/2023 TER categories (A, B, C) are already set up", "PPh 21 Setup")
            return True
        
        # Get configuration from defaults.json
        config = get_default_config()
        if not config:
            debug_log("No defaults.json configuration found", "PPh 21 Setup Error")
            return False
        
        # Check if ter_rates are defined
        ter_rates = config.get("ter_rates", {})
        if not ter_rates:
            debug_log("No TER rates found in configuration", "PPh 21 Setup Error")
            return False
            
        # Setup TER rate categories
        setup_ter_categories_for_pmk168(ter_rates)
        
        # Setup PTKP to TER mapping
        ptkp_to_ter_mapping = config.get("ptkp_to_ter_mapping", {})
        if ptkp_to_ter_mapping:
            setup_ptkp_ter_mapping(ptkp_to_ter_mapping)
            
        # Update PPh 21 Settings notes to reference PMK 168/2023
        update_pph21_settings_notes()
        
        debug_log("PMK 168/2023 TER categories setup completed successfully", "PPh 21 Setup")
        return True
        
    except Exception as e:
        frappe.log_error(f"Error setting up PMK 168/2023 TER categories: {str(e)}", "PPh 21 Setup Error")
        debug_log(f"Error setting up PMK 168/2023 TER categories: {str(e)}", "PPh 21 Setup Error", trace=True)
        return False

def setup_ter_categories_for_pmk168(ter_rates):
    """
    Setup TER categories for PMK 168/2023 (TER A, B, C)
    
    Args:
        ter_rates (dict): Configuration for TER rates by category
        
    Returns:
        int: Number of TER entries created
    """
    try:
        debug_log("Setting up TER rate categories", "PPh 21 Setup")
        
        # Check if PPh 21 TER Table DocType exists
        if not frappe.db.exists("DocType", "PPh 21 TER Table"):
            debug_log("PPh 21 TER Table DocType not found", "PPh 21 Setup Error")
            return 0
            
        # Delete existing entries for TER A, B, C if any exist
        for category in ["TER A", "TER B", "TER C"]:
            if frappe.db.exists("PPh 21 TER Table", {"status_pajak": category}):
                debug_log(f"Clearing existing {category} rates", "PPh 21 Setup")
                frappe.db.sql(f"DELETE FROM `tabPPh 21 TER Table` WHERE status_pajak = '{category}'")
        
        # Create category description mapping
        category_descriptions = {
            "TER A": "PTKP TK/0 (Rp 54 juta/tahun)",
            "TER B": "PTKP K/0, TK/1, TK/2, K/1 (Rp 58,5-63 juta/tahun)",
            "TER C": "PTKP nilai tinggi (> Rp 63 juta/tahun)"
        }
        
        # Track total entries created
        count = 0
        
        # Create TER entries for each category
        for category, rates in ter_rates.items():
            if category not in ["TER A", "TER B", "TER C"]:
                debug_log(f"Skipping unsupported category: {category}", "PPh 21 Setup")
                continue
                
            # Get category description
            category_desc = category_descriptions.get(category, "")
            
            # Create entries for this category
            for rate_data in rates:
                try:
                    # Determine if this is the highest bracket
                    is_highest = "is_highest_bracket" in rate_data and rate_data["is_highest_bracket"]
                    if rate_data.get("income_to", 0) == 0:
                        is_highest = True
                    
                    # Create description
                    if rate_data["income_to"] == 0:
                        description = f"{category_desc} - Penghasilan > Rp{rate_data['income_from']:,.0f}"
                    elif rate_data["income_from"] == 0:
                        description = f"{category_desc} - Penghasilan ≤ Rp{rate_data['income_to']:,.0f}"
                    else:
                        description = f"{category_desc} - Penghasilan Rp{rate_data['income_from']:,.0f}-Rp{rate_data['income_to']:,.0f}"
                    
                    # Create TER entry
                    ter = frappe.get_doc({
                        "doctype": "PPh 21 TER Table",
                        "status_pajak": category,
                        "income_from": flt(rate_data["income_from"]),
                        "income_to": flt(rate_data["income_to"]),
                        "rate": flt(rate_data["rate"]),
                        "description": description,
                        "is_highest_bracket": 1 if is_highest else 0,
                        "pmk_168": 1  # Flag for PMK 168/2023
                    })
                    
                    # Skip validation for bulk import
                    ter.flags.ignore_validate = True
                    ter.flags.ignore_mandatory = True
                    ter.flags.ignore_permissions = True
                    ter.insert(ignore_permissions=True)
                    
                    count += 1
                except Exception as e:
                    frappe.log_error(f"Error creating TER rate {category}: {str(e)}", "PPh 21 Setup Error")
                    debug_log(f"Error creating TER rate {category}: {str(e)}", "PPh 21 Setup Error", trace=True)
        
        # Commit changes
        frappe.db.commit()
        debug_log(f"Created {count} TER entries for PMK 168/2023", "PPh 21 Setup")
        return count
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error setting up TER categories: {str(e)}", "PPh 21 Setup Error")
        debug_log(f"Error setting up TER categories: {str(e)}", "PPh 21 Setup Error", trace=True)
        return 0

def setup_ptkp_ter_mapping(mapping_data):
    """
    Setup PTKP to TER category mapping for PMK 168/2023
    
    Args:
        mapping_data (dict): PTKP to TER mapping configuration
        
    Returns:
        int: Number of mapping entries created
    """
    try:
        debug_log("Setting up PTKP to TER mapping", "PPh 21 Setup")
        
        # Check if mapping DocType exists
        mapping_doctype = "PTKP TER Mapping"
        if not frappe.db.exists("DocType", mapping_doctype):
            debug_log(f"{mapping_doctype} DocType not found, creating custom mapping", "PPh 21 Setup")
            # Store in PPh 21 Settings as a field value instead
            return setup_ptkp_ter_mapping_in_settings(mapping_data)
        
        # Clear existing mapping entries
        frappe.db.sql(f"DELETE FROM `tab{mapping_doctype}`")
        
        # Create mapping for each PTKP status
        count = 0
        for ptkp_status, ter_category in mapping_data.items():
            try:
                # Create new mapping entry
                mapping = frappe.get_doc({
                    "doctype": mapping_doctype,
                    "ptkp_status": ptkp_status,
                    "ter_category": ter_category,
                    "description": get_ptkp_description(ptkp_status, ter_category)
                })
                
                # Insert with permission bypass
                mapping.flags.ignore_permissions = True
                mapping.flags.ignore_validate = True
                mapping.insert(ignore_permissions=True)
                
                count += 1
            except Exception as e:
                frappe.log_error(f"Error creating mapping for {ptkp_status}: {str(e)}", "PPh 21 Setup Error")
                debug_log(f"Error creating mapping for {ptkp_status}: {str(e)}", "PPh 21 Setup Error", trace=True)
        
        # Commit changes
        frappe.db.commit()
        debug_log(f"Created {count} PTKP to TER mappings for PMK 168/2023", "PPh 21 Setup")
        return count
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error setting up PTKP to TER mapping: {str(e)}", "PPh 21 Setup Error")
        debug_log(f"Error setting up PTKP to TER mapping: {str(e)}", "PPh 21 Setup Error", trace=True)
        return 0

def setup_ptkp_ter_mapping_in_settings(mapping_data):
    """
    Store PTKP to TER mapping as a JSON field in PPh 21 Settings
    
    Args:
        mapping_data (dict): PTKP to TER mapping configuration
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not frappe.db.exists("PPh 21 Settings", "PPh 21 Settings"):
            debug_log("PPh 21 Settings not found", "PPh 21 Setup")
            return False
            
        # Get settings
        settings = frappe.get_doc("PPh 21 Settings", "PPh 21 Settings")
        
        # Store mapping as a JSON field
        if hasattr(settings, 'ptkp_ter_mapping_json'):
            settings.ptkp_ter_mapping_json = json.dumps(mapping_data)
        else:
            # Try setting as custom field
            settings.set('ptkp_ter_mapping_json', json.dumps(mapping_data))
        
        # Save settings
        settings.flags.ignore_validate = True
        settings.flags.ignore_permissions = True
        settings.save(ignore_permissions=True)
        
        debug_log(f"Stored PTKP to TER mapping in PPh 21 Settings", "PPh 21 Setup")
        frappe.db.commit()
        return True
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error setting up PTKP to TER mapping in settings: {str(e)}", "PPh 21 Setup Error")
        debug_log(f"Error setting up PTKP to TER mapping in settings: {str(e)}", "PPh 21 Setup Error", trace=True)
        return False

def get_ptkp_description(ptkp_status, ter_category):
    """
    Get description for PTKP to TER mapping based on status and category
    
    Args:
        ptkp_status (str): PTKP status (e.g. 'TK0', 'K1')
        ter_category (str): TER category (e.g. 'TER A', 'TER B')
        
    Returns:
        str: Description for the mapping
    """
    # Generate description based on PTKP status
    status_prefix = ptkp_status[:2] if len(ptkp_status) >= 2 else ptkp_status
    tanggungan = ptkp_status[2:] if len(ptkp_status) > 2 else "0"
    
    # Get PTKP description
    if status_prefix == "TK":
        ptkp_desc = f"Tidak Kawin, {tanggungan} tanggungan"
    elif status_prefix == "K":
        ptkp_desc = f"Kawin, {tanggungan} tanggungan"
    elif status_prefix == "HB":
        ptkp_desc = f"Penghasilan istri digabung, {tanggungan} tanggungan"
    else:
        ptkp_desc = ptkp_status
    
    # Get TER category description
    if ter_category == "TER A":
        ter_desc = "TER A (PTKP TK/0 - Rp 54 juta/tahun)"
    elif ter_category == "TER B":
        ter_desc = "TER B (PTKP K/0, TK/1, TK/2, K/1 - Rp 58,5-63 juta/tahun)"
    elif ter_category == "TER C":
        ter_desc = "TER C (PTKP nilai tinggi > Rp 63 juta/tahun)"
    else:
        ter_desc = ter_category
    
    return f"{ptkp_desc} → {ter_desc} (PMK 168/2023)"

def update_pph21_settings_notes():
    """
    Update PPh 21 Settings notes to reference PMK 168/2023
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not frappe.db.exists("PPh 21 Settings", "PPh 21 Settings"):
            debug_log("PPh 21 Settings not found", "PPh 21 Setup")
            return False
            
        # Get settings
        settings = frappe.get_doc("PPh 21 Settings", "PPh 21 Settings")
        
        # Update TER notes
        if hasattr(settings, 'ter_notes'):
            settings.ter_notes = "Tarif Efektif Rata-rata (TER) sesuai PMK-168/PMK.010/2023 dengan 3 kategori (TER A, B, C)"
        
        # Update description if available
        if hasattr(settings, 'description'):
            settings.description = "Pengaturan PPh 21 dengan implementasi PMK 168/2023 untuk Tarif Efektif Rata-rata (TER)"
        
        # Save settings
        settings.flags.ignore_validate = True
        settings.flags.ignore_permissions = True
        settings.save(ignore_permissions=True)
        
        debug_log(f"Updated PPh 21 Settings notes with PMK 168/2023 reference", "PPh 21 Setup")
        frappe.db.commit()
        return True
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error updating PPh 21 Settings notes: {str(e)}", "PPh 21 Setup Error")
        debug_log(f"Error updating PPh 21 Settings notes: {str(e)}", "PPh 21 Setup Error", trace=True)
        return False

def setup_salary_components():
    """Setup standard salary components for Indonesian payroll"""
    try:
        debug_log("Setting up salary components", "Payroll Setup")
        
        # Get components configuration from centralized config
        components_config = get_default_config().get("salary_components", {})
        if not components_config:
            debug_log("No salary components configuration found in defaults.json", "Payroll Setup")
            return False
        
        # Process earnings components
        earnings = components_config.get("earnings", [])
        for component in earnings:
            create_salary_component(component, "Earning")
            
        # Process deduction components
        deductions = components_config.get("deductions", [])
        for component in deductions:
            # Add PMK 168/2023 reference for PPh 21
            if component.get("name") == "PPh 21" and "supports_ter" in component and component["supports_ter"]:
                component["description"] = "PPh 21 (PMK 168/2023) dengan kategori TER A, B, C"
                
            create_salary_component(component, "Deduction")
            
        debug_log("Salary components setup completed", "Payroll Setup")
        return True
        
    except Exception as e:
        frappe.log_error(f"Error in setup_salary_components: {str(e)}", "Payroll Setup")
        debug_log(f"Error in setup_salary_components: {str(e)}", "Payroll Setup Error", trace=True)
        return False

def create_salary_component(component_config, component_type):
    """Create a salary component from configuration"""
    try:
        name = component_config.get("name")
        if not name:
            return None
            
        # Get existing component or create new
        if frappe.db.exists("Salary Component", name):
            component = frappe.get_doc("Salary Component", name)
        else:
            component = frappe.new_doc("Salary Component")
            component.salary_component = name
        
        # Set component type
        component.type = component_type
        
        # Set abbreviation
        if "abbr" in component_config:
            component.salary_component_abbr = component_config.get("abbr")
        else:
            # Generate abbreviation if not provided
            component.salary_component_abbr = name[:3].upper()
        
        # Set optional fields if provided
        if "description" in component_config:
            component.description = component_config.get("description")
            
        if "round_to_nearest" in component_config:
            component.round_to_the_nearest_integer = component_config.get("round_to_nearest")
            
        if "statistical_component" in component_config:
            component.statistical_component = component_config.get("statistical_component")
            
        if "depends_on_payment_days" in component_config:
            component.depends_on_payment_days = component_config.get("depends_on_payment_days")
            
        if "is_tax_applicable" in component_config:
            component.is_tax_applicable = component_config.get("is_tax_applicable")
            
        if "variable_based_on_taxable_salary" in component_config:
            component.variable_based_on_taxable_salary = component_config.get("variable_based_on_taxable_salary")
        
        # Special handling for PPh 21 with PMK 168/2023 TER categories
        if name == "PPh 21" and "supports_ter" in component_config and component_config["supports_ter"]:
            # Check if custom field exists
            if frappe.db.exists("Custom Field", {"dt": "Salary Component", "fieldname": "supports_ter"}):
                component.supports_ter = 1
            
            # Set description if not already set
            if not component.description:
                component.description = "PPh 21 (PMK 168/2023) dengan kategori TER A, B, C"
        
        # Save component
        component.flags.ignore_validate = True
        component.flags.ignore_permissions = True
        
        if component.is_new():
            component.insert(ignore_permissions=True)
            debug_log(f"Created salary component: {name}", "Payroll Setup")
        else:
            component.save(ignore_permissions=True)
            debug_log(f"Updated salary component: {name}", "Payroll Setup")
        
        return component
        
    except Exception as e:
        frappe.log_error(f"Error creating salary component {component_config.get('name')}: {str(e)}", "Payroll Setup")
        debug_log(f"Error creating salary component {component_config.get('name')}: {str(e)}", "Payroll Setup Error", trace=True)
        return None