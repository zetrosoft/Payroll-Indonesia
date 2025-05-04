# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-04 01:49:05 by dannyaudian

import frappe
from frappe import _ 
from frappe.model.document import Document
from frappe.utils import flt, cstr, now_datetime

# Import shared functions from setup.py to avoid duplication
from payroll_indonesia.fixtures.setup import (
    find_parent_account,
    create_account,
    DEFAULT_BPJS_VALUES,
    get_default_bpjs_values,
    debug_log
)

__all__ = [
    'BPJSAccountMapping',
    'get_mapping_for_company',
    'create_default_mapping',
    'create_parent_account_for_mapping',
    'find_valid_parent',
    'setup_expense_accounts',
    'create_bpjs_settings',
    'diagnose_accounts',
    'validate',
    'on_update_mapping'
]

# Module level functions
@frappe.whitelist()
def get_mapping_for_company(company=None):
    """
    Get BPJS Account mapping for specified company
    
    Args:
        company (str, optional): Company name to get mapping for, uses default if not specified
        
    Returns:
        dict: Dictionary containing account mapping details or None if not found
    """
    if not company:
        company = frappe.defaults.get_user_default("Company")
        if not company:
            # Try to get first company
            companies = frappe.get_all("Company")
            if companies:
                company = companies[0].name
    
    if not company:
        return None
    
    # Try to get from cache first
    cache_key = f"bpjs_mapping_{company}"
    mapping_dict = frappe.cache().get_value(cache_key)
    
    if mapping_dict:
        return mapping_dict
    
    try:
        # Find mapping for this company
        mapping_name = frappe.db.get_value(
            "BPJS Account Mapping", 
            {"company": company},
            "name"
        )
        
        # If no mapping exists, try to create one with BPJS Settings accounts
        if not mapping_name:
            mapping_name = create_default_mapping(company)
            
        if not mapping_name:
            return None
        
        # Get complete document data
        mapping = frappe.get_cached_doc("BPJS Account Mapping", mapping_name)
        
        # Convert to dictionary for Jinja template use
        mapping_dict = {
            "name": mapping.name,
            "company": mapping.company,
            "mapping_name": mapping.mapping_name,
            "kesehatan_employee_account": mapping.kesehatan_employee_account,
            "jht_employee_account": mapping.jht_employee_account,
            "jp_employee_account": mapping.jp_employee_account,
            "kesehatan_employer_debit_account": mapping.kesehatan_employer_debit_account,
            "jht_employer_debit_account": mapping.jht_employer_debit_account,
            "jp_employer_debit_account": mapping.jp_employer_debit_account,
            "jkk_employer_debit_account": mapping.jkk_employer_debit_account,
            "jkm_employer_debit_account": mapping.jkm_employer_debit_account,
            "kesehatan_employer_credit_account": mapping.kesehatan_employer_credit_account,
            "jht_employer_credit_account": mapping.jht_employer_credit_account,
            "jp_employer_credit_account": mapping.jp_employer_credit_account,
            "jkk_employer_credit_account": mapping.jkk_employer_credit_account,
            "jkm_employer_credit_account": mapping.jkm_employer_credit_account
        }
        
        # Cache the result with appropriate TTL
        frappe.cache().set_value(cache_key, mapping_dict, expires_in_sec=3600)
        
        return mapping_dict
    except Exception as e:
        frappe.log_error(
            f"Error getting BPJS account mapping for company {company}: {str(e)}", 
            "BPJS Mapping Error"
        )
        return None


@frappe.whitelist()
def create_default_mapping(company):
    """
    Create a default BPJS Account Mapping based on BPJS Settings
    
    Args:
        company (str): Company name
        
    Returns:
        str: Name of created mapping or None if failed
    """
    try:
        # Check if mapping already exists
        existing_mapping = frappe.db.exists("BPJS Account Mapping", {"company": company})
        if existing_mapping:
            debug_log(f"BPJS Account Mapping already exists for {company}: {existing_mapping}", "BPJS Mapping")
            return existing_mapping
            
        # Create parent accounts first for liabilities and expenses
        liability_parent = create_parent_account_for_mapping(company, "Liability")
        expense_parent = create_parent_account_for_mapping(company, "Expense")
        
        if not liability_parent or not expense_parent:
            debug_log(f"Failed to create parent accounts for {company}", "BPJS Mapping Error")
            return None
            
        # Check BPJS Settings and create if not exists
        bpjs_settings = None
        if not frappe.db.exists("BPJS Settings", None):
            bpjs_settings = create_bpjs_settings()
        else:
            bpjs_settings = frappe.get_cached_doc("BPJS Settings")
            
        # Create new mapping with ignore_validate flag
        mapping = frappe.new_doc("BPJS Account Mapping")
        mapping.mapping_name = f"Default BPJS Mapping - {company}"
        mapping.company = company
        mapping.flags.ignore_validate = True
        
        # Set accounts from BPJS Settings if available
        if bpjs_settings:
            # Map BPJS Settings fields to mapping fields
            settings_to_mapping = {
                "kesehatan_account": ["kesehatan_employee_account", "kesehatan_employer_credit_account"],
                "jht_account": ["jht_employee_account", "jht_employer_credit_account"],
                "jp_account": ["jp_employee_account", "jp_employer_credit_account"],
                "jkk_account": ["jkk_employer_credit_account"],
                "jkm_account": ["jkm_employer_credit_account"]
            }
            
            for settings_field, mapping_fields in settings_to_mapping.items():
                if hasattr(bpjs_settings, settings_field) and bpjs_settings.get(settings_field):
                    for mapping_field in mapping_fields:
                        mapping.set(mapping_field, bpjs_settings.get(settings_field))
        
        # Insert mapping without strict validation
        mapping.insert(ignore_permissions=True, ignore_mandatory=True)
        
        # Create missing expense accounts
        setup_expense_accounts(mapping, expense_parent)
        
        # Save changes after account setup
        mapping.save(ignore_permissions=True)
        frappe.db.commit()
        
        # Clear cache for the company
        frappe.cache().delete_value(f"bpjs_mapping_{company}")
        
        debug_log(f"Successfully created BPJS Account Mapping for {company}: {mapping.name}", "BPJS Mapping")
        return mapping.name
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            f"Error creating default BPJS account mapping for {company}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}", 
            "BPJS Mapping Error"
        )
        return None


def create_parent_account_for_mapping(company, account_type):
    """
    Create or get parent account for BPJS accounts
    
    Args:
        company (str): Company name
        account_type (str): Account type (Liability or Expense)
        
    Returns:
        str: Account name if created or found, None otherwise
    """
    try:
        abbr = frappe.get_cached_value('Company', company, 'abbr')
        
        if account_type == "Liability":
            # Try several possible parent account candidates
            parent_candidates = [
                f"Duties and Taxes - {abbr}",
                f"Accounts Payable - {abbr}",
                f"Current Liabilities - {abbr}"
            ]
            
            account_name = f"BPJS Payable - {abbr}"
            account_label = "BPJS Payable"
            root_type = "Liability"
            
            # Check if target account already exists
            if frappe.db.exists("Account", account_name):
                return account_name
                
        else:  # Expense
            # Try several possible parent account candidates
            parent_candidates = [
                f"Indirect Expenses - {abbr}",
                f"Direct Expenses - {abbr}",
                f"Expenses - {abbr}"
            ]
            
            account_name = f"BPJS Expenses - {abbr}"
            account_label = "BPJS Expenses"
            root_type = "Expense"
            
            # Check if target account already exists
            if frappe.db.exists("Account", account_name):
                return account_name
        
        # Find valid parent account
        parent_account_name = find_valid_parent(company, parent_candidates)
        
        if not parent_account_name:
            debug_log(f"Could not find suitable parent account for {account_type} in {company}", "Account Creation")
            # Get root account for fallback
            root_type_accounts = frappe.get_all(
                "Account", 
                filters={"company": company, "is_group": 1, "root_type": root_type},
                order_by="lft",
                limit=1
            )
            
            if root_type_accounts:
                parent_account_name = root_type_accounts[0].name
            else:
                debug_log(f"No {root_type} parent account found for {company}", "Account Creation Error")
                return None
        
        # Create parent account if it doesn't exist
        if not frappe.db.exists("Account", account_name):
            try:
                doc = frappe.get_doc({
                    "doctype": "Account",
                    "account_name": account_label,
                    "parent_account": parent_account_name,
                    "company": company,
                    "account_type": account_type,
                    "account_currency": frappe.get_cached_value('Company', company, 'default_currency'),
                    "is_group": 1,
                    "root_type": root_type
                })
                doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
                frappe.db.commit()
                
                debug_log(f"Created parent account: {account_name}", "Account Creation")
            except Exception as e:
                debug_log(f"Error creating parent account {account_name}: {str(e)}", "Account Creation Error")
                return None
        
        return account_name
    except Exception as e:
        frappe.log_error(f"Error in create_parent_account_for_mapping: {str(e)}", "BPJS Account Creation Error")
        return None


def find_valid_parent(company, candidates):
    """
    Find first valid parent account from candidates list
    
    Args:
        company (str): Company name
        candidates (list): List of potential parent account names
        
    Returns:
        str: First valid parent account name or None if none found
    """
    for candidate in candidates:
        if frappe.db.exists("Account", candidate):
            return candidate
    return None


def setup_expense_accounts(mapping_doc, expense_parent):
    """
    Setup expense accounts that don't already exist
    
    Args:
        mapping_doc (obj): BPJS Account Mapping document
        expense_parent (str): Parent expense account name
    """
    try:
        company = mapping_doc.company
        
        # List of expense accounts that need to be created
        expense_accounts = {
            "kesehatan_employer_debit_account": "BPJS Kesehatan Employer Expense",
            "jht_employer_debit_account": "BPJS JHT Employer Expense",
            "jp_employer_debit_account": "BPJS JP Employer Expense",
            "jkk_employer_debit_account": "BPJS JKK Employer Expense",
            "jkm_employer_debit_account": "BPJS JKM Employer Expense"
        }
        
        for field, account_name in expense_accounts.items():
            # Skip if already filled
            if mapping_doc.get(field):
                continue
                
            # Create new account using standardized function from setup.py
            full_account_name = create_account(
                company=company,
                account_name=account_name,
                account_type="Expense",
                parent=expense_parent
            )
            
            if full_account_name:
                # Set in mapping document
                mapping_doc.set(field, full_account_name)
                
    except Exception as e:
        frappe.log_error(f"Error setting up expense accounts: {str(e)}", "BPJS Account Setup Error")


def create_bpjs_settings():
    """
    Create default BPJS Settings if not exists
    
    Returns:
        object: BPJS Settings document if created or exists, None otherwise
    """
    try:
        # Check if already exists
        if frappe.db.exists("BPJS Settings", "BPJS Settings"):
            return frappe.get_doc("BPJS Settings", "BPJS Settings")
            
        # Get default values using standardized function from setup.py
        values = get_default_bpjs_values()
            
        # Create settings
        settings = frappe.new_doc("BPJS Settings")
        
        # Set values
        for key, value in values.items():
            if hasattr(settings, key):
                settings.set(key, flt(value))
                
        # Bypass validation during setup
        settings.flags.ignore_validate = True
        settings.flags.ignore_permissions = True
        settings.insert()
        frappe.db.commit()
        
        debug_log("Created default BPJS Settings", "BPJS Setup")
        return settings
        
    except Exception as e:
        frappe.log_error(f"Error creating default BPJS Settings: {str(e)}", "BPJS Setup Error")
        return None


# Function for diagnostic purposes
@frappe.whitelist()
def diagnose_accounts():
    """
    Diagnose BPJS Account Mapping issues
    
    Returns:
        dict: Diagnostic information about BPJS accounts and mappings
    """
    results = {
        "settings_exists": False,
        "companies": [],
        "mappings": [],
        "issues": []
    }
    
    try:
        # Check BPJS Settings
        if frappe.db.exists("BPJS Settings", None):
            results["settings_exists"] = True
            settings = frappe.get_doc("BPJS Settings")
            results["settings"] = {
                "name": settings.name,
                "kesehatan_account": settings.get("kesehatan_account", "Not Set"),
                "jht_account": settings.get("jht_account", "Not Set"),
                "jp_account": settings.get("jp_account", "Not Set"),
                "jkk_account": settings.get("jkk_account", "Not Set"),
                "jkm_account": settings.get("jkm_account", "Not Set")
            }
        else:
            results["issues"].append("BPJS Settings doesn't exist")
        
        # Check companies and mappings
        companies = frappe.get_all("Company", pluck="name")
        for company in companies:
            company_info = {
                "name": company,
                "has_mapping": False,
                "issues": []
            }
            
            mapping = frappe.db.exists("BPJS Account Mapping", {"company": company})
            if mapping:
                company_info["has_mapping"] = True
                company_info["mapping_name"] = mapping
                
                # Get detailed mapping info and check accounts
                mapping_doc = frappe.get_doc("BPJS Account Mapping", mapping)
                mapping_info = {
                    "name": mapping_doc.name,
                    "company": mapping_doc.company,
                    "accounts": {}
                }
                
                # Check all accounts in mapping
                account_fields = [
                    "kesehatan_employee_account", "jht_employee_account", "jp_employee_account",
                    "kesehatan_employer_debit_account", "jht_employer_debit_account", 
                    "jp_employer_debit_account", "jkk_employer_debit_account", "jkm_employer_debit_account",
                    "kesehatan_employer_credit_account", "jht_employer_credit_account",
                    "jp_employer_credit_account", "jkk_employer_credit_account", "jkm_employer_credit_account"
                ]
                
                for field in account_fields:
                    account = mapping_doc.get(field)
                    mapping_info["accounts"][field] = account or "Not Set"
                    
                    if not account:
                        company_info["issues"].append(f"Missing account: {field}")
                    elif not frappe.db.exists("Account", account):
                        company_info["issues"].append(f"Account {account} does not exist")
                
                results["mappings"].append(mapping_info)
            else:
                company_info["issues"].append("No BPJS Account Mapping exists")
            
            results["companies"].append(company_info)
            
            # Add company issues to global issues list
            if company_info["issues"]:
                for issue in company_info["issues"]:
                    results["issues"].append(f"{company}: {issue}")
        
        return results
    except Exception as e:
        frappe.log_error(f"Error in diagnose_accounts: {str(e)}", "BPJS Diagnostic Error")
        return {"error": str(e), "traceback": frappe.get_traceback()}


# Module level functions for document hooks
def validate(doc, method=None):
    """
    Module level validation function for hooks
    
    Args:
        doc (obj): Document to validate
        method (str): Method that called this function (not used)
    """
    if getattr(doc, "flags", {}).get("ignore_validate"):
        debug_log(f"Skipping validation for {doc.name} during initial setup/migration", "BPJS Mapping")
        return
    
    # Call instance methods
    doc.validate_duplicate_mapping()
    doc.validate_account_types()
    doc.setup_missing_accounts()

def on_update_mapping(doc, method=None):
    """
    Module level on_update function for hooks
    
    Args:
        doc (obj): Document that was updated
        method (str): Method that called this function (not used)
    """
    # Clear cache for this mapping
    frappe.cache().delete_value(f"bpjs_mapping_{doc.company}")
    debug_log(f"Cleared cache for BPJS mapping of company {doc.company}", "BPJS Mapping Update")


class BPJSAccountMapping(Document):
    def validate(self):
        """Validate required fields and account types"""
        # Skip validation if in migration/setup mode
        if getattr(self, "flags", {}).get("ignore_validate"):
            debug_log(f"Skipping validation for {self.name} during initial setup/migration", "BPJS Mapping")
            return
        
        self.validate_duplicate_mapping()
        self.validate_account_types()
        self.setup_missing_accounts()
    
    def validate_duplicate_mapping(self):
        """Ensure no duplicate mapping exists for the same company"""
        if not self.is_new():
            # Skip validation when updating the same document
            return
            
        existing = frappe.db.get_value(
            "BPJS Account Mapping",
            {
                "company": self.company,
                "name": ["!=", self.name]
            },
            "mapping_name"
        )
        
        if existing:
            frappe.throw(_("BPJS Account Mapping '{0}' already exists for company {1}").format(
                existing, self.company
            ))
    
    def validate_account_types(self):
        """Validate that all accounts are of the correct type"""
        # Employee contribution accounts should be liability accounts
        self.validate_account_type(self.kesehatan_employee_account, ["Liability"], "BPJS Kesehatan Employee")
        self.validate_account_type(self.jht_employee_account, ["Liability"], "BPJS JHT Employee")
        self.validate_account_type(self.jp_employee_account, ["Liability"], "BPJS JP Employee")
        
        # Employer expense accounts should be expense accounts
        self.validate_account_type(self.kesehatan_employer_debit_account, ["Expense"], "BPJS Kesehatan Employer Expense")
        self.validate_account_type(self.jht_employer_debit_account, ["Expense"], "BPJS JHT Employer Expense")
        self.validate_account_type(self.jp_employer_debit_account, ["Expense"], "BPJS JP Employer Expense")
        self.validate_account_type(self.jkk_employer_debit_account, ["Expense"], "BPJS JKK Employer Expense")
        self.validate_account_type(self.jkm_employer_debit_account, ["Expense"], "BPJS JKM Employer Expense")
        
        # Employer liability accounts should be liability accounts
        self.validate_account_type(self.kesehatan_employer_credit_account, ["Liability"], "BPJS Kesehatan Employer Liability")
        self.validate_account_type(self.jht_employer_credit_account, ["Liability"], "BPJS JHT Employer Liability")
        self.validate_account_type(self.jp_employer_credit_account, ["Liability"], "BPJS JP Employer Liability")
        self.validate_account_type(self.jkk_employer_credit_account, ["Liability"], "BPJS JKK Employer Liability")
        self.validate_account_type(self.jkm_employer_credit_account, ["Liability"], "BPJS JKM Employer Liability")
    
    def validate_account_type(self, account, allowed_types, account_description):
        """
        Validate that an account is of the correct type
        
        Args:
            account (str): Account name to validate
            allowed_types (list): List of allowed account types
            account_description (str): Description of the account for error messages
        """
        if not account:
            # Skip validation if account is not provided
            return
            
        account_doc = frappe.db.get_value(
            "Account", 
            account, 
            ["account_type", "root_type", "company"], 
            as_dict=1
        )
        
        if not account_doc:
            frappe.throw(_("Account {0} does not exist").format(account))
            
        if account_doc.root_type not in allowed_types:
            frappe.throw(_("{0} account {1} must be a {2} account").format(
                account_description, account, " or ".join(allowed_types)
            ))
            
        if account_doc.company != self.company:
            frappe.throw(_("Account {0} does not belong to company {1}").format(
                account, self.company
            ))
    
    def setup_missing_accounts(self):
        """Setup missing GL accounts from BPJS Settings or create new ones"""
        # Try to get accounts from BPJS Settings first
        bpjs_settings_accounts = self.get_accounts_from_bpjs_settings()
        
        # Fields mapping: {field_name: account_description}
        employee_accounts = {
            "kesehatan_employee_account": "BPJS Kesehatan Employee Liability",
            "jht_employee_account": "BPJS JHT Employee Liability",
            "jp_employee_account": "BPJS JP Employee Liability"
        }
        
        employer_expense_accounts = {
            "kesehatan_employer_debit_account": "BPJS Kesehatan Employer Expense",
            "jht_employer_debit_account": "BPJS JHT Employer Expense",
            "jp_employer_debit_account": "BPJS JP Employer Expense",
            "jkk_employer_debit_account": "BPJS JKK Employer Expense",
            "jkm_employer_debit_account": "BPJS JKM Employer Expense"
        }
        
        employer_liability_accounts = {
            "kesehatan_employer_credit_account": "BPJS Kesehatan Employer Liability",
            "jht_employer_credit_account": "BPJS JHT Employer Liability",
            "jp_employer_credit_account": "BPJS JP Employer Liability",
            "jkk_employer_credit_account": "BPJS JKK Employer Liability",
            "jkm_employer_credit_account": "BPJS JKM Employer Liability"
        }
        
        # Create parent accounts for grouping
        liability_parent = self.create_parent_account(self.company, "Liability")
        expense_parent = self.create_parent_account(self.company, "Expense")
        
        # Setup employee liability accounts
        for field, description in employee_accounts.items():
            self.setup_account(
                field, 
                description, 
                "Liability", 
                liability_parent, 
                bpjs_settings_accounts.get(field)
            )
        
        # Setup employer expense accounts
        for field, description in employer_expense_accounts.items():
            self.setup_account(
                field, 
                description, 
                "Expense", 
                expense_parent, 
                bpjs_settings_accounts.get(field)
            )
        
        # Setup employer liability accounts
        for field, description in employer_liability_accounts.items():
            self.setup_account(
                field, 
                description, 
                "Liability", 
                liability_parent, 
                bpjs_settings_accounts.get(field)
            )
    
    def setup_account(self, field, description, account_type, parent, existing_account=None):
        """
        Setup an account for a specific field if missing
        
        Args:
            field (str): Field name to set
            description (str): Account description
            account_type (str): Account type
            parent (str): Parent account name
            existing_account (str, optional): Existing account name from BPJS Settings
        """
        # Skip if already set
        if self.get(field):
            return
        
        # Use existing account from BPJS Settings if available
        if existing_account:
            self.set(field, existing_account)
            return
        
        # Create new account if needed using standardized function from setup.py
        account_name = create_account(
            company=self.company,
            account_name=description,
            account_type=account_type,
            parent=parent
        )
        
        if account_name:
            self.set(field, account_name)
    
    def get_accounts_from_bpjs_settings(self):
        """
        Get already created accounts from BPJS Settings
        
        Returns:
            dict: Dictionary of account fields and values
        """
        accounts = {}
        
        # Try to get BPJS Settings
        try:
            bpjs_settings = frappe.get_cached_doc("BPJS Settings")
            
            # Map from BPJS Settings to Account Mapping fields
            field_mappings = {
                "kesehatan_account": ["kesehatan_employee_account", "kesehatan_employer_credit_account"],
                "jht_account": ["jht_employee_account", "jht_employer_credit_account"],
                "jp_account": ["jp_employee_account", "jp_employer_credit_account"],
                "jkk_account": ["jkk_employer_credit_account"],
                "jkm_account": ["jkm_employer_credit_account"]
            }
            
            for settings_field, mapping_fields in field_mappings.items():
                if hasattr(bpjs_settings, settings_field) and bpjs_settings.get(settings_field):
                    for mapping_field in mapping_fields:
                        accounts[mapping_field] = bpjs_settings.get(settings_field)
        except Exception as e:
            frappe.log_error(f"Error getting accounts from BPJS Settings: {str(e)}", "BPJS Mapping Error")
        
        return accounts
    
    def create_parent_account(self, company, account_type):
        """
        Create or get parent account for BPJS accounts
        
        Args:
            company (str): Company name
            account_type (str): Account type (Liability or Expense)
            
        Returns:
            str: Account name if created or found, None otherwise
        """
        # Use the standardized function
        return create_parent_account_for_mapping(company, account_type)
    
    def get_accounts_for_component(self, component_type):
        """
        Get the accounts to use for a specific BPJS component
        
        Args:
            component_type (str): One of 'kesehatan', 'jht', 'jp', 'jkk', 'jkm'
            
        Returns:
            dict: Dictionary with employee_account, employer_debit, employer_credit keys
        """
        accounts = {
            "employee_account": None,
            "employer_debit": None,
            "employer_credit": None
        }
        
        # Set employee account
        employee_field = f"{component_type}_employee_account"
        if hasattr(self, employee_field):
            accounts["employee_account"] = getattr(self, employee_field)
            
        # Set employer debit (expense) account
        employer_debit_field = f"{component_type}_employer_debit_account"
        if hasattr(self, employer_debit_field):
            accounts["employer_debit"] = getattr(self, employer_debit_field)
            
        # Set employer credit (liability) account
        employer_credit_field = f"{component_type}_employer_credit_account"
        if hasattr(self, employer_credit_field):
            accounts["employer_credit"] = getattr(self, employer_credit_field)
            
        return accounts
    
    def on_update(self):
        """Refresh cache and perform additional operations after update"""
        frappe.cache().delete_value(f"bpjs_mapping_{self.company}")
        debug_log(f"Cleared cache for BPJS mapping of company {self.company}", "BPJS Mapping Update")