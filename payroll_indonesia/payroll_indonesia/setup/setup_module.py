# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-06 18:35:15 by dannyaudian

import frappe
from frappe import _
import json
import os
from frappe.utils import flt

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

# Additional setup functions can be added here
def setup_pph21_defaults():
    """Setup PPh 21 default settings and configurations"""
    try:
        debug_log("Setting up PPh 21 defaults", "PPh21 Setup")
        
        # Check if PPh 21 Settings already exist
        if frappe.db.exists("DocType", "PPh 21 Settings") and frappe.db.get_all("PPh 21 Settings"):
            debug_log("PPh 21 Settings already exist, skipping setup", "PPh21 Setup")
            return True
        
        # Get PPh 21 configuration from centralized config
        tax_config = get_default_config("tax")
        if not tax_config:
            debug_log("Missing PPh 21 configuration in defaults.json, skipping setup", "PPh21 Setup Error")
            return False
        
        # Create PPh 21 Settings
        settings = frappe.new_doc("PPh 21 Settings")
        
        # Set basic properties
        settings.calculation_method = tax_config.get("tax_calculation_method", "Progressive")
        settings.use_ter = tax_config.get("use_ter", 0)
        
        # Additional config based on config data
        # (This would depend on the specific fields in the PPh 21 Settings DocType)
        
        # Save settings
        settings.flags.ignore_validate = True
        settings.flags.ignore_mandatory = True
        settings.insert(ignore_permissions=True)
        frappe.db.commit()
        
        # Setup additional components
        setup_pph21_brackets(settings)
        setup_pph21_ter_rates(settings)
        
        debug_log("PPh 21 setup completed", "PPh21 Setup")
        return True
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error in setup_pph21_defaults: {str(e)}", "PPh21 Setup")
        debug_log(f"Error in setup_pph21_defaults: {str(e)}", "PPh21 Setup Error", trace=True)
        return False

def setup_pph21_brackets(settings):
    """Setup PPh 21 tax brackets"""
    try:
        # Get tax brackets from centralized config
        brackets = get_default_config("tax_brackets")
        if not brackets:
            debug_log("No tax brackets found in config, using defaults", "PPh21 Setup")
            # Use default brackets if not in config
            brackets = [
                {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
                {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
                {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
                {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
            ]
            
        # Add brackets to settings
        for bracket in brackets:
            row = settings.append('tax_brackets', {})
            row.income_from = flt(bracket.get("income_from", 0))
            row.income_to = flt(bracket.get("income_to", 0))
            row.tax_rate = flt(bracket.get("tax_rate", 0))
        
        # Save settings
        settings.flags.ignore_validate = True
        settings.save(ignore_permissions=True)
        frappe.db.commit()
        
        debug_log(f"Added {len(brackets)} tax brackets to PPh 21 Settings", "PPh21 Setup")
        return True
        
    except Exception as e:
        frappe.log_error(f"Error in setup_pph21_brackets: {str(e)}", "PPh21 Setup")
        debug_log(f"Error in setup_pph21_brackets: {str(e)}", "PPh21 Setup Error", trace=True)
        return False

def setup_pph21_ter_rates(settings):
    """Setup PPh 21 TER rates"""
    try:
        # Get TER rates from centralized config
        ter_rates = get_default_config("ter_rates")
        if not ter_rates:
            debug_log("No TER rates found in config, skipping TER setup", "PPh21 Setup")
            return True
            
        # Check if PPh 21 TER Table DocType exists
        if not frappe.db.exists("DocType", "PPh 21 TER Table"):
            debug_log("PPh 21 TER Table DocType not found, skipping TER setup", "PPh21 Setup")
            return False
            
        # Process each tax status and its rates
        added_count = 0
        for status, rates in ter_rates.items():
            for rate_data in rates:
                # Create new TER rate
                ter_doc = frappe.new_doc("PPh 21 TER Table")
                ter_doc.parent = "PPh 21 Settings"
                ter_doc.parentfield = "ter_rates"
                ter_doc.parenttype = "PPh 21 Settings"
                
                # Set fields
                ter_doc.status_pajak = status
                ter_doc.income_from = flt(rate_data.get("income_from", 0))
                ter_doc.income_to = flt(rate_data.get("income_to", 0))
                ter_doc.rate = flt(rate_data.get("rate", 0))
                
                # Insert document
                ter_doc.insert(ignore_permissions=True)
                added_count += 1
        
        if added_count > 0:
            debug_log(f"Added {added_count} TER rates to PPh 21 Settings", "PPh21 Setup")
        
        return True
        
    except Exception as e:
        frappe.log_error(f"Error in setup_pph21_ter_rates: {str(e)}", "PPh21 Setup")
        debug_log(f"Error in setup_pph21_ter_rates: {str(e)}", "PPh21 Setup Error", trace=True)
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
            create_salary_component(component, "earning")
            
        # Process deduction components
        deductions = components_config.get("deductions", [])
        for component in deductions:
            create_salary_component(component, "deduction")
            
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
            
        # Skip if component already exists
        if frappe.db.exists("Salary Component", name):
            return None
            
        # Create new component
        component = frappe.new_doc("Salary Component")
        component.name = name
        component.salary_component = name
        component.type = component_type
        
        # Set optional fields if provided
        if "description" in component_config:
            component.description = component_config.get("description")
            
        if "abbr" in component_config:
            component.salary_component_abbr = component_config.get("abbr")
            
        if "round_to_nearest" in component_config:
            component.round_to_the_nearest_integer = component_config.get("round_to_nearest")
            
        if "statistical_component" in component_config:
            component.statistical_component = component_config.get("statistical_component")
            
        if "depends_on_payment_days" in component_config:
            component.depends_on_payment_days = component_config.get("depends_on_payment_days")
            
        if "is_tax_applicable" in component_config:
            component.is_tax_applicable = component_config.get("is_tax_applicable")
            
        if "is_income_tax_component" in component_config:
            component.is_income_tax_component = component_config.get("is_income_tax_component")
        
        # Process accounts
        accounts = component_config.get("accounts", [])
        for account_config in accounts:
            row = component.append('accounts', {})
            
            # Set required fields
            if "company" in account_config:
                row.company = account_config.get("company")
                
            if "default_account" in account_config:
                row.default_account = account_config.get("default_account")
        
        # Insert with permission bypass
        component.flags.ignore_validate = True
        component.flags.ignore_mandatory = True
        component.insert(ignore_permissions=True)
        
        debug_log(f"Created salary component: {name} ({component_type})", "Payroll Setup")
        return component
        
    except Exception as e:
        frappe.log_error(f"Error creating salary component {component_config.get('name')}: {str(e)}", "Payroll Setup")
        debug_log(f"Error creating salary component {component_config.get('name')}: {str(e)}", "Payroll Setup Error", trace=True)
        return None