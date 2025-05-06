# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-06 15:51:10 by dannyaudian

import frappe
import json
import os
from frappe import _
from frappe.utils import flt, now_datetime

__all__ = [
    'validate_settings', 
    'setup_accounts',
    'get_default_config',
    'find_parent_account',
    'create_account',
    'create_parent_liability_account',
    'create_parent_expense_account',
    'retry_bpjs_mapping',
    'debug_log'
]

# Config handling functions
def get_default_config():
    """
    Load configuration from defaults.json with caching
    
    Returns:
        dict: Configuration data from defaults.json or empty dict if not found/error
    """
    # Try to get from cache first
    config = frappe.cache().get_value("payroll_indonesia_config")
    if config:
        return config
        
    try:
        config_path = frappe.get_app_path("payroll_indonesia", "config", "defaults.json")
        if os.path.exists(config_path):
            with open(config_path) as f:
                config = json.load(f)
                # Cache for 24 hours (86400 seconds)
                frappe.cache().set_value("payroll_indonesia_config", config, expires_in_sec=86400)
                return config
    except Exception as e:
        frappe.log_error(f"Error loading configuration: {str(e)}", "Configuration Error")
    
    return {}

# Validation functions for hooks.py
def validate_settings(doc, method=None):
    """Wrapper for BPJSSettings.validate method with protection against recursion"""
    # Skip if already being validated
    if getattr(doc, "_validated", False):
        return
        
    # Mark as being validated to prevent recursion
    doc._validated = True
    
    try:
        # Call the instance methods
        doc.validate_data_types()
        doc.validate_percentages()
        doc.validate_max_salary()
        doc.validate_account_types()
    finally:
        # Always clean up flag
        doc._validated = False
    
def setup_accounts(doc, method=None):
    """Wrapper for BPJSSettings.setup_accounts method with protection against recursion"""
    # Skip if already being processed
    if getattr(doc, "_setup_running", False):
        return
        
    # Mark as being processed to prevent recursion
    doc._setup_running = True
    
    try:
        # Call the instance method
        doc.setup_accounts()
    finally:
        # Always clean up flag
        doc._setup_running = False

# Account functions
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
    
    # Get parent account candidates from config
    config = get_default_config()
    
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
        # Get candidates from config if available
        if "Payable" in parent_name or account_type in ["Payable", "Tax"]:
            config_candidates = config.get("gl_accounts", {}).get("parent_account_candidates", {}).get("liability", [])
            parent_candidates = candidates or config_candidates or ["Duties and Taxes", "Current Liabilities", "Accounts Payable"]
            debug_log(f"Looking for liability parent among: {', '.join(parent_candidates)}", "Account Lookup")
        else:
            config_candidates = config.get("gl_accounts", {}).get("parent_account_candidates", {}).get("expense", [])
            parent_candidates = candidates or config_candidates or ["Direct Expenses", "Indirect Expenses", "Expenses"]
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

def create_account(company, account_name, account_type, parent):
    """
    Create GL Account if not exists with standardized naming
    
    Args:
        company (str): Company name
        account_name (str): Account name without company abbreviation
        account_type (str): Account type (Payable, Expense, etc.)
        parent (str): Parent account name
        
    Returns:
        str: Full account name if created or already exists, None otherwise
    """
    try:
        # Validate inputs
        if not company or not account_name or not account_type or not parent:
            frappe.throw(_("Missing required parameters for account creation"))
            
        abbr = frappe.get_cached_value('Company', company, 'abbr')
        if not abbr:
            frappe.throw(_("Company {0} does not have an abbreviation").format(company))
            
        # Ensure account name doesn't already include the company abbreviation
        pure_account_name = account_name.replace(f" - {abbr}", "")
        full_account_name = f"{pure_account_name} - {abbr}"
        
        # Check if account already exists
        if frappe.db.exists("Account", full_account_name):
            debug_log(f"Account {full_account_name} already exists", "Account Creation")
            
            # Verify account properties are correct
            account_doc = frappe.db.get_value(
                "Account", 
                full_account_name, 
                ["account_type", "parent_account", "company", "is_group"], 
                as_dict=1
            )
            
            if (account_doc.account_type != account_type or 
                account_doc.parent_account != parent or 
                account_doc.company != company):
                debug_log(
                    f"Account {full_account_name} exists but has different properties. "
                    f"Expected: type={account_type}, parent={parent}, company={company}. "
                    f"Found: type={account_doc.account_type}, parent={account_doc.parent_account}, "
                    f"company={account_doc.company}", 
                    "Account Warning"
                )
                # We don't change existing account properties, just return the name
                
            return full_account_name
            
        # Verify parent account exists
        if not frappe.db.exists("Account", parent):
            frappe.throw(_("Parent account {0} does not exist").format(parent))
            
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
            "root_type": "Liability" if account_type in ["Payable", "Liability"] else "Expense"
        })
        
        # Bypass permissions and mandatory checks during setup
        doc.flags.ignore_permissions = True
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        
        # Commit database changes immediately
        frappe.db.commit()
        
        # Verify account was created
        if frappe.db.exists("Account", full_account_name):
            frappe.msgprint(_(f"Created account: {full_account_name}"))
            debug_log(f"Successfully created account: {full_account_name}", "Account Creation")
            return full_account_name
        else:
            frappe.throw(_("Failed to create account {0} despite no errors").format(full_account_name))
        
    except Exception as e:
        frappe.log_error(
            f"Error creating account {account_name} for {company}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}", 
            "BPJS Account Creation Error"
        )
        debug_log(f"Error creating account {account_name}: {str(e)}", "Account Creation Error", trace=True)
        return None

def create_parent_liability_account(company):
    """
    Create or get parent liability account for BPJS accounts
    
    Args:
        company (str): Company name
        
    Returns:
        str: Parent account name if created or already exists, None otherwise
    """
    try:
        # Validate company
        if not company:
            frappe.throw(_("Company is required to create parent liability account"))
            
        abbr = frappe.get_cached_value('Company', company, 'abbr')
        if not abbr:
            frappe.throw(_("Company {0} does not have an abbreviation").format(company))
        
        parent_name = f"BPJS Payable - {abbr}"
        
        # Check if account already exists
        if frappe.db.exists("Account", parent_name):
            # Verify the account is a group account
            is_group = frappe.db.get_value("Account", parent_name, "is_group")
            if not is_group:
                # Convert to group account if needed
                try:
                    account_doc = frappe.get_doc("Account", parent_name)
                    account_doc.is_group = 1
                    account_doc.flags.ignore_permissions = True
                    account_doc.save()
                    frappe.db.commit()
                    debug_log(f"Updated {parent_name} to be a group account", "Account Fix")
                except Exception as e:
                    frappe.log_error(
                        f"Could not convert {parent_name} to group account: {str(e)}", 
                        "Account Creation Error"
                    )
                    # Continue and return the account name anyway
            
            debug_log(f"Parent liability account {parent_name} already exists", "Account Creation")
            return parent_name
            
        # Find a suitable parent account
        # Get parent candidates from config
        config = get_default_config()
        parent_candidates_from_config = config.get("gl_accounts", {}).get("parent_account_candidates", {}).get("liability", [])
        
        if parent_candidates_from_config:
            parent_candidates = [f"{candidate} - {abbr}" for candidate in parent_candidates_from_config]
        else:
            parent_candidates = [
                f"Duties and Taxes - {abbr}",
                f"Accounts Payable - {abbr}",
                f"Current Liabilities - {abbr}"
            ]
        
        parent_account = None
        for candidate in parent_candidates:
            if frappe.db.exists("Account", candidate):
                parent_account = candidate
                debug_log(f"Found parent account {parent_account} for BPJS Payable", "Account Creation")
                break
        
        if not parent_account:
            # Try to find any liability group account as fallback
            liability_accounts = frappe.get_all(
                "Account",
                filters={"company": company, "is_group": 1, "root_type": "Liability"},
                order_by="lft",
                limit=1
            )
            
            if liability_accounts:
                parent_account = liability_accounts[0].name
                debug_log(f"Using fallback liability parent account: {parent_account}", "Account Creation")
            else:
                frappe.throw(_("No suitable liability parent account found for creating BPJS accounts in company {0}").format(company))
                return None
            
        # Create parent account with explicit error handling
        try:
            debug_log(f"Creating parent liability account {parent_name} under {parent_account}", "Account Creation")
            
            doc = frappe.get_doc({
                "doctype": "Account",
                "account_name": "BPJS Payable",
                "parent_account": parent_account,
                "company": company,
                "account_type": "Payable",
                "account_currency": frappe.get_cached_value('Company', company, 'default_currency'),
                "is_group": 1,
                "root_type": "Liability"
            })
            
            # Bypass permissions and mandatory checks during setup
            doc.flags.ignore_permissions = True
            doc.flags.ignore_mandatory = True
            doc.insert(ignore_permissions=True)
            
            # Commit database changes immediately
            frappe.db.commit()
            
            # Verify account was created
            if frappe.db.exists("Account", parent_name):
                debug_log(f"Successfully created parent liability account: {parent_name}", "Account Creation")
                return parent_name
            else:
                frappe.throw(_("Failed to create parent liability account {0} despite no errors").format(parent_name))
                
        except Exception as e:
            frappe.log_error(
                f"Error creating parent liability account {parent_name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}", 
                "Account Creation Error"
            )
            debug_log(f"Error creating parent liability account for {company}: {str(e)}", "Account Creation Error", trace=True)
            return None
            
    except Exception as e:
        frappe.log_error(
            f"Critical error in create_parent_liability_account for {company}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}", 
            "BPJS Account Creation Error"
        )
        return None

def create_parent_expense_account(company):
    """
    Create or get parent expense account for BPJS accounts
    
    Args:
        company (str): Company name
        
    Returns:
        str: Parent account name if created or already exists, None otherwise
    """
    try:
        # Validate company
        if not company:
            frappe.throw(_("Company is required to create parent expense account"))
            
        abbr = frappe.get_cached_value('Company', company, 'abbr')
        if not abbr:
            frappe.throw(_("Company {0} does not have an abbreviation").format(company))
        
        parent_name = f"BPJS Expenses - {abbr}"
        
        # Check if account already exists
        if frappe.db.exists("Account", parent_name):
            # Verify the account is a group account
            is_group = frappe.db.get_value("Account", parent_name, "is_group")
            if not is_group:
                # Convert to group account if needed
                try:
                    account_doc = frappe.get_doc("Account", parent_name)
                    account_doc.is_group = 1
                    account_doc.flags.ignore_permissions = True
                    account_doc.save()
                    frappe.db.commit()
                    debug_log(f"Updated {parent_name} to be a group account", "Account Fix")
                except Exception as e:
                    frappe.log_error(
                        f"Could not convert {parent_name} to group account: {str(e)}", 
                        "Account Creation Error"
                    )
                    # Continue and return the account name anyway
            
            debug_log(f"Parent expense account {parent_name} already exists", "Account Creation")
            return parent_name
            
        # Find a suitable parent account with explicit error handling
        # Get parent candidates from config
        config = get_default_config()
        parent_candidates_from_config = config.get("gl_accounts", {}).get("parent_account_candidates", {}).get("expense", [])
        
        if parent_candidates_from_config:
            parent_candidates = [f"{candidate} - {abbr}" for candidate in parent_candidates_from_config]
        else:
            parent_candidates = [
                f"Direct Expenses - {abbr}",
                f"Indirect Expenses - {abbr}",
                f"Expenses - {abbr}"
            ]
        
        parent_account = None
        for candidate in parent_candidates:
            if frappe.db.exists("Account", candidate):
                parent_account = candidate
                debug_log(f"Found parent account {parent_account} for BPJS Expenses", "Account Creation")
                break
        
        if not parent_account:
            # Try to find any expense group account as fallback
            expense_accounts = frappe.get_all(
                "Account",
                filters={"company": company, "is_group": 1, "root_type": "Expense"},
                order_by="lft",
                limit=1
            )
            
            if expense_accounts:
                parent_account = expense_accounts[0].name
                debug_log(f"Using fallback expense parent account: {parent_account}", "Account Creation")
            else:
                frappe.throw(_("No suitable expense parent account found for creating BPJS accounts in company {0}").format(company))
                return None
            
        # Create parent account with explicit error handling
        try:
            debug_log(f"Creating parent expense account {parent_name} under {parent_account}", "Account Creation")
            
            doc = frappe.get_doc({
                "doctype": "Account",
                "account_name": "BPJS Expenses",
                "parent_account": parent_account,
                "company": company,
                "account_type": "Expense",
                "account_currency": frappe.get_cached_value('Company', company, 'default_currency'),
                "is_group": 1,
                "root_type": "Expense"
            })
            
            # Bypass permissions and mandatory checks during setup
            doc.flags.ignore_permissions = True
            doc.flags.ignore_mandatory = True
            doc.insert(ignore_permissions=True)
            
            # Commit database changes immediately
            frappe.db.commit()
            
            # Verify account was created
            if frappe.db.exists("Account", parent_name):
                debug_log(f"Successfully created parent expense account: {parent_name}", "Account Creation")
                return parent_name
            else:
                frappe.throw(_("Failed to create parent expense account {0} despite no errors").format(parent_name))
                
        except Exception as e:
            frappe.log_error(
                f"Error creating parent expense account {parent_name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}", 
                "Account Creation Error"
            )
            debug_log(f"Error creating parent expense account for {company}: {str(e)}", "Account Creation Error", trace=True)
            return None
            
    except Exception as e:
        frappe.log_error(
            f"Critical error in create_parent_expense_account for {company}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}", 
            "BPJS Account Creation Error"
        )
        return None

# BPJS Mapping functions
def retry_bpjs_mapping(companies):
    """
    Background job to retry failed BPJS mapping creation
    Called via frappe.enqueue() from ensure_bpjs_mapping_for_all_companies
    
    Args:
        companies (list): List of company names to retry mapping for
    """
    if not companies:
        return
        
    try:
        from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import create_default_mapping
        
        # Get account mapping config
        config = get_default_config()
        account_mapping = config.get("gl_accounts", {}).get("bpjs_account_mapping", {})
        
        for company in companies:
            try:
                if not frappe.db.exists("BPJS Account Mapping", {"company": company}):
                    debug_log(f"Retrying BPJS Account Mapping creation for {company}", "BPJS Mapping Retry")
                    mapping_name = create_default_mapping(company, account_mapping)
                    
                    if mapping_name:
                        frappe.logger().info(f"Successfully created BPJS Account Mapping for {company} on retry")
                        debug_log(f"Successfully created BPJS Account Mapping for {company} on retry", "BPJS Mapping Retry")
                    else:
                        frappe.logger().warning(f"Failed again to create BPJS Account Mapping for {company}")
                        debug_log(f"Failed again to create BPJS Account Mapping for {company}", "BPJS Mapping Retry Error")
            except Exception as e:
                frappe.log_error(
                    f"Error creating BPJS Account Mapping for {company} on retry: {str(e)}\n\n"
                    f"Traceback: {frappe.get_traceback()}", 
                    "BPJS Mapping Retry Error"
                )
                debug_log(f"Error in retry for company {company}: {str(e)}", "BPJS Mapping Retry Error", trace=True)
                
    except Exception as e:
        frappe.log_error(
            f"Error in retry_bpjs_mapping: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}", 
            "BPJS Mapping Retry Error"
        )

# Logging functions
def debug_log(message, title=None, max_length=500, trace=False):
    """
    Debug logging helper with consistent format
    
    Args:
        message (str): Message to log
        title (str, optional): Optional title/context for the log
        max_length (int, optional): Maximum message length (default: 500)
        trace (bool, optional): Whether to include traceback (default: False)
    """
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    
    if os.environ.get("DEBUG_BPJS") or trace:
        # Truncate if message is too long to avoid memory issues
        message = str(message)[:max_length]
        
        if title:
            log_message = f"[{timestamp}] [{title}] {message}"
        else:
            log_message = f"[{timestamp}] {message}"
            
        frappe.logger().debug(f"[BPJS DEBUG] {log_message}")
        
        if trace:
            frappe.logger().debug(f"[BPJS DEBUG] [TRACE] {frappe.get_traceback()[:max_length]}")