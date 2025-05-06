# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-06 15:05:12 by dannyaudian

import frappe
from frappe import _
from frappe.utils import getdate, flt, now_datetime
import json
import os

__all__ = [
    'before_install',
    'after_install',
    'check_system_readiness',
    'create_accounts',
    'create_account',
    'find_parent_account',
    'create_supplier_group',
    'setup_pph21_defaults',
    'setup_pph21_ter',
    'get_ter_rates',
    'setup_income_tax_slab',
    'setup_bpjs',
    'create_bpjs_settings',
    'get_default_config',
    'create_account_hooks',
    'debug_log',
    'display_installation_summary',
]

# Constants for default values
DEFAULT_CONFIG_PATH = "payroll_indonesia/payroll_indonesia/config/defaults.json"

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
    Setup requirements after installing the app with improved error handling
    
    Creates accounts, sets up tax configuration, configures BPJS and more.
    The custom fields are handled by the fixtures automatically.
    """
    debug_log("Starting Payroll Indonesia after_install process", "Installation")
    
    # Load configuration defaults
    config = get_default_config()
    
    # Track setup results
    results = {
        "accounts": False,
        "suppliers": False,
        "pph21_settings": False,
        "ter_rates": False,
        "tax_slab": False,
        "bpjs_setup": False
    }
    
    try:
        # Create accounts first (required for salary components)
        results["accounts"] = create_accounts(config)
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
        # Setup tax configuration
        pph21_settings = setup_pph21_defaults(config)
        results["pph21_settings"] = bool(pph21_settings)
        debug_log("PPh 21 setup completed", "Installation")
    except Exception as e:
        frappe.log_error(
            f"Error during PPh 21 setup: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "PPh 21 Setup Error"
        )
        
    try:
        # Setup TER rates
        results["ter_rates"] = setup_pph21_ter(config)
        debug_log("TER rates setup completed", "Installation")
    except Exception as e:
        frappe.log_error(
            f"Error during TER rates setup: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "TER Setup Error"
        )
        
    try:
        # Setup tax slab
        results["tax_slab"] = setup_income_tax_slab(config)
        debug_log("Tax slab setup completed", "Installation")
    except Exception as e:
        frappe.log_error(
            f"Error during tax slab setup: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Tax Slab Setup Error"
        )
    
    try:
        # Setup BPJS
        results["bpjs_setup"] = setup_bpjs(config)
        debug_log("BPJS setup completed", "Installation")
    except Exception as e:
        frappe.log_error(
            f"Error during BPJS setup: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Setup Error"
        )
        
    try:
        # Create account hooks
        create_account_hooks()
        debug_log("Created account hooks", "Installation")
    except Exception as e:
        frappe.log_error(
            f"Error creating account hooks: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Account Hooks Setup Error"
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

def display_installation_summary(results, config):
    """
    Display summary of installation results
    
    Args:
        results (dict): Dictionary of setup results with component names as keys
                        and success status (True/False) as values
        config (dict): Configuration data from defaults.json
    """
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

def check_system_readiness():
    """
    Check if system is ready for Payroll Indonesia installation
    
    Returns:
        bool: True if ready, False otherwise
    """
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

def create_accounts(config):
    """
    Create required Accounts for Indonesian payroll management with standardized naming
    
    Args:
        config (dict): Configuration data from defaults.json
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not config:
        debug_log("No configuration data available for creating accounts", "Account Setup")
        return False
        
    gl_accounts = config.get("gl_accounts", {})
    if not gl_accounts:
        debug_log("No GL accounts configuration found in defaults.json", "Account Setup")
        return False
    
    # Build account list from config
    accounts = []
    
    # Add expense accounts
    for _, account_info in gl_accounts.get("expense_accounts", {}).items():
        accounts.append(account_info)
        
    # Add BPJS expense accounts
    for _, account_info in gl_accounts.get("bpjs_expense_accounts", {}).items():
        accounts.append(account_info)
        
    # Add payable accounts
    for _, account_info in gl_accounts.get("payable_accounts", {}).items():
        accounts.append(account_info)
        
    # Add BPJS payable accounts
    for _, account_info in gl_accounts.get("bpjs_payable_accounts", {}).items():
        accounts.append(account_info)
    
    # Get parent accounts from config
    parent_accounts = []
    for _, parent_info in gl_accounts.get("parent_accounts", {}).items():
        parent_accounts.append(parent_info)
    
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
            
            debug_log(f"Creating accounts for company: {company} (Abbr: {company_abbr})", "Account Setup")
            
            # Create parent accounts first with better error handling
            created_parents = []
            for parent_account in parent_accounts:
                try:
                    # Calculate full account name with company abbreviation
                    full_account_name = f"{parent_account['account_name']} - {company_abbr}"
                    
                    # Check if account already exists
                    if frappe.db.exists("Account", full_account_name):
                        # Verify the account is a group account
                        is_group = frappe.db.get_value("Account", full_account_name, "is_group")
                        if not is_group:
                            # Make it a group account
                            account_doc = frappe.get_doc("Account", full_account_name)
                            account_doc.is_group = 1
                            account_doc.flags.ignore_permissions = True
                            account_doc.save()
                            debug_log(f"Updated {full_account_name} to be a group account", "Account Fix")
                            
                        created_parents.append(full_account_name)
                        debug_log(f"Parent account already exists: {full_account_name}", "Account Setup")
                        continue
                    
                    # Find parent account from the template
                    template_parent = parent_account["parent_account"]
                    
                    # Get candidate list for parent account types from config
                    candidates = []
                    if "root_type" in parent_account:
                        if parent_account["root_type"] == "Liability":
                            candidates = gl_accounts.get("parent_account_candidates", {}).get("liability", [])
                        elif parent_account["root_type"] == "Expense":
                            candidates = gl_accounts.get("parent_account_candidates", {}).get("expense", [])
                    
                    parent = find_parent_account(
                        company, 
                        template_parent, 
                        company_abbr, 
                        parent_account["account_type"],
                        candidates
                    )
                    
                    if not parent:
                        debug_log(f"Could not find parent account {template_parent} for {company}", "Account Setup")
                        continue
                        
                    # Create new parent account
                    doc = frappe.get_doc({
                        "doctype": "Account",
                        "account_name": parent_account["account_name"],
                        "company": company,
                        "parent_account": parent,
                        "account_type": parent_account["account_type"],
                        "root_type": parent_account["root_type"],
                        "account_currency": frappe.get_cached_value('Company', company, 'default_currency'),
                        "is_group": parent_account["is_group"]
                    })
                    
                    # Bypass permissions for installation/setup
                    doc.flags.ignore_permissions = True
                    doc.flags.ignore_mandatory = True
                    doc.insert(ignore_permissions=True)
                    
                    # Commit immediately to make account available
                    frappe.db.commit()
                    
                    created_parents.append(full_account_name)
                    debug_log(f"Created parent account: {full_account_name}", "Account Creation")
                    
                except Exception as e:
                    frappe.log_error(
                        f"Error creating parent account {parent_account['account_name']} for {company}: {str(e)}\n\n"
                        f"Traceback: {frappe.get_traceback()}",
                        "Account Creation Error"
                    )
                    overall_success = False
            
            # Now create individual accounts
            created_accounts = []
            failed_accounts = []
                
            # Create each account
            for account in accounts:
                try:
                    # Find parent account - use the created parent or find standard parent
                    if account["parent_account"] in ["BPJS Payable", "BPJS Expenses"]:
                        # Use the BPJS parent accounts we just created
                        parent_name = f"{account['parent_account']} - {company_abbr}"
                        if parent_name in created_parents:
                            parent_account = parent_name
                        else:
                            debug_log(f"BPJS parent {parent_name} not found, skipping {account['account_name']}", "Account Setup")
                            continue
                    else:
                        # Find standard parent account
                        parent_account = find_parent_account(company, account["parent_account"], company_abbr, account["account_type"])
                        if not parent_account:
                            failed_accounts.append(account["account_name"])
                            debug_log(f"Could not find parent account {account['parent_account']} for {company}", "Account Setup")
                            continue
                            
                    # Create account using standardized function
                    full_account_name = create_account(
                        company=company,
                        account_name=account["account_name"],
                        account_type=account["account_type"],
                        parent=parent_account,
                        root_type=account.get("root_type")
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

def create_account(company, account_name, account_type, parent, root_type=None):
    """
    Create GL Account if not exists
    
    Args:
        company (str): Company name
        account_name (str): Account name without company abbreviation
        account_type (str): Account type (Payable, Receivable, etc.)
        parent (str): Parent account name
        root_type (str, optional): Root type (Asset, Liability, etc.). If None, determined from account_type.
        
    Returns:
        str: Full account name if created or already exists, None otherwise
    """
    try:
        # Validate inputs
        if not company or not account_name or not account_type or not parent:
            debug_log(f"Missing required parameter for account creation: company={company}, account_name={account_name}, account_type={account_type}, parent={parent}", "Account Creation Error")
            return None
            
        abbr = frappe.get_cached_value('Company', company, 'abbr')
        if not abbr:
            debug_log(f"Company {company} has no abbreviation", "Account Creation Error")
            return None
            
        # Standardize account name (remove company suffix if already present)
        pure_account_name = account_name.replace(f" - {abbr}", "")
        full_account_name = f"{pure_account_name} - {abbr}"
        
        # Check if account already exists
        if frappe.db.exists("Account", full_account_name):
            debug_log(f"Account {full_account_name} already exists", "Account Creation")
            return full_account_name
            
        # Verify parent account exists
        if not frappe.db.exists("Account", parent):
            debug_log(f"Parent account {parent} does not exist", "Account Creation Error")
            return None
            
        # Determine root_type based on account_type if not provided
        if not root_type:
            root_type = "Liability"  # Default
            if account_type in ["Direct Expense", "Indirect Expense", "Expense Account"]:
                root_type = "Expense"
            elif account_type == "Asset":
                root_type = "Asset"
            elif account_type in ["Direct Income", "Indirect Income", "Income Account"]:
                root_type = "Income"
            
        # Create new account with explicit permissions
        debug_log(f"Creating account: {full_account_name} (Type: {account_type}, Parent: {parent}, Root: {root_type})", "Account Creation")
        
        doc = frappe.get_doc({
            "doctype": "Account",
            "account_name": pure_account_name,
            "company": company,
            "parent_account": parent,
            "account_type": account_type,
            "account_currency": frappe.get_cached_value('Company', company, 'default_currency'),
            "is_group": 0,
            "root_type": root_type
        })
        
        # Bypass permissions and mandatory checks during setup
        doc.flags.ignore_permissions = True
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        
        # Commit database changes immediately for availability
        frappe.db.commit()
        
        # Verify account was created
        if frappe.db.exists("Account", full_account_name):
            debug_log(f"Successfully created account: {full_account_name}", "Account Creation")
            return full_account_name
        else:
            debug_log(f"Failed to create account {full_account_name} despite no errors", "Account Creation Error")
            return None
        
    except Exception as e:
        frappe.log_error(
            f"Error creating account {account_name} for {company}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Account Creation Error"
        )
        debug_log(f"Error creating account {account_name}: {str(e)}", "Account Creation Error")
        return None

def find_parent_account(company, parent_name, company_abbr, account_type, candidates=None):
    """
    Find parent account with multiple fallback options
    
    Args:
        company (str): Company name
        parent_name (str): Parent account name
        company_abbr (str): Company abbreviation
        account_type (str): Account type to find appropriate parent
        candidates (list, optional): List of candidate parent account names to try
        
    Returns:
        str: Parent account name if found, None otherwise
    """
    debug_log(f"Finding parent account: {parent_name} for company {company}", "Account Lookup")
    
    # Try exact name
    parent = frappe.db.get_value(
        "Account", 
        {"account_name": parent_name, "company": company}, 
        "name"
    )
    if parent:
        debug_log(f"Found parent account by exact name match: {parent}", "Account Lookup")
        return parent
        
    # Try with company abbreviation
    parent = frappe.db.get_value(
        "Account", 
        {"name": f"{parent_name} - {company_abbr}"}, 
        "name"
    )
    if parent:
        debug_log(f"Found parent account with company suffix: {parent}", "Account Lookup")
        return parent
    
    # Handle BPJS parent account names or use provided candidates
    if parent_name == "BPJS Payable" or parent_name == "BPJS Expenses" or not candidates:
        # Get parent account based on account type
        if "Payable" in parent_name or account_type in ["Payable", "Tax"]:
            parent_candidates = candidates or ["Duties and Taxes", "Current Liabilities", "Accounts Payable"]
            debug_log(f"Looking for liability parent among: {', '.join(parent_candidates)}", "Account Lookup")
        else:
            # Look for expense parent accounts with valid account types
            parent_candidates = candidates or ["Direct Expenses", "Indirect Expenses", "Expenses"]
            debug_log(f"Looking for expense parent among: {', '.join(parent_candidates)}", "Account Lookup")
    else:
        parent_candidates = candidates
        debug_log(f"Using provided candidates for parent accounts: {', '.join(parent_candidates)}", "Account Lookup")
            
    for candidate in parent_candidates:
        candidate_account = frappe.db.get_value(
            "Account", 
            {"account_name": candidate, "company": company}, 
            "name"
        )
        
        if candidate_account:
            debug_log(f"Found parent {candidate_account} for {parent_name}", "Account Lookup")
            return candidate_account
            
        candidate_account = frappe.db.get_value(
            "Account", 
            {"name": f"{candidate} - {company_abbr}"}, 
            "name"
        )
            
        if candidate_account:
            debug_log(f"Found parent {candidate_account} for {parent_name}", "Account Lookup")
            return candidate_account
    
    # Try broad search for accounts with similar name
    similar_accounts = frappe.db.get_list(
        "Account",
        filters={
            "company": company,
            "is_group": 1,
            "account_name": ["like", f"%{parent_name}%"]
        },
        fields=["name"]
    )
    if similar_accounts:
        debug_log(f"Found similar parent account: {similar_accounts[0].name}", "Account Lookup")
        return similar_accounts[0].name
        
    # Try any group account of correct type as fallback
    # Use correct mapping for account types
    root_type = "Expense"  # Default for expense accounts
    if account_type in ["Payable", "Receivable", "Tax"]:
        root_type = "Liability"
    elif account_type in ["Direct Income", "Indirect Income", "Income Account"]:
        root_type = "Income"
    
    debug_log(f"Searching for any {root_type} group account as fallback", "Account Lookup")
    
    parents = frappe.get_all(
        "Account", 
        filters={"company": company, "is_group": 1, "root_type": root_type},
        pluck="name",
        limit=1
    )
    if parents:
        debug_log(f"Using fallback parent account: {parents[0]}", "Account Lookup")
        return parents[0]
    
    debug_log(f"Could not find any suitable parent account for {parent_name}", "Account Lookup Error") 
    return None

def create_supplier_group():
    """
    Create Government supplier group for tax and BPJS entities
    
    Returns:
        bool: True if successful, False otherwise
    """
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
    Create BPJS supplier entity
    
    Args:
        config (dict): Configuration data from defaults.json
        
    Returns:
        bool: True if successful, False otherwise
    """
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
            debug_log(f"Supplier group {supplier_group} does not exist", "Supplier Setup")
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

def setup_pph21_defaults(config):
    """
    Setup default PPh 21 configuration with TER method using config data
    
    Args:
        config (dict): Configuration data from defaults.json
        
    Returns:
        object: PPh 21 Settings document if successful, None otherwise
    """
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
        
        # Run on_update method to validate settings if exists
        try:
            if hasattr(settings, 'on_update'):
                settings.on_update()
        except Exception as e:
            debug_log(f"Non-critical error during settings on_update: {str(e)}", "PPh 21 Setup")
            
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
            debug_log("No TER rates found in config, loading from separate file", "TER Setup")
            ter_rates = get_ter_rates()
            
        if not ter_rates:
            debug_log("No TER rates found", "TER Setup Error")
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
                    # It's highest if it's the last item or if income_to is 0
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
                        debug_log(f"Updated TER rate for {status} with range {rate_data['income_from']}-{rate_data['income_to']}", "TER Setup")
                    else:
                        # Create TER entry with is_highest_bracket flag for entries with income_to=0
                        ter_entry = frappe.get_doc({
                            "doctype": "PPh 21 TER Table",
                            "status_pajak": status,
                            "income_from": flt(rate_data["income_from"]),
                            "income_to": flt(rate_data["income_to"]),
                            "rate": flt(rate_data["rate"]),
                            "description": description,
                            "is_highest_bracket": 1 if is_highest else 0  # Set the flag for highest bracket
                        })
                        
                        # Add debug message to confirm highest bracket setting
                        if is_highest:
                            debug_log(f"Setting highest bracket flag for {status} with rate {rate_data['rate']}", "TER Setup")
                        
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

def get_ter_rates():
    """
    Get TER rates from file if not provided in config
    
    Returns:
        dict: TER rates by status
    """
    try:
        # Check if file exists
        ter_path = frappe.get_app_path("payroll_indonesia", "payroll_indonesia", "config", "ter_rates.json")
        debug_log(f"Looking for TER rates at: {ter_path}", "TER Setup")
        
        if os.path.exists(ter_path):
            with open(ter_path, "r") as f:
                rates = json.load(f)
                debug_log(f"Loaded TER rates from file with {len(rates)} statuses", "TER Setup")
                return rates
    except Exception as e:
        debug_log(f"Error loading TER rates from file: {str(e)}", "TER Setup Error")
        
    debug_log("Using hardcoded TER rates", "TER Setup")
    # Return hardcoded minimal rates as fallback
    return {
        "TK0": [
            {"income_from": 0, "income_to": 4500000, "rate": 0},
            {"income_from": 4500000, "income_to": 5000000, "rate": 0.5},
            {"income_from": 5000000, "income_to": 6000000, "rate": 1.0},
            {"income_from": 6000000, "income_to": 7000000, "rate": 1.75},
            {"income_from": 7000000, "income_to": 8000000, "rate": 2.5},
            {"income_from": 8000000, "income_to": 9000000, "rate": 3.0},
            {"income_from": 9000000, "income_to": 10000000, "rate": 3.5},
            {"income_from": 10000000, "income_to": 15000000, "rate": 4.5},
            {"income_from": 15000000, "income_to": 20000000, "rate": 5.5},
            {"income_from": 20000000, "income_to": 500000000, "rate": 7.5},
            {"income_from": 500000000, "income_to": 0, "rate": 10.0}
        ]
    }

def setup_income_tax_slab(config):
    """
    Create Income Tax Slab for Indonesia using config data
    
    Args:
        config (dict): Configuration data from defaults.json
        
    Returns:
        bool: True if successful, False otherwise
    """
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

def setup_bpjs(config):
    """
    Setup BPJS configurations and account mappings for all companies using config data
    
    Args:
        config (dict): Configuration data from defaults.json
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create BPJS Settings
        settings = create_bpjs_settings(config)
        if not settings:
            debug_log("Failed to create BPJS Settings", "BPJS Setup Error")
            return False
        
        debug_log("Created BPJS Settings successfully", "BPJS Setup")
            
        # Run setup_accounts method if exists
        if hasattr(settings, 'setup_accounts'):
            settings.setup_accounts()
        
        # Get all companies
        companies = frappe.get_all("Company", pluck="name")
        if not companies:
            debug_log("No companies found for BPJS account mapping", "BPJS Setup Warning")
            return True  # Return True as settings were created successfully
        
        # Get account mapping configuration
        bpjs_account_mapping = config.get("gl_accounts", {}).get("bpjs_account_mapping", {})
        
        # Track success and failures
        success_count = 0
        failed_companies = []
        
        # Create mappings for each company
        for company in companies:
            try:
                debug_log(f"Creating BPJS account mapping for company: {company}", "BPJS Setup")
                
                # Check if mapping already exists
                existing_mapping = frappe.db.exists("BPJS Account Mapping", {"company": company})
                if existing_mapping:
                    debug_log(f"BPJS account mapping already exists for {company}", "BPJS Setup")
                    success_count += 1
                    continue
                
                # Create default mapping for this company
                from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import create_default_mapping
                mapping = create_default_mapping(company, bpjs_account_mapping)
                
                if mapping:
                    debug_log(f"Successfully created BPJS account mapping for {company}", "BPJS Setup")
                    success_count += 1
                else:
                    debug_log(f"Failed to create BPJS account mapping for {company}", "BPJS Setup Error")
                    failed_companies.append(company)
                        
            except Exception as e:
                frappe.log_error(
                    f"Error creating BPJS account mapping for {company}: {str(e)}\n\n"
                    f"Traceback: {frappe.get_traceback()}",
                    "BPJS Setup Error"
                )
                failed_companies.append(company)
        
        # Commit all changes
        frappe.db.commit()
        
        # Log summary
        if success_count > 0:
            debug_log(f"Successfully created BPJS account mappings for {success_count} companies", "BPJS Setup")
            
        if failed_companies:
            debug_log(f"Failed to create BPJS account mappings for {len(failed_companies)} companies: {', '.join(failed_companies)}", "BPJS Setup Warning")
            
            # Schedule background job to retry failed companies
            try:
                frappe.enqueue(
                    method="payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.bpjs_settings.retry_bpjs_mapping",
                    companies=failed_companies,
                    queue="long",
                    timeout=1500
                )
                debug_log(f"Scheduled background job to retry BPJS mapping creation for failed companies", "BPJS Setup")
            except Exception as e:
                frappe.log_error(
                    f"Failed to schedule retry for BPJS mapping: {str(e)}\n\n"
                    f"Traceback: {frappe.get_traceback()}", 
                    "BPJS Mapping Error"
                )
        
        # Return True if at least some mappings were created or if none were needed
        return True
        
    except Exception as e:
        frappe.log_error(
            f"Error setting up BPJS: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Setup Error"
        )
        return False

def create_bpjs_settings(config):
    """
    Create and configure BPJS Settings using config data
    
    Args:
        config (dict): Configuration data from defaults.json
        
    Returns:
        object: BPJS Settings document if successful, None otherwise
    """
    try:
        # Check if already exists
        if frappe.db.exists("BPJS Settings", "BPJS Settings"):
            debug_log("BPJS Settings already exists, retrieving", "BPJS Setup")
            return frappe.get_doc("BPJS Settings", "BPJS Settings")
            
        # Load values from config
        bpjs_config = config.get("bpjs", {})
        if not bpjs_config:
            debug_log("No BPJS config found, using defaults", "BPJS Setup")
            # Fallback to defaults
            bpjs_config = {
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
            
        debug_log(f"Creating new BPJS Settings with values from config", "BPJS Setup")
            
        # Create settings
        settings = frappe.new_doc("BPJS Settings")
        
        # Set values from config
        for key, value in bpjs_config.items():
            if hasattr(settings, key):
                settings.set(key, flt(value))
        
        # Bypass validation during setup
        settings.flags.ignore_validate = True
        settings.flags.ignore_permissions = True
        settings.insert(ignore_permissions=True)
        
        # Commit to make available to subsequent functions
        frappe.db.commit()
        
        debug_log("BPJS Settings created successfully", "BPJS Setup")
        return settings
        
    except Exception as e:
        frappe.log_error(
            f"Error creating BPJS Settings: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Setup Error"
        )
        return None

def get_default_config():
    """
    Get configuration data from defaults.json
    
    Returns:
        dict: Configuration data
    """
    try:
        # Check if file exists
        config_path = frappe.get_app_path("payroll_indonesia", DEFAULT_CONFIG_PATH)
        debug_log(f"Looking for configuration at: {config_path}", "Config")
        
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)
                debug_log("Loaded configuration from defaults.json", "Config")
                return config
    except Exception as e:
        debug_log(f"Error loading configuration: {str(e)}", "Config Error")
        frappe.log_error(
            f"Error loading configuration: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Configuration Error"
        )
        
    debug_log("Using empty configuration", "Config")
    return {}

def create_account_hooks():
    """
    Create hooks for account updates
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        account_hooks_path = frappe.get_app_path("payroll_indonesia", "payroll_indonesia", "account_hooks.py")
        debug_log(f"Creating account hooks at: {account_hooks_path}", "Setup")
        
        with open(account_hooks_path, "w") as f:
            f.write("""# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-06 15:05:12 by dannyaudian

import frappe
from frappe.utils import now_datetime

def account_on_update(doc, method=None):
    \"\"\"Hook when accounts are updated\"\"\"
    # FIXED: Updated account types to match valid options
    if doc.account_type in ["Payable", "Direct Expense", "Indirect Expense", "Expense Account", "Liability"] and ("BPJS" in doc.account_name):
        # Update BPJS mappings
        update_bpjs_mappings(doc)

def update_bpjs_mappings(account_doc):
    \"\"\"Update BPJS mappings that use this account\"\"\"
    # Get all mappings for this company
    mappings = frappe.get_all(
        "BPJS Account Mapping",
        filters={"company": account_doc.company},
        pluck="name"
    )
    
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    
    for mapping_name in mappings:
        mapping = frappe.get_doc("BPJS Account Mapping", mapping_name)
        
        # Check all account fields for a match
        account_fields = [
            "kesehatan_employee_account", "jht_employee_account", "jp_employee_account",
            "kesehatan_employer_debit_account", "jht_employer_debit_account",
            "jp_employer_debit_account", "jkk_employer_debit_account", "jkm_employer_debit_account",
            "kesehatan_employer_credit_account", "jht_employer_credit_account",
            "jp_employer_credit_account", "jkk_employer_credit_account", "jkm_employer_credit_account"
        ]
        
        updated = False
        for field in account_fields:
            if hasattr(mapping, field) and getattr(mapping, field) == account_doc.name:
                # Account is being used in this mapping
                updated = True
        
        if updated:
            # Clear cache for this mapping
            frappe.cache().delete_value(f"bpjs_mapping_{mapping.company}")
            frappe.logger().info(f"[{timestamp}] Cleared cache for BPJS mapping {mapping_name} due to account update")
""")
            
        debug_log("Successfully created account_hooks.py", "Setup")
        return True
    except Exception as e:
        frappe.log_error(
            f"Error creating account_hooks.py: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Setup Error"
        )
        return False

def debug_log(message, title="Debug", trace=False):
    """
    Utility to log debug messages with optional traceback
    
    Args:
        message (str): Message to log
        title (str): Title for grouping
        trace (bool): Whether to include frappe.get_traceback()
    """
    try:
        if trace:
            message += "\n\n" + frappe.get_traceback()
        print(f"[{title}] {message}")
    except Exception:
        pass