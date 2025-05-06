# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-06 17:26:07 by dannyaudian

import frappe
from frappe import _
from frappe.utils import getdate, flt, now_datetime
import json
import os

__all__ = [
    'before_install',
    'after_install',
    'after_sync',
    'check_system_readiness',
    'setup_accounts',
    'setup_pph21',
    'create_supplier_group',
    'create_bpjs_supplier',
    'setup_salary_components',
    'display_installation_summary'
]

def before_install():
    """
    Setup requirements before installing the app
    
    Performs system readiness checks to ensure proper installation.
    """
    try:
        # Check if system is ready for installation
        check_system_readiness()
    except Exception as e:
        frappe.log_error(
            f"Error during before_install: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Payroll Indonesia Installation Error"
        )

def after_install():
    """
    Setup requirements after installing the app
    
    Creates accounts, sets up tax configuration, configures BPJS and more.
    The custom fields are handled by the fixtures automatically.
    """
    # Import needed utility functions
    from payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.utils import get_default_config, debug_log
    
    debug_log("Starting Payroll Indonesia after_install process", "Installation")
    
    # Load configuration defaults
    config = get_default_config()
    
    # Track setup results
    results = {
        "accounts": False,
        "suppliers": False,
        "pph21_settings": False,
        "salary_components": False,
        "bpjs_setup": False
    }
    
    try:
        # Create accounts first (required for salary components)
        results["accounts"] = setup_accounts(config)
        debug_log("Account setup completed", "Installation")
    except Exception as e:
        frappe.log_error(
            f"Error during account setup: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Account Setup Error"
        )
        
    try:
        # Setup suppliers
        supplier_results = create_supplier_group()
        # Only attempt creating BPJS supplier if supplier group creation was successful
        if supplier_results and config.get("suppliers", {}).get("bpjs", {}):
            supplier_results = create_bpjs_supplier(config)
        results["suppliers"] = supplier_results
        debug_log("Supplier setup completed", "Installation")
    except Exception as e:
        frappe.log_error(
            f"Error during supplier setup: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Supplier Setup Error"
        )
        
    try:
        # Setup tax configuration and TER rates
        pph21_results = setup_pph21(config)
        results["pph21_settings"] = pph21_results
        debug_log("PPh 21 setup completed", "Installation")
    except Exception as e:
        frappe.log_error(
            f"Error during PPh 21 setup: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "PPh 21 Setup Error"
        )
    
    try:
        # Setup salary components
        results["salary_components"] = setup_salary_components(config)
        debug_log("Salary components setup completed", "Installation")
    except Exception as e:
        frappe.log_error(
            f"Error during salary components setup: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Salary Components Setup Error"
        )
        
    try:
        # Setup BPJS - Use module function to create a single instance
        from payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.bpjs_settings import setup_bpjs_settings
        results["bpjs_setup"] = setup_bpjs_settings()
        debug_log("BPJS setup completed", "Installation")
    except Exception as e:
        frappe.log_error(
            f"Error during BPJS setup: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Setup Error"
        )
        
    # Commit all changes
    try:
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(
            f"Error committing changes: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Installation Database Error"
        )
    
    # Display installation summary
    display_installation_summary(results, config)

def after_sync():
    """
    Setup function that runs after app sync
    
    Updates BPJS settings if they exist
    """
    from payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.utils import get_default_config, debug_log
    
    try:
        debug_log("Starting after_sync process", "App Sync")
        
        # Check if BPJS Settings already exist
        if frappe.db.exists("DocType", "BPJS Settings") and frappe.db.exists("BPJS Settings", "BPJS Settings"):
            # Use module function to update from latest defaults
            from payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.bpjs_settings import update_bpjs_settings
            updated = update_bpjs_settings()
            debug_log(f"Updated BPJS Settings: {updated}", "App Sync")
    except Exception as e:
        frappe.log_error(
            f"Error during after_sync: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Payroll Indonesia Sync Error"
        )

def check_system_readiness():
    """
    Check if system is ready for Payroll Indonesia installation
    
    Returns:
        bool: True if ready, False otherwise
    """
    from payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.utils import debug_log
    
    # Check if required DocTypes exist
    required_core_doctypes = [
        "Salary Component", "Salary Structure", "Salary Slip", 
        "Employee", "Company", "Account"
    ]
    
    missing_doctypes = []
    for doctype in required_core_doctypes:
        if not frappe.db.exists("DocType", doctype):
            missing_doctypes.append(doctype)
            
    if missing_doctypes:
        debug_log(f"Required DocTypes missing: {', '.join(missing_doctypes)}", "System Readiness Check")
        frappe.log_error(
            f"Required DocTypes missing: {', '.join(missing_doctypes)}",
            "System Readiness Check"
        )
        
    # Check if company exists
    companies = frappe.get_all("Company")
    if not companies:
        debug_log("No company found. Some setup steps may fail.", "System Readiness Check")
        frappe.log_error("No company found", "System Readiness Check")
    else:
        # Check if each company has an abbreviation
        for company in companies:
            abbr = frappe.get_cached_value("Company", company.name, "abbr") 
            if not abbr:
                debug_log(f"Company {company.name} has no abbreviation set", "System Readiness Check")
                frappe.log_error(f"Company {company.name} has no abbreviation", "System Readiness Check")
        
    # Return True so installation can continue with warnings
    return True

def setup_accounts(config):
    """
    Create required Accounts for Indonesian payroll management using utility functions
    
    Args:
        config (dict): Configuration data from defaults.json
        
    Returns:
        bool: True if successful, False otherwise
    """
    from payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.utils import (
        debug_log, create_account, find_parent_account, 
        create_parent_liability_account, create_parent_expense_account
    )
    
    if not config:
        debug_log("No configuration data available for creating accounts", "Account Setup")
        return False
        
    gl_accounts = config.get("gl_accounts", {})
    if not gl_accounts:
        debug_log("No GL accounts configuration found in defaults.json", "Account Setup")
        return False
    
    # Build account list from config sections
    account_sections = ['expense_accounts', 'payable_accounts']
    accounts = []
    
    # Add accounts from each section
    for section in account_sections:
        for _, account_info in gl_accounts.get(section, {}).items():
            accounts.append(account_info)
    
    # Get all companies
    companies = frappe.get_all("Company", pluck="name")
    if not companies:
        debug_log("No company found. Cannot create accounts.", "Account Setup")
        return False
        
    # Track overall success
    overall_success = True
    
    # Process each company
    for company in companies:
        try:
            # Get company abbreviation
            company_abbr = frappe.db.get_value("Company", company, "abbr")
            if not company_abbr:
                debug_log(f"Company {company} has no abbreviation, skipping", "Account Setup")
                overall_success = False
                continue
            
            debug_log(f"Creating accounts for company: {company}", "Account Setup")
            
            # Create parent accounts first - utilize utility functions
            parent_liability = create_parent_liability_account(company)
            parent_expense = create_parent_expense_account(company)
            
            if not parent_liability or not parent_expense:
                debug_log(f"Failed to create parent accounts for {company}", "Account Setup")
                overall_success = False
                continue
            
            # Create individual accounts
            created_accounts = []
            failed_accounts = []
                
            # Create each account
            for account in accounts:
                try:
                    # Find parent account using utility function
                    parent_name = account["parent_account"]
                    parent_account = find_parent_account(company, parent_name, company_abbr, account["account_type"])
                    
                    if not parent_account:
                        failed_accounts.append(account["account_name"])
                        debug_log(f"Could not find parent account {parent_name} for {company}", "Account Setup")
                        continue
                            
                    # Create account using standardized utility function
                    full_account_name = create_account(
                        company=company,
                        account_name=account["account_name"],
                        account_type=account["account_type"],
                        parent=parent_account
                    )
                    
                    if full_account_name:
                        created_accounts.append(account["account_name"])
                        debug_log(f"Created account: {full_account_name}", "Account Creation")
                    else:
                        failed_accounts.append(account["account_name"])
                        
                except Exception as e:
                    frappe.log_error(
                        f"Error creating account {account['account_name']} for {company}: {str(e)}\n\n"
                        f"Traceback: {frappe.get_traceback()}",
                        "Account Creation Error"
                    )
                    failed_accounts.append(account["account_name"])
                    overall_success = False
            
            # Log summary
            if created_accounts:
                debug_log(f"Created {len(created_accounts)} accounts for {company}", "Account Setup")
                
            if failed_accounts:
                debug_log(f"Failed to create {len(failed_accounts)} accounts for {company}: {', '.join(failed_accounts)}", "Account Setup Error")
                overall_success = False
                
        except Exception as e:
            frappe.log_error(
                f"Error setting up accounts for company {company}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Account Creation Error"
            )
            overall_success = False
    
    return overall_success

def create_supplier_group():
    """
    Create Government supplier group for tax and BPJS entities
    
    Returns:
        bool: True if successful, False otherwise
    """
    from payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.utils import debug_log
    
    try:
        # Skip if already exists
        if frappe.db.exists("Supplier Group", "Government"):
            debug_log("Government supplier group already exists", "Supplier Setup")
            return True
            
        # Check if parent group exists
        if not frappe.db.exists("Supplier Group", "All Supplier Groups"):
            debug_log("All Supplier Groups parent group missing", "Supplier Setup Error")
            return False
            
        # Create the group
        group = frappe.new_doc("Supplier Group")
        group.supplier_group_name = "Government"
        group.parent_supplier_group = "All Supplier Groups"
        group.is_group = 0
        group.flags.ignore_permissions = True
        group.insert(ignore_permissions=True)
        
        # Commit immediately
        frappe.db.commit()
        
        # Create specific BPJS supplier group
        if not frappe.db.exists("Supplier Group", "BPJS Provider"):
            bpjs_group = frappe.new_doc("Supplier Group")
            bpjs_group.supplier_group_name = "BPJS Provider"
            bpjs_group.parent_supplier_group = "Government"
            bpjs_group.is_group = 0
            bpjs_group.flags.ignore_permissions = True
            bpjs_group.insert(ignore_permissions=True)
            frappe.db.commit()
            debug_log("Created BPJS Provider supplier group", "Supplier Setup")
        
        # Create tax authority supplier group
        if not frappe.db.exists("Supplier Group", "Tax Authority"):
            tax_group = frappe.new_doc("Supplier Group")
            tax_group.supplier_group_name = "Tax Authority"
            tax_group.parent_supplier_group = "Government"
            tax_group.is_group = 0
            tax_group.flags.ignore_permissions = True
            tax_group.insert(ignore_permissions=True)
            frappe.db.commit()
            debug_log("Created Tax Authority supplier group", "Supplier Setup")
        
        debug_log("Created Government supplier group hierarchy", "Supplier Setup")
        return True
        
    except Exception as e:
        frappe.log_error(
            f"Failed to create supplier group: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Supplier Setup Error"
        )
        return False

def create_bpjs_supplier(config):
    """
    Create BPJS supplier entity from config
    
    Args:
        config (dict): Configuration data from defaults.json
        
    Returns:
        bool: True if successful, False otherwise
    """
    from payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.utils import debug_log
    
    try:
        supplier_config = config.get("suppliers", {}).get("bpjs", {})
        if not supplier_config:
            debug_log("No BPJS supplier configuration found", "Supplier Setup")
            return False
            
        supplier_name = supplier_config.get("supplier_name", "BPJS")
        
        # Skip if already exists
        if frappe.db.exists("Supplier", supplier_name):
            debug_log(f"Supplier {supplier_name} already exists", "Supplier Setup")
            return True
            
        # Ensure supplier group exists
        supplier_group = supplier_config.get("supplier_group", "Government")
        if not frappe.db.exists("Supplier Group", supplier_group):
            supplier_group = "BPJS Provider"  # Try alternative
            if not frappe.db.exists("Supplier Group", supplier_group):
                supplier_group = "Government"  # Fallback
                if not frappe.db.exists("Supplier Group", supplier_group):
                    debug_log(f"No suitable supplier group exists", "Supplier Setup")
                    return False
            
        # Create supplier
        supplier = frappe.new_doc("Supplier")
        supplier.supplier_name = supplier_name
        supplier.supplier_group = supplier_group
        supplier.supplier_type = supplier_config.get("supplier_type", "Government")
        supplier.country = supplier_config.get("country", "Indonesia")
        supplier.default_currency = supplier_config.get("default_currency", "IDR")
        
        supplier.flags.ignore_permissions = True
        supplier.insert(ignore_permissions=True)
        
        frappe.db.commit()
        debug_log(f"Created supplier: {supplier_name}", "Supplier Setup")
        return True
        
    except Exception as e:
        frappe.log_error(
            f"Failed to create BPJS supplier: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Supplier Setup Error"
        )
        return False

def setup_pph21(config):
    """
    Setup PPh 21 tax settings including TER and tax slabs
    
    Args:
        config (dict): Configuration from defaults.json
        
    Returns:
        bool: True if successful, False otherwise
    """
    from payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.utils import debug_log
    
    try:
        # Setup PPh 21 Settings first
        pph21_settings = setup_pph21_defaults(config)
        if not pph21_settings:
            debug_log("Failed to setup PPh 21 defaults", "PPh 21 Setup Error")
            return False
            
        # Setup TER rates
        ter_result = setup_pph21_ter(config)
        
        # Setup income tax slab
        tax_slab_result = setup_income_tax_slab(config)
        
        return ter_result and tax_slab_result
    except Exception as e:
        frappe.log_error(
            f"Error in PPh 21 setup: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "PPh 21 Setup Error"
        )
        return False

def setup_pph21_defaults(config):
    """
    Setup default PPh 21 configuration with TER method using config data
    
    Args:
        config (dict): Configuration data from defaults.json
        
    Returns:
        object: PPh 21 Settings document if successful, None otherwise
    """
    from payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.utils import debug_log
    
    try:
        # Check if already exists
        settings = None
        if frappe.db.exists("PPh 21 Settings", "PPh 21 Settings"):
            settings = frappe.get_doc("PPh 21 Settings", "PPh 21 Settings")
            settings.ptkp_table = []
            settings.bracket_table = []
        else:
            settings = frappe.new_doc("PPh 21 Settings")
        
        # Set TER as default calculation method from config
        tax_config = config.get("tax", {})
        settings.calculation_method = tax_config.get("tax_calculation_method", "TER")
        settings.use_ter = tax_config.get("use_ter", 1)
        settings.use_gross_up = tax_config.get("use_gross_up", 0)
        settings.npwp_mandatory = tax_config.get("npwp_mandatory", 0)
        settings.biaya_jabatan_percent = tax_config.get("biaya_jabatan_percent", 5.0)
        settings.biaya_jabatan_max = tax_config.get("biaya_jabatan_max", 500000.0)
        settings.umr_default = tax_config.get("umr_default", 4900000.0)
        settings.ter_notes = "Tarif Efektif Rata-rata (TER) sesuai PMK-168/PMK.010/2023"
        
        # Add PTKP values from config
        ptkp_values = config.get("ptkp", {})
        if not ptkp_values:
            debug_log("No PTKP values found in config, using defaults", "PPh 21 Setup")
            # Fallback to defaults
            ptkp_values = {
                "TK0": 54000000, "TK1": 58500000, "TK2": 63000000, "TK3": 67500000,
                "K0": 58500000, "K1": 63000000, "K2": 67500000, "K3": 72000000,
                "HB0": 112500000, "HB1": 117000000, "HB2": 121500000, "HB3": 126000000
            }
            
        # Add PTKP values
        for status, amount in ptkp_values.items():
            # Create description
            tanggungan = status[2:] if len(status) > 2 else "0"
            description = ""
            
            if status.startswith("TK"):
                description = f"Tidak Kawin, {tanggungan} Tanggungan"
            elif status.startswith("K"):
                description = f"Kawin, {tanggungan} Tanggungan" 
            elif status.startswith("HB"):
                description = f"Kawin (Penghasilan Istri Digabung), {tanggungan} Tanggungan"
                
            settings.append("ptkp_table", {
                "status_pajak": status,
                "ptkp_amount": flt(amount),
                "description": description
            })
        
        # Add tax brackets from config
        tax_brackets = config.get("tax_brackets", [])
        if not tax_brackets:
            debug_log("No tax brackets found in config, using defaults", "PPh 21 Setup")
            # Fallback to defaults
            tax_brackets = [
                {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
                {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
                {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
                {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
            ]
        
        for bracket in tax_brackets:
            settings.append("bracket_table", {
                "income_from": flt(bracket["income_from"]),
                "income_to": flt(bracket["income_to"]),
                "tax_rate": flt(bracket["tax_rate"])
            })
        
        # Save settings
        settings.flags.ignore_permissions = True
        settings.flags.ignore_validate = True
        if settings.is_new():
            settings.insert(ignore_permissions=True)
        else:
            settings.save(ignore_permissions=True)
            
        # Commit changes
        frappe.db.commit()
            
        debug_log("PPh 21 Settings configured successfully", "PPh 21 Setup")
        return settings
        
    except Exception as e:
        frappe.log_error(
            f"Error setting up PPh 21: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "PPh 21 Setup Error"
        )
        return None

def setup_pph21_ter(config):
    """
    Setup default TER rates based on PMK-168/PMK.010/2023 using config data
    
    Args:
        config (dict): Configuration data from defaults.json
        
    Returns:
        bool: True if successful, False otherwise
    """
    from payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.utils import debug_log
    
    try:
        # Skip if DocType doesn't exist
        if not frappe.db.exists("DocType", "PPh 21 TER Table"):
            debug_log("PPh 21 TER Table DocType doesn't exist", "TER Setup Error")
            return False
        
        # Clear existing TER rates
        try:
            frappe.db.sql("DELETE FROM `tabPPh 21 TER Table`")
            frappe.db.commit()
            debug_log("Cleared existing TER rates", "TER Setup")
        except Exception as e:
            frappe.log_error(
                f"Error clearing existing TER rates: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "TER Setup Error"
            )
        
        # Get TER rates from config
        ter_rates = config.get("ter_rates", {})
        if not ter_rates:
            debug_log("No TER rates found in config", "TER Setup Error")
            return False
            
        # Create TER rates
        count = 0
        status_list = list(ter_rates.keys())
        
        for status in status_list:
            # Determine the highest bracket for each status
            status_rates = ter_rates[status]
            status_rates_count = len(status_rates)
            
            for idx, rate_data in enumerate(status_rates):
                try:
                    # Check if this is the highest bracket
                    is_highest = (idx == status_rates_count - 1) or (rate_data["income_to"] == 0)
                    
                    # Create description
                    if rate_data["income_to"] == 0:
                        description = f"{status} > Rp{rate_data['income_from']:,.0f}"
                    elif rate_data["income_from"] == 0:
                        description = f"{status} ≤ Rp{rate_data['income_to']:,.0f}"
                    else:
                        description = f"{status} Rp{rate_data['income_from']:,.0f}-Rp{rate_data['income_to']:,.0f}"
                    
                    # Check if entry already exists
                    existing = frappe.db.exists(
                        "PPh 21 TER Table",
                        {
                            "status_pajak": status,
                            "income_from": flt(rate_data["income_from"]),
                            "income_to": flt(rate_data["income_to"])
                        }
                    )
                    
                    if existing:
                        # Update existing entry
                        ter_entry = frappe.get_doc("PPh 21 TER Table", existing)
                        ter_entry.rate = flt(rate_data["rate"])
                        ter_entry.description = description
                        ter_entry.is_highest_bracket = 1 if is_highest else 0
                        ter_entry.flags.ignore_permissions = True
                        ter_entry.save(ignore_permissions=True)
                        debug_log(f"Updated TER rate for {status}", "TER Setup")
                    else:
                        # Create TER entry with is_highest_bracket flag
                        ter_entry = frappe.get_doc({
                            "doctype": "PPh 21 TER Table",
                            "status_pajak": status,
                            "income_from": flt(rate_data["income_from"]),
                            "income_to": flt(rate_data["income_to"]),
                            "rate": flt(rate_data["rate"]),
                            "description": description,
                            "is_highest_bracket": 1 if is_highest else 0
                        })
                        
                        ter_entry.flags.ignore_permissions = True
                        ter_entry.insert(ignore_permissions=True)
                    
                    count += 1
                except Exception as e:
                    frappe.log_error(
                        f"Error creating TER rate for {status} with rate {rate_data['rate']}: {str(e)}\n\n"
                        f"Traceback: {frappe.get_traceback()}",
                        "TER Rate Error"
                    )
        
        # Commit all changes
        frappe.db.commit()
        debug_log(f"Processed {count} TER rates successfully", "TER Setup")
        return count > 0
            
    except Exception as e:
        frappe.log_error(
            f"Error setting up TER rates: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "TER Setup Error"
        )
        return False

def setup_income_tax_slab(config):
    """
    Create Income Tax Slab for Indonesia using config data
    
    Args:
        config (dict): Configuration data from defaults.json
        
    Returns:
        bool: True if successful, False otherwise
    """
    from payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.utils import debug_log
    
    try:
        # Skip if already exists
        if frappe.db.exists("Income Tax Slab", {"currency": "IDR", "is_default": 1}):
            debug_log("Income Tax Slab already exists", "Tax Slab Setup")
            return True
        
        # Get company
        company = frappe.db.get_default("company")
        if not company:
            companies = frappe.get_all("Company", pluck="name")
            if companies:
                company = companies[0]
            else:
                debug_log("No company found for income tax slab", "Tax Slab Setup Error")
                return False
        
        # Get tax brackets from config
        tax_brackets = config.get("tax_brackets", [])
        if not tax_brackets:
            debug_log("No tax brackets found in config, using defaults", "Tax Slab Setup")
            # Fallback to defaults
            tax_brackets = [
                {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
                {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
                {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
                {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
            ]
        
        # Create tax slab
        tax_slab = frappe.new_doc("Income Tax Slab")
        tax_slab.name = "Indonesia Income Tax"
        tax_slab.title = "Indonesia Income Tax"
        tax_slab.effective_from = getdate("2023-01-01")
        tax_slab.company = company
        tax_slab.currency = config.get("defaults", {}).get("currency", "IDR")
        tax_slab.is_default = 1
        tax_slab.disabled = 0

        # Add tax brackets
        for bracket in tax_brackets:
            tax_slab.append("slabs", {
                "from_amount": flt(bracket["income_from"]), 
                "to_amount": flt(bracket["income_to"]), 
                "percent_deduction": flt(bracket["tax_rate"])
            })
            
        # Save with flags
        tax_slab.flags.ignore_permissions = True
        tax_slab.flags.ignore_mandatory = True
        tax_slab.insert()
        frappe.db.commit()
        
        debug_log(f"Created Income Tax Slab for Indonesia with company {company}", "Tax Slab Setup")
        return True
        
    except Exception as e:
        frappe.log_error(f"Error creating Income Tax Slab: {str(e)}", "Tax Slab Setup Error")
        return False

def setup_salary_components(config):
    """
    Create salary components from config
    
    Args:
        config (dict): Configuration data from defaults.json
        
    Returns:
        bool: True if successful, False otherwise
    """
    from payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.utils import debug_log
    
    try:
        # Get salary component configuration
        component_config = config.get("salary_components", {})
        if not component_config:
            debug_log("No salary component configuration found", "Salary Components Setup")
            return False
            
        earnings = component_config.get("earnings", [])
        deductions = component_config.get("deductions", [])
        
        created_count = 0
        
        # Create earnings components
        for component in earnings:
            if not frappe.db.exists("Salary Component", component.get("name")):
                comp_doc = frappe.new_doc("Salary Component")
                comp_doc.salary_component = component.get("name")
                comp_doc.salary_component_abbr = component.get("abbr")
                comp_doc.type = "Earning"
                comp_doc.is_tax_applicable = component.get("is_tax_applicable", True)
                comp_doc.flags.ignore_permissions = True
                comp_doc.insert()
                created_count += 1
                debug_log(f"Created earning component: {component.get('name')}", "Salary Components Setup")
        
        # Create deductions components
        for component in deductions:
            if not frappe.db.exists("Salary Component", component.get("name")):
                comp_doc = frappe.new_doc("Salary Component")
                comp_doc.salary_component = component.get("name")
                comp_doc.salary_component_abbr = component.get("abbr")
                comp_doc.type = "Deduction"
                comp_doc.variable_based_on_taxable_salary = component.get("variable_based_on_taxable_salary", False)
                comp_doc.statistical_component = component.get("statistical_component", False)
                comp_doc.flags.ignore_permissions = True
                comp_doc.insert()
                created_count += 1
                debug_log(f"Created deduction component: {component.get('name')}", "Salary Components Setup")
        
        frappe.db.commit()
        debug_log(f"Created {created_count} salary components", "Salary Components Setup")
        return created_count > 0 or (len(earnings) + len(deductions) == 0)  # True if created or if none needed
        
    except Exception as e:
        frappe.log_error(
            f"Error setting up salary components: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Salary Components Setup Error"
        )
        return False

def display_installation_summary(results, config):
    """
    Display summary of installation results
    
    Args:
        results (dict): Dictionary of setup results with component names as keys
                        and success status (True/False) as values
        config (dict): Configuration data from defaults.json
    """
    from payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.utils import debug_log
    
    success_items = []
    failed_items = []
    
    for item, success in results.items():
        if success:
            success_items.append(_(item))
        else:
            failed_items.append(_(item))
    
    # Get app version from config
    app_version = config.get("app_info", {}).get("version", "1.0.0") if config else "1.0.0"
    
    if success_items:
        success_msg = _("Payroll Indonesia v{0} has been installed. Successfully configured: {1}").format(
            app_version,
            ", ".join(success_items)
        )
        indicator = "green" if len(failed_items) == 0 else "yellow"
        frappe.msgprint(success_msg, indicator=indicator, title=_("Installation Complete"))
    
    if failed_items:
        failed_msg = _("The following components had setup issues: {0}. Please check the error logs.").format(
            ", ".join(failed_items)
        )
        frappe.msgprint(failed_msg, indicator="red", title=_("Setup Issues"))
        
        # Log diagnostic information
        diagnostic_info = {
            "success": success_items,
            "failed": failed_items,
            "timestamp": now_datetime().strftime('%Y-%m-%d %H:%M:%S'),
            "user": frappe.session.user,
            "system": {
                "frappe_version": frappe.__version__,
                "app_version": app_version
            }
        }
        
        frappe.log_error(
            f"Installation summary: {json.dumps(diagnostic_info, indent=2)}",
            "Payroll Indonesia Installation Summary"
        )