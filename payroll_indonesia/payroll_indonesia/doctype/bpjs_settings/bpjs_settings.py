# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-04 03:32:10 by dannyaudian

from __future__ import unicode_literals
import frappe
import os
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime
from payroll_indonesia.fixtures.setup import find_parent_account

__all__ = [
    'validate',
    'setup_accounts',
    'on_update',
    'create_account',
    'create_parent_liability_account',
    'create_parent_expense_account',
    'retry_bpjs_mapping',
    'debug_log',
    'BPJSSettings'
]

# MODULE LEVEL FUNCTIONS - Used by hooks.py
def validate(doc, method=None):
    """
    Module level validation function for hooks
    
    Args:
        doc (obj): BPJS Settings document
        method (str, optional): Method that called this function
    """
    if getattr(doc, "flags", {}).get("ignore_validate"):
        return
        
    doc.validate_data_types()
    doc.validate_percentages() 
    doc.validate_max_salary()
    doc.validate_account_types()

def setup_accounts(doc):
    """
    Module level setup_accounts called by hooks
    
    Args:
        doc (obj): BPJS Settings document
    """
    if not doc:
        return
    doc.setup_accounts()
    
def on_update(doc):
    """
    Module level on_update called by hooks
    
    Args:
        doc (obj): BPJS Settings document
    """
    if not doc:
        return
    try:
        doc.update_salary_structures()
        doc.ensure_bpjs_mapping_for_all_companies()
    except Exception as e:
        frappe.log_error(f"Error in on_update: {str(e)}", "BPJS Settings On Update Error")

# HELPER FUNCTIONS
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
            
        # Find a suitable parent account with explicit error handling
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
        
        for company in companies:
            try:
                if not frappe.db.exists("BPJS Account Mapping", {"company": company}):
                    debug_log(f"Retrying BPJS Account Mapping creation for {company}", "BPJS Mapping Retry")
                    mapping_name = create_default_mapping(company)
                    
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

class BPJSSettings(Document):
    def validate(self):
        """Validate BPJS settings"""
        if getattr(self, "flags", {}).get("ignore_validate"):
            return
            
        self.validate_data_types()
        self.validate_percentages()
        self.validate_max_salary()
        self.validate_account_types()
    
    def validate_data_types(self):
        """Validate that all numeric fields contain valid numbers"""
        numeric_fields = [
            "kesehatan_employee_percent", "kesehatan_employer_percent",
            "jht_employee_percent", "jht_employer_percent",
            "jp_employee_percent", "jp_employer_percent",
            "jkk_percent", "jkm_percent",
            "kesehatan_max_salary", "jp_max_salary"
        ]
        
        for field in numeric_fields:
            try:
                value = flt(self.get(field))
                # Update with cleaned value
                self.set(field, value)
            except (ValueError, TypeError):
                frappe.throw(_(f"Value of {field} must be a number"))
    
    def validate_percentages(self):
        """Validate BPJS percentage ranges"""
        validations = [
            ("kesehatan_employee_percent", 0, 5, "BPJS Kesehatan employee percentage must be between 0 and 5%"),
            ("kesehatan_employer_percent", 0, 10, "BPJS Kesehatan employer percentage must be between 0 and 10%"),
            ("jht_employee_percent", 0, 5, "JHT employee percentage must be between 0 and 5%"),
            ("jht_employer_percent", 0, 10, "JHT employer percentage must be between 0 and 10%"),
            ("jp_employee_percent", 0, 5, "JP employee percentage must be between 0 and 5%"),
            ("jp_employer_percent", 0, 5, "JP employer percentage must be between 0 and 5%"),
            ("jkk_percent", 0, 5, "JKK percentage must be between 0 and 5%"),
            ("jkm_percent", 0, 5, "JKM percentage must be between 0 and 5%")
        ]
        
        for field, min_val, max_val, message in validations:
            value = flt(self.get(field))
            if value < min_val or value > max_val:
                frappe.throw(_(message))
    
    def validate_max_salary(self):
        """Validate maximum salary thresholds"""
        if flt(self.kesehatan_max_salary) <= 0:
            frappe.throw(_("BPJS Kesehatan maximum salary must be greater than 0"))
            
        if flt(self.jp_max_salary) <= 0:
            frappe.throw(_("JP maximum salary must be greater than 0"))
    
    def validate_account_types(self):
        """Validate that BPJS accounts are of the correct type"""
        account_fields = ["kesehatan_account", "jht_account", "jp_account", "jkk_account", "jkm_account"]
        
        for field in account_fields:
            account = self.get(field)
            if account:
                account_data = frappe.db.get_value(
                    "Account", 
                    account, 
                    ["account_type", "root_type", "company", "is_group"], 
                    as_dict=1
                )
                
                if not account_data:
                    frappe.throw(_("Account {0} does not exist").format(account))
                    
                if account_data.root_type != "Liability" or (account_data.account_type != "Payable" and account_data.account_type != "Liability"):
                    frappe.throw(_("Account {0} must be of type 'Payable' or a Liability account").format(account))
    
    def setup_accounts(self):
        """Setup GL accounts for BPJS components for all companies using standardized naming"""
        debug_log("Starting setup_accounts method", "BPJS Setup")
        
        try:
            # Get companies to process
            default_company = frappe.defaults.get_defaults().get("company")
            if not default_company:
                companies = frappe.get_all("Company", pluck="name")
                if not companies:
                    frappe.msgprint(_("No company found. Please create a company before setting up BPJS accounts."))
                    return
            else:
                companies = [default_company]
        
            debug_log(f"Setting up accounts for companies: {', '.join(companies)}", "BPJS Setup")
            
            # Track results for summary
            results = {
                "success": [],
                "failed": [],
                "skipped": []
            }
            
            # Loop through companies and create accounts
            for company in companies:
                try:
                    # Cache company abbreviation for consistency
                    abbr = frappe.get_cached_value('Company', company, 'abbr')
                    if not abbr:
                        debug_log(f"Company {company} has no abbreviation, skipping", "BPJS Setup")
                        results["skipped"].append(company)
                        continue
                    
                    # Create parent accounts with enhanced error handling
                    debug_log(f"Creating parent accounts for company {company}", "BPJS Setup")
                    liability_parent = create_parent_liability_account(company)
                    
                    if not liability_parent:
                        debug_log(f"Failed to create parent liability account for {company}, stopping setup", "BPJS Setup Error")
                        results["failed"].append(f"{company} (liability parent)")
                        continue
                    
                    expense_parent = create_parent_expense_account(company)
                    
                    if not expense_parent:
                        debug_log(f"Failed to create parent expense account for {company}, stopping setup", "BPJS Setup Error")
                        results["failed"].append(f"{company} (expense parent)")
                        continue
                    
                    debug_log(f"Created/verified parent accounts for {company}:", "BPJS Setup")
                    debug_log(f"  - Liability parent: {liability_parent}", "BPJS Setup")
                    debug_log(f"  - Expense parent: {expense_parent}", "BPJS Setup")
                
                    # Define BPJS liability accounts with standardized names
                    bpjs_liability_accounts = {
                        "kesehatan_account": {
                            "account_name": "BPJS Kesehatan Payable",
                            "account_type": "Payable",
                            "field": "kesehatan_account"
                        },
                        "jht_account": {
                            "account_name": "BPJS JHT Payable",
                            "account_type": "Payable",
                            "field": "jht_account"
                        },
                        "jp_account": {
                            "account_name": "BPJS JP Payable",
                            "account_type": "Payable",
                            "field": "jp_account"
                        },
                        "jkk_account": {
                            "account_name": "BPJS JKK Payable",
                            "account_type": "Payable",
                            "field": "jkk_account"
                        },
                        "jkm_account": {
                            "account_name": "BPJS JKM Payable",
                            "account_type": "Payable",
                            "field": "jkm_account"
                        }
                    }
                
                    # Create liability accounts and update settings
                    created_liability_accounts = []
                    for key, account_info in bpjs_liability_accounts.items():
                        # Skip if already set to a valid account
                        current_account = self.get(account_info["field"])
                        if current_account and frappe.db.exists("Account", current_account):
                            debug_log(f"Field {account_info['field']} already set to {current_account}", "BPJS Setup")
                            continue
                        
                        # Create new account with enhanced error handling
                        account = create_account(
                            company=company,
                            account_name=account_info["account_name"],
                            account_type=account_info["account_type"],
                            parent=liability_parent
                        )
                        
                        if account:
                            # Update settings field with new account
                            self.set(account_info["field"], account)
                            created_liability_accounts.append(account)
                            debug_log(f"Set {account_info['field']} to {account}", "BPJS Setup")
                        else:
                            debug_log(f"Failed to create account {account_info['account_name']}", "BPJS Setup Error")
                
                    # Define expense accounts with standardized names
                    if expense_parent:
                        bpjs_expense_accounts = {
                            "kesehatan_employer_expense": "BPJS Kesehatan Employer Expense",
                            "jht_employer_expense": "BPJS JHT Employer Expense",
                            "jp_employer_expense": "BPJS JP Employer Expense",
                            "jkk_employer_expense": "BPJS JKK Employer Expense",
                            "jkm_employer_expense": "BPJS JKM Employer Expense"
                        }
                        
                        # Create expense accounts (these won't be stored in BPJS Settings but in the mapping)
                        created_expense_accounts = []
                        for field, account_name in bpjs_expense_accounts.items():
                            # Calculate full account name for checking if exists
                            full_account_name = f"{account_name} - {abbr}"
                            if frappe.db.exists("Account", full_account_name):
                                debug_log(f"Expense account {full_account_name} already exists", "BPJS Setup")
                                created_expense_accounts.append(full_account_name)
                                continue
                                
                            account = create_account(
                                company=company,
                                account_name=account_name,
                                account_type="Expense",
                                parent=expense_parent
                            )
                            
                            if account:
                                created_expense_accounts.append(account)
                                debug_log(f"Created expense account: {account}", "BPJS Setup")
                
                    # Save changes to BPJS Settings
                    if created_liability_accounts:
                        self.flags.ignore_validate = True
                        self.flags.ignore_mandatory = True
                        self.save(ignore_permissions=True)
                        debug_log(f"Saved BPJS Settings with {len(created_liability_accounts)} new liability accounts", "BPJS Setup")
                
                    # Create BPJS mapping
                    mapping_result = self._create_bpjs_mapping(company)
                    debug_log(f"BPJS mapping creation result for {company}: {mapping_result}", "BPJS Setup")
                    
                    # Track company as success if we got this far
                    results["success"].append(company)
                
                except Exception as e:
                    frappe.log_error(
                        f"Error setting up BPJS accounts for company {company}: {str(e)}\n\n"
                        f"Traceback: {frappe.get_traceback()}", 
                        "BPJS Setup Error"
                    )
                    debug_log(f"Error setting up BPJS accounts for {company}: {str(e)}", "BPJS Setup Error", trace=True)
                    results["failed"].append(company)
                    continue
            
            # Log summary of results
            if results["success"]:
                debug_log(f"Successfully set up BPJS accounts for companies: {', '.join(results['success'])}", "BPJS Setup")
                
            if results["failed"]:
                debug_log(f"Failed to set up BPJS accounts for companies: {', '.join(results['failed'])}", "BPJS Setup Error")
                
            if results["skipped"]:
                debug_log(f"Skipped BPJS account setup for companies: {', '.join(results['skipped'])}", "BPJS Setup")
                    
        except Exception as e:
            frappe.log_error(
                f"Error in setup_accounts: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}", 
                "BPJS Setup Error"
            )
            debug_log(f"Error in setup_accounts: {str(e)}", "BPJS Setup Error", trace=True)
    
    def _create_bpjs_mapping(self, company):
        """
        Create BPJS mapping for company
        
        Args:
            company (str): Company name
            
        Returns:
            str: Mapping name if created, None otherwise
        """
        try:
            # Check if mapping already exists
            existing_mapping = frappe.db.exists("BPJS Account Mapping", {"company": company})
            if existing_mapping:
                debug_log(f"BPJS Account Mapping already exists for {company}: {existing_mapping}", "BPJS Mapping")
                return existing_mapping
                
            # Import create_default_mapping function
            try:
                from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import create_default_mapping
                
                debug_log(f"Creating new BPJS Account Mapping for {company}", "BPJS Mapping")
                mapping_name = create_default_mapping(company)
                
                if mapping_name:
                    debug_log(f"Created BPJS mapping: {mapping_name}", f"Company: {company}")
                    return mapping_name
                else:
                    debug_log(f"Failed to create BPJS mapping for {company}", "BPJS Mapping Error")
                    return None
            except ImportError:
                frappe.logger().warning("Could not import create_default_mapping, skipping mapping creation")
                debug_log("Could not import create_default_mapping, skipping mapping creation", "BPJS Mapping Error")
                return None
            except Exception as e:
                frappe.log_error(
                    f"Error creating mapping for {company}: {str(e)}\n\n"
                    f"Traceback: {frappe.get_traceback()}", 
                    "BPJS Mapping Error"
                )
                debug_log(f"Error creating mapping for {company}: {str(e)}", "BPJS Mapping Error", trace=True)
                return None
        except Exception as e:
            frappe.log_error(
                f"Error in _create_bpjs_mapping for {company}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}", 
                "BPJS Mapping Error"
            )
            debug_log(f"Error in _create_bpjs_mapping for {company}: {str(e)}", "BPJS Mapping Error", trace=True)
            return None
    
    def on_update(self):
        """Update related documents when settings change"""
        debug_log("Starting on_update processing", "BPJS Settings")
        
        try:
            # Update salary structure assignments if needed
            self.update_salary_structures()
        
            # Ensure all companies have BPJS mapping
            self.ensure_bpjs_mapping_for_all_companies()
        except Exception as e:
            frappe.log_error(
                f"Error in on_update: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}", 
                "BPJS Settings Update Error"
            )
            debug_log(f"Error in on_update: {str(e)}", "BPJS Settings Update Error", trace=True)

    def update_salary_structures(self):
        """
        Update BPJS components in active salary structures
        with proper handling of submitted documents
        """
        try:
            debug_log("Starting update_salary_structures method", "BPJS Settings")
        
            # Find active salary structures
            salary_structures = frappe.get_all(
                "Salary Structure",
                filters={"is_active": "Yes"},
                fields=["name", "docstatus"],
            )
        
            if not salary_structures:
                debug_log("No active salary structures found", "BPJS Settings")
                return
                
            # Log for debug
            debug_log(f"Found {len(salary_structures)} active salary structures", "BPJS Settings")
        
            # Get list of BPJS components to update with standardized names
            bpjs_components = {
                "BPJS Kesehatan Employee": self.kesehatan_employee_percent,
                "BPJS Kesehatan Employer": self.kesehatan_employer_percent,
                "BPJS JHT Employee": self.jht_employee_percent,
                "BPJS JHT Employer": self.jht_employer_percent,
                "BPJS JP Employee": self.jp_employee_percent,
                "BPJS JP Employer": self.jp_employer_percent,
                "BPJS JKK": self.jkk_percent,
                "BPJS JKM": self.jkm_percent
            }
        
            # Count statistics
            updated_count = 0
            submitted_count = 0
            skipped_count = 0
            error_count = 0
        
            # Update each salary structure
            for structure in salary_structures:
                try:
                    # Different handling based on docstatus
                    if structure.docstatus == 1:  # Submitted
                        debug_log(f"Salary structure {structure.name} is submitted, using alternative update method", "BPJS Settings")
                    
                        # For submitted structures, we need to create amendment rather than direct updates
                        # Instead, we'll just log this for manual follow-up
                        submitted_count += 1
                        continue
                
                    # For draft structures, proceed with normal updates    
                    ss = frappe.get_doc("Salary Structure", structure.name)
                    debug_log(f"Processing salary structure: {structure.name} (draft)", "BPJS Settings")
                
                    # Flag to check if changes were made
                    changes_made = False
                
                    # Track missing components
                    missing_components = []
                
                    # Update each component
                    for component_name, percent in bpjs_components.items():
                        # Check in earnings
                        found = False
                        for detail in ss.earnings:
                            if detail.salary_component == component_name:
                                found = True
                                if detail.amount_based_on_formula and detail.formula:
                                    debug_log(f"Component {component_name} uses custom formula, skipping", "BPJS Settings")
                                    continue
                            
                                # Update rate if needed
                                if detail.amount != percent:
                                    debug_log(f"Updating {component_name} in earnings from {detail.amount} to {percent}", "BPJS Settings")
                                    detail.amount = percent
                                    changes_made = True
                                break
                            
                        if not found:
                            # Check in deductions
                            for detail in ss.deductions:
                                if detail.salary_component == component_name:
                                    found = True
                                    if detail.amount_based_on_formula and detail.formula:
                                        debug_log(f"Component {component_name} uses custom formula, skipping", "BPJS Settings")
                                        continue
                                
                                    # Update rate if needed
                                    if detail.amount != percent:
                                        debug_log(f"Updating {component_name} in deductions from {detail.amount} to {percent}", "BPJS Settings")
                                        detail.amount = percent
                                        changes_made = True
                                    break
                    
                        if not found:
                            missing_components.append(component_name)
                
                    # Log warning about missing components
                    if missing_components:
                        debug_log(f"Salary Structure {structure.name} missing BPJS components: {', '.join(missing_components)}", "BPJS Settings")
                        skipped_count += 1
                
                    # Save if changes were made
                    if changes_made:
                        ss.flags.ignore_validate = True
                        ss.flags.ignore_mandatory = True
                        ss.save(ignore_permissions=True)
                        updated_count += 1
                        debug_log(f"Saved changes to {structure.name}", "BPJS Settings")
                    
                except Exception as e:
                    error_count += 1
                    frappe.log_error(
                        f"Error updating salary structure {structure.name}: {str(e)}\n\n"
                        f"Traceback: {frappe.get_traceback()}", 
                        "BPJS Update Error"
                    )
                    debug_log(f"Error updating {structure.name}: {str(e)}", "BPJS Settings", trace=True)
                    continue
        
            # Log summary
            debug_log(
                f"Salary Structure Update Summary: "
                f"Updated: {updated_count}, "
                f"Submitted (skipped): {submitted_count}, "
                f"Missing components: {skipped_count}, "
                f"Errors: {error_count}",
                "BPJS Settings"
            )
                
        except Exception as e:
            frappe.log_error(
                f"Error in update_salary_structures: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}", 
                "BPJS Settings Update Error"
            )
            debug_log(f"Critical error in update_salary_structures: {str(e)}", "BPJS Settings", trace=True)
        
    def ensure_bpjs_mapping_for_all_companies(self):
        """Ensure all companies have BPJS mapping"""
        try:
            debug_log("Starting ensure_bpjs_mapping_for_all_companies method", "BPJS Settings")
            companies = frappe.get_all("Company", pluck="name")
            failed_companies = []
        
            for company in companies:
                # Check if mapping exists
                mapping_exists = frappe.db.exists("BPJS Account Mapping", {"company": company})
                debug_log(f"Company {company} mapping exists: {mapping_exists}", "BPJS Settings")
            
                if not mapping_exists:
                    mapping_name = self._create_bpjs_mapping(company)
                    if not mapping_name:
                        failed_companies.append(company)
                        debug_log(f"Failed to create BPJS mapping for {company}, will retry later", "BPJS Settings")
    
            # Schedule retry for failed companies
            if failed_companies:
                debug_log(f"Scheduling retry for failed companies: {', '.join(failed_companies)}", "BPJS Settings")
                try:
                    frappe.enqueue(
                        method="payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.bpjs_settings.retry_bpjs_mapping",
                        companies=failed_companies,
                        queue="long",
                        timeout=1500
                    )
                except Exception as e:
                    frappe.log_error(
                        f"Failed to schedule retry for BPJS mapping: {str(e)}\n\n"
                        f"Traceback: {frappe.get_traceback()}", 
                        "BPJS Mapping Error"
                    )
                    debug_log(f"Failed to schedule retry for BPJS mapping: {str(e)}", "BPJS Settings", trace=True)
                
        except Exception as e:
            frappe.log_error(
                f"Error ensuring BPJS mapping for all companies: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}", 
                "BPJS Settings Update Error"
            )
            debug_log(f"Critical error in ensure_bpjs_mapping_for_all_companies: {str(e)}", "BPJS Settings", trace=True)

    @frappe.whitelist()
    def export_settings(self):
        """
        Export BPJS settings to a format that can be imported by other instances
        
        Returns:
            dict: Dictionary of exportable settings
        """
        # Fields to export
        fields_to_export = [
            "kesehatan_employee_percent",
            "kesehatan_employer_percent",
            "kesehatan_max_salary",
            "jht_employee_percent", 
            "jht_employer_percent",
            "jp_employee_percent",
            "jp_employer_percent",
            "jp_max_salary",
            "jkk_percent",
            "jkm_percent"
        ]
        
        result = {}
        for field in fields_to_export:
            result[field] = flt(self.get(field))
            
        return result
