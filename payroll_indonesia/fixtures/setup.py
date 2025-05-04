# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-04 03:38:05 by dannyaudian

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
    'get_default_bpjs_values',
    'create_account_hooks',
    'debug_log',
    'display_installation_summary',
    'DEFAULT_BPJS_VALUES'
]

# Constants for default values
DEFAULT_CONFIG_PATH = "payroll_indonesia/payroll_indonesia/config/defaults.json"
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
    """
    debug_log("Starting Payroll Indonesia after_install process", "Installation")
    
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
        results["accounts"] = create_accounts()
        debug_log("Account setup completed", "Installation")
    except Exception as e:
        frappe.log_error(
            f"Error during account setup: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Account Setup Error"
        )
        
    try:
        # Setup suppliers
        results["suppliers"] = create_supplier_group()
        debug_log("Supplier group setup completed", "Installation")
    except Exception as e:
        frappe.log_error(
            f"Error during supplier setup: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Supplier Setup Error"
        )
        
    try:
        # Setup tax configuration
        pph21_settings = setup_pph21_defaults()
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
        results["ter_rates"] = setup_pph21_ter()
        debug_log("TER rates setup completed", "Installation")
    except Exception as e:
        frappe.log_error(
            f"Error during TER rates setup: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "TER Setup Error"
        )
        
    try:
        # Setup tax slab
        results["tax_slab"] = setup_income_tax_slab()
        debug_log("Tax slab setup completed", "Installation")
    except Exception as e:
        frappe.log_error(
            f"Error during tax slab setup: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Tax Slab Setup Error"
        )
    
    try:
        # Setup BPJS
        results["bpjs_setup"] = setup_bpjs()
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
    display_installation_summary(results)

def display_installation_summary(results):
    """
    Display summary of installation results
    
    Args:
        results (dict): Dictionary of setup results with component names as keys
                        and success status (True/False) as values
    """
    success_items = []
    failed_items = []
    
    for item, success in results.items():
        if success:
            success_items.append(_(item))
        else:
            failed_items.append(_(item))
    
    if success_items:
        success_msg = _("Payroll Indonesia has been installed. Successfully configured: {0}").format(
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
                "app_version": frappe.get_module("payroll_indonesia").__version__
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

def create_accounts():
    """
    Create required Accounts for Indonesian payroll management with standardized naming
    
    Returns:
        bool: True if successful, False otherwise
    """
    # Define accounts to create with standardized names
    accounts = [
        # Basic expense accounts
        {"account_name": "Beban Gaji Pokok", "parent_account": "Direct Expenses", "account_type": "Expense"},
        {"account_name": "Beban Tunjangan Makan", "parent_account": "Direct Expenses", "account_type": "Expense"},
        {"account_name": "Beban Tunjangan Transport", "parent_account": "Direct Expenses", "account_type": "Expense"},
        {"account_name": "Beban Insentif", "parent_account": "Direct Expenses", "account_type": "Expense"},
        {"account_name": "Beban Bonus", "parent_account": "Direct Expenses", "account_type": "Expense"},
        
        # BPJS expense accounts - using standardized naming
        {"account_name": "BPJS JHT Employer Expense", "parent_account": "BPJS Expenses", "account_type": "Expense"},
        {"account_name": "BPJS JP Employer Expense", "parent_account": "BPJS Expenses", "account_type": "Expense"},
        {"account_name": "BPJS JKK Employer Expense", "parent_account": "BPJS Expenses", "account_type": "Expense"},
        {"account_name": "BPJS JKM Employer Expense", "parent_account": "BPJS Expenses", "account_type": "Expense"},
        {"account_name": "BPJS Kesehatan Employer Expense", "parent_account": "BPJS Expenses", "account_type": "Expense"},
        
        # Liability accounts
        {"account_name": "Hutang PPh 21", "parent_account": "Duties and Taxes", "account_type": "Tax"},
        
        # BPJS liability accounts - using standardized naming
        {"account_name": "BPJS JHT Payable", "parent_account": "BPJS Payable", "account_type": "Payable"},
        {"account_name": "BPJS JP Payable", "parent_account": "BPJS Payable", "account_type": "Payable"},
        {"account_name": "BPJS Kesehatan Payable", "parent_account": "BPJS Payable", "account_type": "Payable"},
        {"account_name": "BPJS JKK Payable", "parent_account": "BPJS Payable", "account_type": "Payable"},
        {"account_name": "BPJS JKM Payable", "parent_account": "BPJS Payable", "account_type": "Payable"}
    ]
    
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
            
            # Create parent accounts for BPJS
            parent_accounts = [
                {"account_name": "BPJS Payable", "parent_account": "Duties and Taxes", "account_type": "Payable", "is_group": 1, "root_type": "Liability"},
                {"account_name": "BPJS Expenses", "parent_account": "Direct Expenses", "account_type": "Expense", "is_group": 1, "root_type": "Expense"}
            ]
            
            # Create BPJS parent accounts first with better error handling
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
                    parent = find_parent_account(company, template_parent, company_abbr, parent_account["account_type"])
                    
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
                        "is_group": 1
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

def create_account(company, account_name, account_type, parent):
    """
    Create GL Account if not exists
    
    Args:
        company (str): Company name
        account_name (str): Account name without company abbreviation
        account_type (str): Account type (Payable, Receivable, etc.)
        parent (str): Parent account name
        
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
            
        # Determine root_type based on account_type
        if account_type in ["Payable", "Receivable", "Tax", "Liability"]:
            root_type = "Liability"
        elif account_type == "Asset":
            root_type = "Asset"
        elif account_type == "Expense":
            root_type = "Expense"
        elif account_type == "Income":
            root_type = "Income"
        else:
            root_type = "Asset"  # Default fallback
            
        # Create new account with explicit permissions
        debug_log(f"Creating account: {full_account_name} (Type: {account_type}, Parent: {parent})", "Account Creation")
        
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

def find_parent_account(company, parent_name, company_abbr, account_type):
    """
    Find parent account with multiple fallback options
    
    Args:
        company (str): Company name
        parent_name (str): Parent account name
        company_abbr (str): Company abbreviation
        account_type (str): Account type to find appropriate parent
        
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
    
    # Handle BPJS parent account names
    if parent_name == "BPJS Payable" or parent_name == "BPJS Expenses":
        # Get parent account based on account type
        if "Payable" in parent_name:
            parent_candidates = ["Duties and Taxes", "Current Liabilities", "Accounts Payable"]
            debug_log(f"Looking for liability parent among: {', '.join(parent_candidates)}", "Account Lookup")
        else:
            parent_candidates = ["Direct Expenses", "Indirect Expenses", "Expenses"]
            debug_log(f"Looking for expense parent among: {', '.join(parent_candidates)}", "Account Lookup")
            
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
    root_type = "Expense" if account_type == "Expense" else "Liability"
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

def setup_pph21_defaults():
    """
    Setup default PPh 21 configuration with TER method
    
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
        
        # Set TER as default calculation method
        settings.calculation_method = "TER"
        settings.use_ter = 1
        settings.ter_notes = "Tarif Efektif Rata-rata (TER) sesuai PMK-168/PMK.010/2023"
        
        # Add PTKP values
        ptkp_values = {
            "TK0": 54000000,  # tidak kawin, 0 tanggungan
            "TK1": 58500000,  # tidak kawin, 1 tanggungan
            "TK2": 63000000,  # tidak kawin, 2 tanggungan
            "TK3": 67500000,  # tidak kawin, 3 tanggungan
            "K0": 58500000,   # kawin, 0 tanggungan
            "K1": 63000000,   # kawin, 1 tanggungan
            "K2": 67500000,   # kawin, 2 tanggungan
            "K3": 72000000,   # kawin, 3 tanggungan
            "HB0": 112500000, # kawin penghasilan istri digabung, 0 tanggungan
            "HB1": 117000000, # kawin penghasilan istri digabung, 1 tanggungan
            "HB2": 121500000, # kawin penghasilan istri digabung, 2 tanggungan
            "HB3": 126000000  # kawin penghasilan istri digabung, 3 tanggungan
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
        
        # Add tax brackets
        brackets = [
            {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
            {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
            {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
            {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
            {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
        ]
        
        for bracket in brackets:
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

def setup_pph21_ter():
    """
    Setup default TER rates based on PMK-168/PMK.010/2023
    
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
        
        # Load TER rates from JSON file
        ter_rates = get_ter_rates()
        if not ter_rates:
            debug_log("No TER rates found", "TER Setup Error")
            return False
            
        # Create TER rates
        count = 0
        status_list = list(ter_rates.keys())
        
        for status in status_list:
            for rate_data in ter_rates[status]:
                try:
                    # Create description
                    if rate_data["income_to"] == 0:
                        description = f"{status} > Rp{rate_data['income_from']:,.0f}"
                    elif rate_data["income_from"] == 0:
                        description = f"{status} ≤ Rp{rate_data['income_to']:,.0f}"
                    else:
                        description = f"{status} Rp{rate_data['income_from']:,.0f}-Rp{rate_data['income_to']:,.0f}"
                    
                    ter_entry = frappe.get_doc({
                        "doctype": "PPh 21 TER Table",
                        "status_pajak": status,
                        "income_from": flt(rate_data["income_from"]),
                        "income_to": flt(rate_data["income_to"]),
                        "rate": flt(rate_data["rate"]),
                        "description": description
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
        debug_log(f"Created {count} TER rates successfully", "TER Setup")
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
    Get TER rates either from file or hardcoded defaults
    
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
    # Return hardcoded minimal rates (TK0 & K0 only for brevity)
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
        ],
        "K0": [
            {"income_from": 0, "income_to": 4875000, "rate": 0},
            {"income_from": 4875000, "income_to": 5500000, "rate": 0.5},
            {"income_from": 5500000, "income_to": 6500000, "rate": 1.0},
            {"income_from": 6500000, "income_to": 7500000, "rate": 1.75},
            {"income_from": 7500000, "income_to": 8500000, "rate": 2.25},
            {"income_from": 8500000, "income_to": 9500000, "rate": 2.75},
            {"income_from": 9500000, "income_to": 11000000, "rate": 3.25},
            {"income_from": 11000000, "income_to": 15500000, "rate": 4.0},
            {"income_from": 15500000, "income_to": 21500000, "rate": 5.0},
            {"income_from": 21500000, "income_to": 500000000, "rate": 7.0},
            {"income_from": 500000000, "income_to": 0, "rate": 9.5}
        ]
    }

def setup_income_tax_slab():
    """
    Create Income Tax Slab for Indonesia
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Skip if already exists
        existing_slabs = frappe.get_all(
            "Income Tax Slab",
            filters={"currency": "IDR", "is_default": 1, "disabled": 0},
            fields=["name"]
        )
        
        if existing_slabs:
            debug_log(f"Default Income Tax Slab already exists: {existing_slabs[0].name}", "Tax Slab Setup")
            return True
        
        # Get company
        company = frappe.db.get_default("company")
        if not company:
            companies = frappe.get_all("Company", pluck="name")
            if companies:
                company = companies[0]
            else:
                debug_log("No company found for Income Tax Slab", "Tax Slab Setup Error")
                return False
        
        # Create tax slab
        tax_slab = frappe.new_doc("Income Tax Slab")
        tax_slab.title = "Indonesia Income Tax" 
        tax_slab.effective_from = getdate("2023-01-01")
        tax_slab.company = company
        tax_slab.currency = "IDR"
        tax_slab.is_default = 1
        tax_slab.disabled = 0

        # Add tax brackets
        tax_slab.append("slabs", {"from_amount": 0, "to_amount": 60000000, "percent_deduction": 5})
        tax_slab.append("slabs", {"from_amount": 60000000, "to_amount": 250000000, "percent_deduction": 15})
        tax_slab.append("slabs", {"from_amount": 250000000, "to_amount": 500000000, "percent_deduction": 25})
        tax_slab.append("slabs", {"from_amount": 500000000, "to_amount": 5000000000, "percent_deduction": 30})
        tax_slab.append("slabs", {"from_amount": 5000000000, "to_amount": 0, "percent_deduction": 35})
            
        # Save with permissions
        tax_slab.flags.ignore_permissions = True
        tax_slab.insert(ignore_permissions=True)
        
        # Commit immediately
        frappe.db.commit()
        
        debug_log(f"Created Income Tax Slab: {tax_slab.name}", "Tax Slab Setup")
        return True
        
    except Exception as e:
        frappe.log_error(
            f"Error creating Income Tax Slab: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Tax Slab Setup Error"
        )
        return False

def setup_bpjs():
    """
    Setup BPJS configurations and account mappings for all companies
    
    Creates BPJS Settings document and ensures BPJS Account Mapping for all companies
    is automatically created during application installation.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create BPJS Settings
        settings = create_bpjs_settings()
        if not settings:
            debug_log("Failed to create BPJS Settings", "BPJS Setup Error")
            return False
        
        debug_log("Created BPJS Settings successfully", "BPJS Setup")
            
        # Let BPJS Settings handle account setup
        settings.setup_accounts()
        
        # Get all companies
        companies = frappe.get_all("Company", pluck="name")
        if not companies:
            debug_log("No companies found for BPJS account mapping", "BPJS Setup Warning")
            return True  # Return True as settings were created successfully
        
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
                mapping = create_default_mapping(company)
                
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

def create_bpjs_settings():
    """
    Create and configure BPJS Settings
    
    Returns:
        object: BPJS Settings document if successful, None otherwise
    """
    try:
        # Check if already exists
        if frappe.db.exists("BPJS Settings", "BPJS Settings"):
            debug_log("BPJS Settings already exists, retrieving", "BPJS Setup")
            return frappe.get_doc("BPJS Settings", "BPJS Settings")
            
        # Load defaults from config or use hardcoded values
        values = get_default_bpjs_values()
        debug_log(f"Creating new BPJS Settings with default values", "BPJS Setup")
            
        # Create settings
        settings = frappe.new_doc("BPJS Settings")
        
        # Set values
        for key, value in values.items():
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

def get_default_bpjs_values():
    """
    Get default BPJS values from config file or use defaults
    
    Returns:
        dict: Default BPJS values
    """
    try:
        # Try to load from file
        config_path = frappe.get_app_path("payroll_indonesia", DEFAULT_CONFIG_PATH)
        debug_log(f"Looking for BPJS default values at: {config_path}", "BPJS Setup")
        
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                values = json.load(f)
                
                # Validate required keys
                missing_keys = []
                for key in DEFAULT_BPJS_VALUES:
                    if key not in values:
                        values[key] = DEFAULT_BPJS_VALUES[key]
                        missing_keys.append(key)
                
                if missing_keys:
                    debug_log(f"Some keys were missing in config file and were set to defaults: {', '.join(missing_keys)}", "BPJS Setup")
                        
                debug_log("Loaded BPJS default values from file", "BPJS Setup")
                return values
    except Exception as e:
        debug_log(f"Error loading BPJS defaults from file: {str(e)}", "BPJS Setup Error")
        
    debug_log("Using hardcoded BPJS default values", "BPJS Setup")
    return DEFAULT_BPJS_VALUES

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
# Last modified: 2025-05-04 03:38:05 by dannyaudian

import frappe
from frappe.utils import now_datetime

def account_on_update(doc, method=None):
    \"\"\"Hook when accounts are updated\"\"\"
    if doc.account_type in ["Payable", "Expense", "Liability"] and ("BPJS" in doc.account_name):
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

def debug_log(message, title=None, max_length=500):
    """
    Debug logging helper with consistent format
    
    Args:
        message (str): Message to log
        title (str, optional): Optional title/context for the log
        max_length (int, optional): Maximum message length (default: 500)
    """
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    
    # Truncate if message is too long to avoid memory issues
    message = str(message)[:max_length]
    
    if title:
        log_message = f"[{timestamp}] [{title}] {message}"
    else:
        log_message = f"[{timestamp}] {message}"
        
    # Log to both debug logger and application logs
    frappe.logger().debug(f"[SETUP] {log_message}")
    
    # Create application log for important messages
    if title and title.endswith("Error"):
        frappe.log_error(message, f"Setup {title}")