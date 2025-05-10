# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-06 17:45:10 by dannyaudian

import frappe
import json
import os
from frappe import _
from frappe.utils import flt, cint, getdate, now_datetime

# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-09 12:55:00 by dannyaudian

import frappe
import json
import os
from frappe import _
from frappe.utils import flt, cint, getdate, now_datetime

__all__ = [
    'get_default_config',
    'debug_log',
    'find_parent_account',
    'create_account',
    'create_parent_liability_account',
    'create_parent_expense_account',
    'retry_bpjs_mapping',
    'get_bpjs_settings',
    'calculate_bpjs_contributions',
    'get_ptkp_settings',
    'get_spt_month',
    'get_pph21_settings',
    'get_pph21_brackets',
    'map_ptkp_to_ter',  # Tambahan fungsi baru
    'get_ter_rate',
    'should_use_ter',
    'create_tax_summary_doc',
    'get_ytd_tax_info'
]

# Config handling functions
def get_default_config(section=None):
    """
    Load configuration from defaults.json with caching
    
    Args:
        section (str, optional): Specific section to retrieve from config
        
    Returns:
        dict: Configuration data from defaults.json or empty dict if not found/error
    """
    # Try to get from cache first
    cache_key = "payroll_indonesia_config"
    if section:
        cache_key += f"_{section}"
    
    config = frappe.cache().get_value(cache_key)
    if config:
        return config
        
    try:
        config_path = frappe.get_app_path("payroll_indonesia", "config", "defaults.json")
        if not os.path.exists(config_path):
            frappe.log_error(
                f"Config file not found at {config_path}",
                "Config Error"
            )
            return {} if section is None else {}
        
        with open(config_path) as f:
            all_config = json.load(f)
            
            # Cache full config for 24 hours (86400 seconds)
            frappe.cache().set_value("payroll_indonesia_config", all_config, expires_in_sec=86400)
            
            # Return and cache requested section if specified
            if section:
                section_data = all_config.get(section, {})
                frappe.cache().set_value(f"payroll_indonesia_config_{section}", section_data, expires_in_sec=86400)
                return section_data
                
            return all_config
    except Exception as e:
        frappe.log_error(f"Error loading configuration: {str(e)}", "Configuration Error")
        return {} if section is None else {}

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

def create_account(company, account_name, account_type, parent, root_type=None):
    """
    Create GL Account if not exists with standardized naming
    
    Args:
        company (str): Company name
        account_name (str): Account name without company abbreviation
        account_type (str): Account type (Payable, Expense, etc.)
        parent (str): Parent account name
        root_type (str, optional): Root type (Asset, Liability, etc.). If None, determined from account_type.
        
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
            
        # Determine root_type based on account_type if not provided
        if not root_type:
            root_type = "Liability"  # Default
            if account_type in ["Direct Expense", "Indirect Expense", "Expense Account", "Expense"]:
                root_type = "Expense"
            elif account_type == "Asset":
                root_type = "Asset"
            elif account_type in ["Direct Income", "Indirect Income", "Income Account"]:
                root_type = "Income"
            
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
        
        # Commit database changes immediately
        frappe.db.commit()
        
        # Verify account was created
        if frappe.db.exists("Account", full_account_name):
            debug_log(f"Successfully created account: {full_account_name}", "Account Creation")
            return full_account_name
        else:
            frappe.throw(_("Failed to create account {0} despite no errors").format(full_account_name))
        
    except Exception as e:
        frappe.log_error(
            f"Error creating account {account_name} for {company}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}", 
            "Account Creation Error"
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
        
        # Get config for parent account properties
        config = get_default_config()
        parent_account_info = config.get("gl_accounts", {}).get("parent_accounts", {}).get("bpjs_payable", {})
        account_name = parent_account_info.get("account_name", "BPJS Payable")
        
        parent_name = f"{account_name} - {abbr}"
        
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
        parent_candidates_from_config = config.get("gl_accounts", {}).get("parent_account_candidates", {}).get("liability", [])
        
        if parent_candidates_from_config:
            parent_candidates = parent_candidates_from_config
        else:
            parent_candidates = ["Duties and Taxes", "Accounts Payable", "Current Liabilities"]
        
        parent_account = find_parent_account(
            company=company,
            parent_name=parent_account_info.get("parent_account", "Duties and Taxes"),
            company_abbr=abbr,
            account_type="Payable",
            candidates=parent_candidates
        )
        
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
                "account_name": account_name,
                "parent_account": parent_account,
                "company": company,
                "account_type": parent_account_info.get("account_type", "Payable"),
                "account_currency": frappe.get_cached_value('Company', company, 'default_currency'),
                "is_group": 1,
                "root_type": parent_account_info.get("root_type", "Liability")
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
            "Account Creation Error"
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
        
        # Get config for parent account properties
        config = get_default_config()
        parent_account_info = config.get("gl_accounts", {}).get("parent_accounts", {}).get("bpjs_expenses", {})
        account_name = parent_account_info.get("account_name", "BPJS Expenses")
        
        parent_name = f"{account_name} - {abbr}"
        
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
            
        # Find a suitable parent account
        # Get parent candidates from config
        parent_candidates_from_config = config.get("gl_accounts", {}).get("parent_account_candidates", {}).get("expense", [])
        
        if parent_candidates_from_config:
            parent_candidates = parent_candidates_from_config
        else:
            parent_candidates = ["Direct Expenses", "Indirect Expenses", "Expenses"]
        
        parent_account = find_parent_account(
            company=company,
            parent_name=parent_account_info.get("parent_account", "Direct Expenses"),
            company_abbr=abbr,
            account_type="Expense",
            candidates=parent_candidates
        )
        
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
                "account_name": account_name,
                "parent_account": parent_account,
                "company": company,
                "account_type": parent_account_info.get("account_type", "Expense"),
                "account_currency": frappe.get_cached_value('Company', company, 'default_currency'),
                "is_group": 1,
                "root_type": parent_account_info.get("root_type", "Expense")
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
            "Account Creation Error"
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
        # Import conditionally to avoid circular imports
        module_path = "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping"
        try:
            module = frappe.get_module(module_path)
            create_default_mapping = getattr(module, "create_default_mapping", None)
        except (ImportError, AttributeError) as e:
            frappe.log_error(f"Failed to import create_default_mapping: {str(e)}", "BPJS Mapping Error")
            return

        if not create_default_mapping:
            frappe.log_error("create_default_mapping function not found", "BPJS Mapping Error")
            return
        
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

# BPJS Settings and Calculation Functions
def get_bpjs_settings():
    """
    Get BPJS settings from DocType or .env file or site_config.json
    with improved error handling and validation
    
    Returns:
        dict: Dictionary containing BPJS settings
    """
    try:
        # First try to get from DocType if it exists
        if frappe.db.exists("DocType", "BPJS Settings"):
            try:
                doc_list = frappe.db.get_all("BPJS Settings")
                if doc_list:
                    doc = frappe.get_single("BPJS Settings")
                    
                    # Validate required fields exist
                    required_fields = [
                        'kesehatan_employee_percent', 'kesehatan_employer_percent', 'kesehatan_max_salary',
                        'jht_employee_percent', 'jht_employer_percent', 
                        'jp_employee_percent', 'jp_employer_percent', 'jp_max_salary',
                        'jkk_percent', 'jkm_percent'
                    ]
                    
                    missing_fields = []
                    for field in required_fields:
                        if not hasattr(doc, field):
                            missing_fields.append(field)
                            
                    if missing_fields:
                        frappe.log_error(
                            f"BPJS Settings missing required fields: {', '.join(missing_fields)}",
                            "BPJS Settings Error"
                        )
                    else:
                        # All fields exist, return structured settings
                        return {
                            "kesehatan": {
                                "employee_percent": flt(doc.kesehatan_employee_percent),
                                "employer_percent": flt(doc.kesehatan_employer_percent),
                                "max_salary": flt(doc.kesehatan_max_salary)
                            },
                            "jht": {
                                "employee_percent": flt(doc.jht_employee_percent),
                                "employer_percent": flt(doc.jht_employer_percent)
                            },
                            "jp": {
                                "employee_percent": flt(doc.jp_employee_percent),
                                "employer_percent": flt(doc.jp_employer_percent),
                                "max_salary": flt(doc.jp_max_salary)
                            },
                            "jkk": {
                                "percent": flt(doc.jkk_percent)
                            },
                            "jkm": {
                                "percent": flt(doc.jkm_percent)
                            }
                        }
            except Exception as e:
                frappe.log_error(f"Error retrieving BPJS Settings from DocType: {str(e)}", "BPJS Settings Error")
                # Fall back to config methods
                pass
        
        # Get settings from frappe.conf or initialize empty dict
        settings = frappe.conf.get('bpjs_settings', {})
        
        # Check for environment variables
        env_settings = {
            'kesehatan_employee': os.getenv('BPJS_KESEHATAN_PERCENT_KARYAWAN'),
            'kesehatan_employer': os.getenv('BPJS_KESEHATAN_PERCENT_PERUSAHAAN'),
            'jht_employee': os.getenv('BPJS_JHT_PERCENT_KARYAWAN'),
            'jht_employer': os.getenv('BPJS_JHT_PERCENT_PERUSAHAAN'),
            'jp_employee': os.getenv('BPJS_JP_PERCENT_KARYAWAN'),
            'jp_employer': os.getenv('BPJS_JP_PERCENT_PERUSAHAAN'),
            'jkk_employer': os.getenv('BPJS_JKK_PERCENT'),
            'jkm_employer': os.getenv('BPJS_JKM_PERCENT'),
            'max_salary_kesehatan': os.getenv('BPJS_KES_MAX_SALARY'),
            'max_salary_jp': os.getenv('BPJS_JP_MAX_SALARY'),
        }
        
        # Update settings from environment variables if available
        for key, value in env_settings.items():
            if value:
                try:
                    settings[key] = float(value)
                except (ValueError, TypeError):
                    frappe.log_error(f"Invalid value for BPJS setting {key}: {value}", "BPJS Settings Error")
        
        # Get default values from config
        config = get_default_config("bpjs")
        
        # Apply defaults from config or hardcoded fallbacks
        defaults = {
            'kesehatan_employee': config.get('kesehatan_employee_percent', 1.0),
            'kesehatan_employer': config.get('kesehatan_employer_percent', 4.0),
            'jht_employee': config.get('jht_employee_percent', 2.0),
            'jht_employer': config.get('jht_employer_percent', 3.7),
            'jp_employee': config.get('jp_employee_percent', 1.0),
            'jp_employer': config.get('jp_employer_percent', 2.0),
            'jkk_employer': config.get('jkk_percent', 0.24),
            'jkm_employer': config.get('jkm_percent', 0.3),
            'max_salary_kesehatan': config.get('kesehatan_max_salary', 12000000),
            'max_salary_jp': config.get('jp_max_salary', 9077600),
        }
        
        # Apply defaults for missing values
        for key, value in defaults.items():
            if key not in settings:
                settings[key] = value
        
        # Convert to structured format
        return {
            "kesehatan": {
                "employee_percent": settings.get('kesehatan_employee'),
                "employer_percent": settings.get('kesehatan_employer'),
                "max_salary": settings.get('max_salary_kesehatan')
            },
            "jht": {
                "employee_percent": settings.get('jht_employee'),
                "employer_percent": settings.get('jht_employer')
            },
            "jp": {
                "employee_percent": settings.get('jp_employee'),
                "employer_percent": settings.get('jp_employer'),
                "max_salary": settings.get('max_salary_jp')
            },
            "jkk": {
                "percent": settings.get('jkk_employer')
            },
            "jkm": {
                "percent": settings.get('jkm_employer')
            }
        }
    except Exception as e:
        frappe.log_error(f"Error retrieving BPJS settings: {str(e)}", "BPJS Settings Error")
        
        # Get default values from config as fallback
        config = get_default_config("bpjs")
        
        # Return defaults from config or ultimate hardcoded fallback
        return {
            "kesehatan": {
                "employee_percent": config.get('kesehatan_employee_percent', 1.0),
                "employer_percent": config.get('kesehatan_employer_percent', 4.0),
                "max_salary": config.get('kesehatan_max_salary', 12000000)
            },
            "jht": {
                "employee_percent": config.get('jht_employee_percent', 2.0),
                "employer_percent": config.get('jht_employer_percent', 3.7)
            },
            "jp": {
                "employee_percent": config.get('jp_employee_percent', 1.0),
                "employer_percent": config.get('jp_employer_percent', 2.0),
                "max_salary": config.get('jp_max_salary', 9077600)
            },
            "jkk": {
                "percent": config.get('jkk_percent', 0.24)
            },
            "jkm": {
                "percent": config.get('jkm_percent', 0.3)
            }
        }

def calculate_bpjs_contributions(salary, bpjs_settings=None):
    """
    Calculate BPJS contributions based on salary and settings
    with improved validation and error handling
    
    Args:
        salary (float): Base salary amount
        bpjs_settings (object, optional): BPJS Settings or dict. Will fetch if not provided.
        
    Returns:
        dict: Dictionary containing BPJS contribution details
    """
    try:
        # Validate input
        if salary is None:
            frappe.throw(_("Salary amount is required for BPJS calculation"))
            
        salary = flt(salary)
        if salary < 0:
            frappe.msgprint(_("Negative salary amount provided for BPJS calculation, using absolute value"))
            salary = abs(salary)
        
        # Get BPJS settings if not provided
        if not bpjs_settings:
            bpjs_settings = get_bpjs_settings()
        
        # Get default config values
        config = get_default_config("bpjs")
        
        # Initialize values from config or fallback to defaults
        kesehatan_employee_percent = config.get('kesehatan_employee_percent', 1.0)
        kesehatan_employer_percent = config.get('kesehatan_employer_percent', 4.0)
        kesehatan_max_salary = config.get('kesehatan_max_salary', 12000000)
        
        jht_employee_percent = config.get('jht_employee_percent', 2.0)
        jht_employer_percent = config.get('jht_employer_percent', 3.7)
        
        jp_employee_percent = config.get('jp_employee_percent', 1.0)
        jp_employer_percent = config.get('jp_employer_percent', 2.0)
        jp_max_salary = config.get('jp_max_salary', 9077600)
        
        jkk_percent = config.get('jkk_percent', 0.24)
        jkm_percent = config.get('jkm_percent', 0.3)
        
        # Check if bpjs_settings is a dict or an object and get values
        if isinstance(bpjs_settings, dict):
            # Use dict values with validation
            kesehatan_employee_percent = flt(bpjs_settings.get("kesehatan", {}).get("employee_percent", kesehatan_employee_percent))
            kesehatan_employer_percent = flt(bpjs_settings.get("kesehatan", {}).get("employer_percent", kesehatan_employer_percent))
            kesehatan_max_salary = flt(bpjs_settings.get("kesehatan", {}).get("max_salary", kesehatan_max_salary))
            
            jht_employee_percent = flt(bpjs_settings.get("jht", {}).get("employee_percent", jht_employee_percent))
            jht_employer_percent = flt(bpjs_settings.get("jht", {}).get("employer_percent", jht_employer_percent))
            
            jp_employee_percent = flt(bpjs_settings.get("jp", {}).get("employee_percent", jp_employee_percent))
            jp_employer_percent = flt(bpjs_settings.get("jp", {}).get("employer_percent", jp_employer_percent))
            jp_max_salary = flt(bpjs_settings.get("jp", {}).get("max_salary", jp_max_salary))
            
            jkk_percent = flt(bpjs_settings.get("jkk", {}).get("percent", jkk_percent))
            jkm_percent = flt(bpjs_settings.get("jkm", {}).get("percent", jkm_percent))
        else:
            # Use object attributes with validation
            if hasattr(bpjs_settings, 'kesehatan_employee_percent'):
                kesehatan_employee_percent = flt(bpjs_settings.kesehatan_employee_percent)
            
            if hasattr(bpjs_settings, 'kesehatan_employer_percent'):
                kesehatan_employer_percent = flt(bpjs_settings.kesehatan_employer_percent)
                
            if hasattr(bpjs_settings, 'kesehatan_max_salary'):
                kesehatan_max_salary = flt(bpjs_settings.kesehatan_max_salary)
                
            if hasattr(bpjs_settings, 'jht_employee_percent'):
                jht_employee_percent = flt(bpjs_settings.jht_employee_percent)
                
            if hasattr(bpjs_settings, 'jht_employer_percent'):
                jht_employer_percent = flt(bpjs_settings.jht_employer_percent)
                
            if hasattr(bpjs_settings, 'jp_employee_percent'):
                jp_employee_percent = flt(bpjs_settings.jp_employee_percent)
                
            if hasattr(bpjs_settings, 'jp_employer_percent'):
                jp_employer_percent = flt(bpjs_settings.jp_employer_percent)
                
            if hasattr(bpjs_settings, 'jp_max_salary'):
                jp_max_salary = flt(bpjs_settings.jp_max_salary)
                
            if hasattr(bpjs_settings, 'jkk_percent'):
                jkk_percent = flt(bpjs_settings.jkk_percent)
                
            if hasattr(bpjs_settings, 'jkm_percent'):
                jkm_percent = flt(bpjs_settings.jkm_percent)
        
        # Validate percentages
        if kesehatan_employee_percent < 0 or kesehatan_employee_percent > 100:
            frappe.msgprint(_("Invalid BPJS Kesehatan employee percentage. Using default 1%"))
            kesehatan_employee_percent = 1.0
            
        if kesehatan_max_salary <= 0:
            frappe.msgprint(_("Invalid BPJS Kesehatan maximum salary. Using default 12,000,000"))
            kesehatan_max_salary = 12000000
            
        if jp_max_salary <= 0:
            frappe.msgprint(_("Invalid BPJS JP maximum salary. Using default 9,077,600"))
            jp_max_salary = 9077600
        
        # Cap salaries at maximum thresholds
        kesehatan_salary = min(flt(salary), kesehatan_max_salary)
        jp_salary = min(flt(salary), jp_max_salary)
        
        # Calculate BPJS Kesehatan
        kesehatan_karyawan = kesehatan_salary * (kesehatan_employee_percent / 100)
        kesehatan_perusahaan = kesehatan_salary * (kesehatan_employer_percent / 100)
        
        # Calculate BPJS Ketenagakerjaan - JHT
        jht_karyawan = flt(salary) * (jht_employee_percent / 100)
        jht_perusahaan = flt(salary) * (jht_employer_percent / 100)
        
        # Calculate BPJS Ketenagakerjaan - JP
        jp_karyawan = jp_salary * (jp_employee_percent / 100)
        jp_perusahaan = jp_salary * (jp_employer_percent / 100)
        
        # Calculate BPJS Ketenagakerjaan - JKK and JKM
        jkk = flt(salary) * (jkk_percent / 100)
        jkm = flt(salary) * (jkm_percent / 100)
        
        # Return structured result
        return {
            "kesehatan": {
                "karyawan": kesehatan_karyawan,
                "perusahaan": kesehatan_perusahaan,
                "total": kesehatan_karyawan + kesehatan_perusahaan
            },
            "ketenagakerjaan": {
                "jht": {
                    "karyawan": jht_karyawan,
                    "perusahaan": jht_perusahaan,
                    "total": jht_karyawan + jht_perusahaan
                },
                "jp": {
                    "karyawan": jp_karyawan,
                    "perusahaan": jp_perusahaan,
                    "total": jp_karyawan + jp_perusahaan
                },
                "jkk": jkk,
                "jkm": jkm
            }
        }
    except Exception as e:
        frappe.log_error(f"Error calculating BPJS contributions: {str(e)}", "BPJS Calculation Error")
        debug_log(f"Error calculating BPJS contributions: {str(e)}", "Calculation Error", trace=True)
        
        # Return empty structure to avoid breaking code that relies on the structure
        return {
            "kesehatan": {"karyawan": 0, "perusahaan": 0, "total": 0},
            "ketenagakerjaan": {
                "jht": {"karyawan": 0, "perusahaan": 0, "total": 0},
                "jp": {"karyawan": 0, "perusahaan": 0, "total": 0},
                "jkk": 0, "jkm": 0
            }
        }

# Tax Calculation Functions
def get_ptkp_settings():
    """
    Get PTKP settings from PPh 21 Settings DocType or .env file or defaults
    with improved error handling
    
    Returns:
        dict: Dictionary containing PTKP settings
    """
    try:
        # First try to get from DocType if it exists
        if frappe.db.exists("DocType", "PPh 21 Settings"):
            try:
                doc_list = frappe.db.get_all("PPh 21 Settings")
                if doc_list:
                    doc = frappe.get_single("PPh 21 Settings")
                    result = {}
                    
                    # Check if ptkp_table exists and has rows
                    if hasattr(doc, 'ptkp_table') and doc.ptkp_table:
                        # Get PTKP values from child table
                        for row in doc.ptkp_table:
                            if hasattr(row, 'status_pajak') and hasattr(row, 'ptkp_amount'):
                                result[row.status_pajak] = float(row.ptkp_amount)
                        
                        if result:
                            return result
            except Exception as e:
                frappe.log_error(f"Error getting PTKP settings from DocType: {str(e)}", "PTKP Settings Error")
                # Fall back to config methods
                pass
        
        # Get from config
        config = get_default_config("ptkp")
        if config:
            return config
        
        # Initialize settings dict if no config
        settings = {}
        
        # Check for environment variables
        env_settings = {
            'pribadi': os.getenv('PTKP_PRIBADI'),
            'kawin': os.getenv('PTKP_KAWIN'),
            'anak': os.getenv('PTKP_ANAK'),
        }
        
        # Update settings from environment variables if available
        for key, value in env_settings.items():
            if value:
                try:
                    settings[key] = float(value)
                except (ValueError, TypeError):
                    frappe.log_error(f"Invalid value for PTKP setting {key}: {value}", "PTKP Settings Error")
        
        # Default values if not configured
        defaults = {
            'pribadi': 54000000,  # Annual PTKP for individual
            'kawin': 4500000,     # Additional for married status
            'anak': 4500000,      # Additional per dependent
        }
        
        # Apply defaults for missing values
        for key, value in defaults.items():
            if key not in settings:
                settings[key] = value
                
        # Calculate standard PTKP values if not from DocType or config
        if 'TK0' not in settings:
            settings['TK0'] = settings['pribadi']
            settings['K0'] = settings['pribadi'] + settings['kawin']
            settings['K1'] = settings['pribadi'] + settings['kawin'] + settings['anak']
            settings['K2'] = settings['pribadi'] + settings['kawin'] + (2 * settings['anak'])
            settings['K3'] = settings['pribadi'] + settings['kawin'] + (3 * settings['anak'])
            # Add all missing status variations for TER
            settings['TK1'] = settings['pribadi'] + settings['anak']
            settings['TK2'] = settings['pribadi'] + (2 * settings['anak'])
            settings['TK3'] = settings['pribadi'] + (3 * settings['anak'])
            # Add HB (Penghasilan Istri-Suami Digabung) statuses
            settings['HB0'] = 2 * settings['pribadi'] + settings['kawin']
            settings['HB1'] = 2 * settings['pribadi'] + settings['kawin'] + settings['anak']
            settings['HB2'] = 2 * settings['pribadi'] + settings['kawin'] + (2 * settings['anak'])
            settings['HB3'] = 2 * settings['pribadi'] + settings['kawin'] + (3 * settings['anak'])
                
        return settings
    except Exception as e:
        frappe.log_error(f"Error retrieving PTKP settings: {str(e)}", "PTKP Settings Error")
        debug_log(f"Error retrieving PTKP settings: {str(e)}", "PTKP Settings Error", trace=True)
        
        # Return default PTKP values from config or fallback
        config_ptkp = get_default_config("ptkp")
        if config_ptkp:
            return config_ptkp
        
        # Ultimate fallback to hardcoded values
        return {
            'TK0': 54000000, 'TK1': 58500000, 'TK2': 63000000, 'TK3': 67500000,
            'K0': 58500000, 'K1': 63000000, 'K2': 67500000, 'K3': 72000000,
            'HB0': 112500000, 'HB1': 117000000, 'HB2': 121500000, 'HB3': 126000000,
        }

def get_spt_month():
    """
    Get the month for annual SPT calculation from .env file or default
    with improved validation
    
    Returns:
        int: Month number (1-12)
    """
    try:
        # Get from environment variable
        spt_month_str = os.getenv('SPT_BULAN')
        
        if spt_month_str:
            try:
                spt_month = int(spt_month_str)
                # Validate month is in correct range
                if spt_month < 1 or spt_month > 12:
                    frappe.log_error(
                        f"Invalid SPT_BULAN value: {spt_month}. Must be between 1-12. Using default (12)",
                        "SPT Month Error"
                    )
                    return 12
                return spt_month
            except ValueError:
                frappe.log_error(
                    f"Invalid SPT_BULAN format: {spt_month_str}. Must be an integer. Using default (12)",
                    "SPT Month Error"
                )
                return 12
        else:
            return 12  # Default to December
    except Exception as e:
        frappe.log_error(f"Error getting SPT month: {str(e)}", "SPT Month Error")
        return 12  # Default to December

# TER-related functions
def get_pph21_settings():
    """
    Get PPh 21 settings from DocType or defaults
    
    Returns:
        dict: PPh 21 settings including calculation method and TER usage
    """
    try:
        # Get settings from config
        config_tax = get_default_config("tax")
        
        if frappe.db.exists("DocType", "PPh 21 Settings"):
            doc_list = frappe.db.get_all("PPh 21 Settings")
            if doc_list:
                try:
                    doc = frappe.get_single("PPh 21 Settings")
                    
                    # Validate required fields
                    method = "Progressive"
                    use_ter = 0
                    
                    if hasattr(doc, 'calculation_method'):
                        method = doc.calculation_method
                        
                    if hasattr(doc, 'use_ter'):
                        use_ter = cint(doc.use_ter)
                        
                    return {
                        'calculation_method': method,
                        'use_ter': use_ter,
                        'ptkp_settings': get_ptkp_settings(),
                        'brackets': get_pph21_brackets()
                    }
                except Exception as e:
                    frappe.log_error(f"Error retrieving PPh 21 settings: {str(e)}", "PPh 21 Settings Error")
    except Exception as e:
        frappe.log_error(f"Error checking for PPh 21 Settings DocType: {str(e)}", "PPh 21 Settings Error")
    
    # Get settings from config or use defaults
    tax_config = get_default_config("tax")
    
    # Default settings from config or hardcoded defaults
    return {
        'calculation_method': tax_config.get('tax_calculation_method', 'Progressive'),
        'use_ter': tax_config.get('use_ter', 0),
        'ptkp_settings': get_ptkp_settings(),
        'brackets': get_pph21_brackets()
    }

def get_pph21_brackets():
    """
    Get PPh 21 tax brackets from DocType or defaults
    with improved error handling
    
    Returns:
        list: List of tax brackets with income ranges and rates
    """
    brackets = []
    
    try:
        if frappe.db.exists("DocType", "PPh 21 Settings"):
            try:
                # Check if there are settings records
                doc_list = frappe.db.get_all("PPh 21 Settings")
                if doc_list:
                    # Query tax brackets from child table
                    brackets = frappe.db.sql("""
                        SELECT income_from, income_to, tax_rate 
                        FROM `tabPPh 21 Tax Bracket`
                        WHERE parent = 'PPh 21 Settings'
                        ORDER BY income_from ASC
                    """, as_dict=1)
            except Exception as e:
                frappe.log_error(f"Error retrieving PPh 21 brackets from DB: {str(e)}", "PPh 21 Brackets Error")
    except Exception as e:
        frappe.log_error(f"Error checking for PPh 21 Settings DocType: {str(e)}", "PPh 21 Brackets Error")
    
    # If no brackets found, get from config
    if not brackets:
        config_brackets = get_default_config("tax_brackets")
        if config_brackets:
            brackets = config_brackets
        else:
            # Ultimate fallback to hardcoded brackets
            brackets = [
                {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
                {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
                {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
                {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
            ]
    
    # Validate brackets
    for i, bracket in enumerate(brackets):
        # Ensure all required fields exist
        if not all(k in bracket for k in ['income_from', 'income_to', 'tax_rate']):
            frappe.log_error(f"Invalid bracket format at index {i}: {bracket}", "PPh 21 Brackets Error")
            continue
        
        # Ensure values are numeric
        try:
            bracket['income_from'] = flt(bracket['income_from'])
            bracket['income_to'] = flt(bracket['income_to'])
            bracket['tax_rate'] = flt(bracket['tax_rate'])
        except Exception:
            frappe.log_error(f"Non-numeric values in bracket at index {i}: {bracket}", "PPh 21 Brackets Error")
    
    # Sort brackets by income_from to ensure proper order
    brackets.sort(key=lambda x: flt(x['income_from']))
    
    return brackets

def get_ter_rate(status_pajak, penghasilan_bruto):
    """
    Get TER rate for a specific tax status and income level
    with improved validation and error handling
    
    Args:
        status_pajak (str): Tax status (TK0, K0, etc)
        penghasilan_bruto (float): Gross income
        
    Returns:
        float: TER rate as decimal (e.g., 0.05 for 5%)
    """
    try:
        # Validate inputs
        if not status_pajak:
            status_pajak = "TK0"  # Default to TK0
            frappe.msgprint(_("Tax status not provided, using default (TK0)"))
            
        if not penghasilan_bruto:
            penghasilan_bruto = 0
            
        penghasilan_bruto = flt(penghasilan_bruto)
        if penghasilan_bruto < 0:
            frappe.msgprint(_("Negative income provided for TER calculation, using absolute value"))
            penghasilan_bruto = abs(penghasilan_bruto)
        
        # Map PTKP status to TER category using the new function
        ter_category = map_ptkp_to_ter(status_pajak)
        
        # First check if we can get from database table
        if frappe.db.exists("DocType", "PPh 21 TER Table"):
            ter = frappe.db.sql("""
                SELECT rate
                FROM `tabPPh 21 TER Table`
                WHERE status_pajak = %s
                  AND %s >= income_from
                  AND (%s <= income_to OR income_to = 0)
                LIMIT 1
            """, (ter_category, penghasilan_bruto, penghasilan_bruto), as_dict=1)
            
            if ter:
                # Convert percent to decimal
                rate = flt(ter[0].rate) / 100.0
                return rate
        
        # If no database result, try to get from config
        ter_rates = get_default_config("ter_rates")
        if ter_rates and ter_category in ter_rates:
            status_rates = ter_rates[ter_category]
            for rate_data in status_rates:
                income_from = flt(rate_data.get("income_from", 0))
                income_to = flt(rate_data.get("income_to", 0))
                
                if (penghasilan_bruto >= income_from) and (income_to == 0 or penghasilan_bruto <= income_to):
                    rate = flt(rate_data.get("rate", 0)) / 100.0
                    return rate
        
        # Sisanya sama seperti fungsi asli...
        # ... kode yang ada ...
    
    except Exception as e:
        frappe.log_error(
            f"Error getting TER rate for status {status_pajak} and income {penghasilan_bruto}: {str(e)}",
            "TER Rate Error"
        )
        debug_log(f"Error getting TER rate: {str(e)}", "TER Rate Error", trace=True)
        return 0

def should_use_ter():
    """
    Check if TER method should be used based on system settings
    with error handling
    
    Returns:
        bool: True if TER should be used, False otherwise
    """
    try:
        # First check config settings
        tax_config = get_default_config("tax")
        if tax_config:
            calc_method = tax_config.get("tax_calculation_method")
            use_ter = tax_config.get("use_ter")
            if calc_method == "TER" and use_ter:
                return True
                
        # If not determined from config, check DocType
        if frappe.db.exists("DocType", "PPh 21 Settings"):
            # Check if there are settings records
            doc_list = frappe.db.get_all("PPh 21 Settings")
            if not doc_list:
                return False
                
            # Get settings
            pph_settings = frappe.get_single("PPh 21 Settings")
            
            # Check required fields
            if not hasattr(pph_settings, 'calculation_method') or not hasattr(pph_settings, 'use_ter'):
                return False
                
            return (pph_settings.calculation_method == "TER" and cint(pph_settings.use_ter) == 1)
    except Exception as e:
        frappe.log_error(f"Error checking TER method settings: {str(e)}", "TER Settings Error")
        debug_log(f"Error checking TER method settings: {str(e)}", "TER Settings Error", trace=True)
        return False

def create_tax_summary_doc(employee, year, tax_amount=0, is_using_ter=0, ter_rate=0):
    """
    Create or update Employee Tax Summary document
    with improved validation and error handling
    
    Args:
        employee (str): Employee ID
        year (int): Tax year
        tax_amount (float): PPh 21 amount to add
        is_using_ter (int): Whether TER method is used
        ter_rate (float): TER rate if applicable
        
    Returns:
        object: Employee Tax Summary document or None on error
    """
    try:
        # Validate required parameters
        if not employee:
            frappe.throw(_("Employee is required to create tax summary"))
            
        if not year or not isinstance(year, int):
            frappe.throw(_("Valid tax year is required to create tax summary"))
            
        # Convert numeric parameters to appropriate types
        tax_amount = flt(tax_amount)
        is_using_ter = cint(is_using_ter)
        ter_rate = flt(ter_rate)
        
        # Check if Employee Tax Summary DocType exists
        if not frappe.db.exists("DocType", "Employee Tax Summary"):
            frappe.log_error("Employee Tax Summary DocType does not exist", "Tax Summary Creation Error")
            return None
            
        # Check if employee exists
        if not frappe.db.exists("Employee", employee):
            frappe.log_error(f"Employee {employee} does not exist", "Tax Summary Creation Error")
            return None
        
        # Check if a record already exists
        filters = {"employee": employee, "year": year}
        name = frappe.db.get_value("Employee Tax Summary", filters)
        
        if name:
            try:
                # Update existing record
                doc = frappe.get_doc("Employee Tax Summary", name)
                
                # Validate ytd_tax field exists
                if not hasattr(doc, 'ytd_tax'):
                    frappe.log_error(
                        f"Employee Tax Summary {name} missing required field: ytd_tax",
                        "Tax Summary Update Error"
                    )
                    return None
                    
                doc.ytd_tax = flt(doc.ytd_tax) + flt(tax_amount)
                
                # Set TER information if applicable and fields exist
                if is_using_ter:
                    if hasattr(doc, 'is_using_ter'):
                        doc.is_using_ter = 1
                    if hasattr(doc, 'ter_rate'):
                        doc.ter_rate = ter_rate
                
                # Save the document
                doc.flags.ignore_validate_update_after_submit = True
                doc.save(ignore_permissions=True)
                frappe.db.commit()
                return doc
            except Exception as e:
                frappe.log_error(
                    f"Error updating tax summary {name} for {employee}, year {year}: {str(e)}",
                    "Tax Summary Update Error"
                )
                debug_log(f"Error updating tax summary: {str(e)}", "Tax Summary Error", trace=True)
                return None
        else:
            try:
                # Get employee name
                employee_name = frappe.db.get_value("Employee", employee, "employee_name")
                if not employee_name:
                    employee_name = employee
                
                # Create new record
                doc = frappe.new_doc("Employee Tax Summary")
                
                # Set required fields
                doc.employee = employee
                doc.employee_name = employee_name
                doc.year = year
                doc.ytd_tax = flt(tax_amount)
                
                # Set title if field exists
                if hasattr(doc, 'title'):
                    doc.title = f"{employee_name} - {year}"
                
                # Set TER information if applicable and fields exist
                if is_using_ter:
                    if hasattr(doc, 'is_using_ter'):
                        doc.is_using_ter = 1
                    if hasattr(doc, 'ter_rate'):
                        doc.ter_rate = ter_rate
                
                # Insert the document
                doc.insert(ignore_permissions=True)
                frappe.db.commit()
                return doc
            except Exception as e:
                frappe.log_error(
                    f"Error creating tax summary for {employee}, year {year}: {str(e)}",
                    "Tax Summary Creation Error"
                )
                debug_log(f"Error creating tax summary: {str(e)}", "Tax Summary Error", trace=True)
                return None
    except Exception as e:
        frappe.log_error(
            f"Error in create_tax_summary_doc for {employee}, year {year}: {str(e)}",
            "Tax Summary Error"
        )
        debug_log(f"Error in create_tax_summary_doc: {str(e)}", "Tax Summary Error", trace=True)
        return None

def get_ytd_tax_info(employee, date=None):
    """
    Get year-to-date tax information for an employee
    with improved validation and error handling
    
    Args:
        employee (str): Employee ID
        date (datetime, optional): Date to determine year, defaults to current date
        
    Returns:
        dict: YTD tax information
    """
    try:
        # Validate employee parameter
        if not employee:
            frappe.throw(_("Employee is required to get YTD tax information"))
            
        # Check if employee exists
        if not frappe.db.exists("Employee", employee):
            frappe.log_error(f"Employee {employee} does not exist", "YTD Tax Info Error")
            return {"ytd_tax": 0, "is_using_ter": 0, "ter_rate": 0}
        
        # Determine tax year from date
        if not date:
            date = getdate()
        
        year = date.year
        
        # First try to get from Employee Tax Summary if exists
        if frappe.db.exists("DocType", "Employee Tax Summary"):
            try:
                tax_summary = frappe.db.get_value(
                    "Employee Tax Summary",
                    {"employee": employee, "year": year},
                    ["ytd_tax", "is_using_ter", "ter_rate"],
                    as_dict=1
                )
                
                if tax_summary:
                    return {
                        "ytd_tax": flt(tax_summary.ytd_tax),
                        "is_using_ter": cint(tax_summary.is_using_ter),
                        "ter_rate": flt(tax_summary.ter_rate)
                    }
            except Exception as e:
                frappe.log_error(
                    f"Error retrieving tax summary for {employee}, year {year}: {str(e)}",
                    "YTD Tax Info Error"
                )
                debug_log(f"Error retrieving tax summary: {str(e)}", "YTD Tax Info Error", trace=True)
                # Continue to alternate method
        
        # Alternatively, calculate from submitted salary slips
        try:
            salary_slips = frappe.get_all(
                "Salary Slip",
                filters={
                    "employee": employee,
                    "start_date": [">=", f"{year}-01-01"],
                    "end_date": ["<", date],
                    "docstatus": 1
                },
                fields=["name"]
            )
            
            ytd_tax = 0
            is_using_ter = 0
            ter_rate = 0
            
            for slip in salary_slips:
                try:
                    slip_doc = frappe.get_doc("Salary Slip", slip.name)
                    
                    # Get PPh 21 component
                    if hasattr(slip_doc, 'deductions'):
                        for deduction in slip_doc.deductions:
                            if deduction.salary_component == "PPh 21":
                                ytd_tax += flt(deduction.amount)
                                break
                    
                    # Check if using TER
                    if hasattr(slip_doc, 'is_using_ter') and slip_doc.is_using_ter:
                        is_using_ter = 1
                        if hasattr(slip_doc, 'ter_rate') and flt(slip_doc.ter_rate) > ter_rate:
                            ter_rate = flt(slip_doc.ter_rate)
                except Exception as e:
                    frappe.log_error(
                        f"Error processing salary slip {slip.name}: {str(e)}",
                        "YTD Tax Calculation Error"
                    )
                    debug_log(f"Error processing salary slip: {str(e)}", "YTD Tax Calculation Error", trace=True)
                    continue
            
            # Return the calculated values
            return {
                "ytd_tax": ytd_tax,
                "is_using_ter": is_using_ter,
                "ter_rate": ter_rate
            }
        except Exception as e:
            frappe.log_error(
                f"Error calculating YTD tax from salary slips for {employee}, year {year}: {str(e)}",
                "YTD Tax Calculation Error"
            )
            debug_log(f"Error calculating YTD tax: {str(e)}", "YTD Tax Calculation Error", trace=True)
            
            # Return default values on error
            return {
                "ytd_tax": 0,
                "is_using_ter": 0,
                "ter_rate": 0
            }
    except Exception as e:
        frappe.log_error(
            f"Error in get_ytd_tax_info for {employee}: {str(e)}",
            "YTD Tax Info Error"
        )
        debug_log(f"Error in get_ytd_tax_info: {str(e)}", "YTD Tax Info Error", trace=True)
        
        # Return default values on error
        return {
            "ytd_tax": 0,
            "is_using_ter": 0,
            "ter_rate": 0
        }
# Di file utils.py, tambahkan fungsi helper untuk mendapatkan BPJS Settings dengan fallback

def get_bpjs_settings_safely():
    """
    Get BPJS Settings with fallback if not found
    
    Returns:
        object: BPJS Settings document or dict with default values
    """
    try:
        # Check if DocType exists
        if not frappe.db.exists("DocType", "BPJS Settings"):
            frappe.log_error("BPJS Settings DocType not found", "BPJS Settings Error")
            return create_default_settings_dict()
            
        # Try to get the singleton
        try:
            return frappe.get_doc("BPJS Settings", "BPJS Settings")
        except frappe.DoesNotExistError:
            frappe.log_error("BPJS Settings singleton not found, will create", "BPJS Settings")
            return create_default_bpjs_settings()
            
    except Exception as e:
        frappe.log_error(
            f"Error retrieving BPJS Settings: {str(e)}\n\n{frappe.get_traceback()}", 
            "BPJS Settings Error"
        )
        return create_default_settings_dict()

def create_default_settings_dict():
    """Create default settings dictionary when BPJS Settings document can't be found"""
    return {
        "kesehatan_employee_percent": 1.0,
        "kesehatan_employer_percent": 4.0,
        "kesehatan_max_salary": 12000000.0,
        "jht_employee_percent": 2.0,
        "jht_employer_percent": 3.7,
        "jp_employee_percent": 1.0,
        "jp_employer_percent": 2.0,
        "jp_max_salary": 9000000.0,
        "jkk_percent": 0.54,
        "jkm_percent": 0.3
    }

def create_default_bpjs_settings():
    """Try to create BPJS Settings document if it doesn't exist"""
    try:
        default_values = create_default_settings_dict()
        
        # Create new BPJS Settings
        doc = frappe.new_doc("BPJS Settings")
        
        # Set default values
        for key, value in default_values.items():
            if hasattr(doc, key):
                setattr(doc, key, value)
                
        # Add flags to bypass validation
        doc.flags.ignore_permissions = True
        doc.flags.ignore_mandatory = True
        doc.flags.ignore_validate = True
        
        # Try to save
        doc.insert()
        frappe.db.commit()
        
        frappe.log_error("Created default BPJS Settings", "BPJS Settings")
        return doc
    except Exception as e:
        frappe.log_error(
            f"Failed to create default BPJS Settings: {str(e)}\n\n{frappe.get_traceback()}", 
            "BPJS Settings Error"
        )
        return create_default_settings_dict()