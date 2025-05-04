# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-04 02:54:09 by dannyaudian

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
        abbr = frappe.get_cached_value('Company', company, 'abbr')
        pure_account_name = account_name.replace(f" - {abbr}", "")
        full_account_name = f"{pure_account_name} - {abbr}"
        
        # Skip if already exists
        if frappe.db.exists("Account", full_account_name):
            debug_log(f"Account {full_account_name} already exists", "Account Creation")
            return full_account_name
            
        # Create new account
        doc = frappe.get_doc({
            "doctype": "Account",
            "account_name": pure_account_name,
            "company": company,
            "parent_account": parent,
            "account_type": account_type,
            "account_currency": frappe.get_cached_value('Company', company, 'default_currency'),
            "is_group": 0
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        frappe.msgprint(_(f"Created account: {full_account_name}"))
        debug_log(f"Created account: {full_account_name}", "Account Creation")
        return full_account_name
        
    except Exception as e:
        frappe.log_error(f"Error creating account {account_name}: {str(e)}", "BPJS Account Creation Error")
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
        abbr = frappe.get_cached_value('Company', company, 'abbr')
        parent_name = f"BPJS Payable - {abbr}"
        
        # Skip if already exists
        if frappe.db.exists("Account", parent_name):
            return parent_name
            
        # Find a suitable parent account
        parent_candidates = [
            f"Duties and Taxes - {abbr}",
            f"Accounts Payable - {abbr}",
            f"Current Liabilities - {abbr}"
        ]
        
        parent_account = None
        for candidate in parent_candidates:
            if frappe.db.exists("Account", candidate):
                parent_account = candidate
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
            else:
                frappe.msgprint(_("No suitable liability parent account found for creating BPJS accounts."))
                return None
            
        # Create parent account
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
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        debug_log(f"Created parent liability account: {parent_name}", "Account Creation")
        return parent_name
    except Exception as e:
        frappe.log_error(f"Error creating parent liability account for {company}: {str(e)}", "BPJS Account Creation Error")
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
        abbr = frappe.get_cached_value('Company', company, 'abbr')
        parent_name = f"BPJS Expenses - {abbr}"
        
        # Skip if already exists
        if frappe.db.exists("Account", parent_name):
            return parent_name
            
        # Find a suitable parent account
        parent_candidates = [
            f"Direct Expenses - {abbr}",
            f"Indirect Expenses - {abbr}",
            f"Expenses - {abbr}"
        ]
        
        parent_account = None
        for candidate in parent_candidates:
            if frappe.db.exists("Account", candidate):
                parent_account = candidate
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
            else:
                frappe.msgprint(_("No suitable expense parent account found for creating BPJS accounts."))
                return None
            
        # Create parent account
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
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        debug_log(f"Created parent expense account: {parent_name}", "Account Creation")
        return parent_name
    except Exception as e:
        frappe.log_error(f"Error creating parent expense account for {company}: {str(e)}", "BPJS Account Creation Error")
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
            if not frappe.db.exists("BPJS Account Mapping", {"company": company}):
                mapping_name = create_default_mapping(company)
                if mapping_name:
                    frappe.logger().info(f"Successfully created BPJS Account Mapping for {company} on retry")
                    debug_log(f"Successfully created BPJS Account Mapping for {company} on retry", "BPJS Mapping Retry")
                else:
                    frappe.logger().warning(f"Failed again to create BPJS Account Mapping for {company}")
                    debug_log(f"Failed again to create BPJS Account Mapping for {company}", "BPJS Mapping Retry Error")
    except Exception as e:
        frappe.log_error(f"Error in retry_bpjs_mapping: {str(e)}", "BPJS Mapping Retry Error")

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
                account_type = frappe.db.get_value("Account", account, "account_type")
                root_type = frappe.db.get_value("Account", account, "root_type")
                
                if root_type != "Liability" or (account_type != "Payable" and account_type != "Liability"):
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
        
            debug_log(f"Setting up accounts for companies: {companies}", "BPJS Setup")
            
            # Loop through companies and create accounts
            for company in companies:
                try:
                    # Create parent accounts first
                    liability_parent = create_parent_liability_account(company)
                    if not liability_parent:
                        frappe.logger().warning(f"Failed to create parent liability account for {company}")
                        continue
                    
                    expense_parent = create_parent_expense_account(company)
                    if not expense_parent:
                        frappe.logger().warning(f"Failed to create parent expense account for {company}")
                        
                    debug_log(f"Created/verified parent accounts for {company}:", "BPJS Setup")
                    debug_log(f"  - Liability parent: {liability_parent}", "BPJS Setup")
                    debug_log(f"  - Expense parent: {expense_parent}", "BPJS Setup")
                
                    # Define BPJS liability accounts to be created with standardized names
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
                    for key, account_info in bpjs_liability_accounts.items():
                        account = self.get(account_info["field"])
                        if not account:
                            account = create_account(
                                company=company,
                                account_name=account_info["account_name"],
                                account_type=account_info["account_type"],
                                parent=liability_parent
                            )
                            if account:
                                self.set(account_info["field"], account)
                                debug_log(f"Set {account_info['field']} to {account}", "BPJS Setup")
                
                    # Define BPJS expense accounts with standardized names
                    if expense_parent:
                        bpjs_expense_accounts = {
                            "kesehatan_employer_expense": "BPJS Kesehatan Employer Expense",
                            "jht_employer_expense": "BPJS JHT Employer Expense",
                            "jp_employer_expense": "BPJS JP Employer Expense",
                            "jkk_employer_expense": "BPJS JKK Employer Expense",
                            "jkm_employer_expense": "BPJS JKM Employer Expense"
                        }
                        
                        # Create expense accounts (these won't be stored in BPJS Settings but in the mapping)
                        for field, account_name in bpjs_expense_accounts.items():
                            create_account(
                                company=company,
                                account_name=account_name,
                                account_type="Expense",
                                parent=expense_parent
                            )
                
                    # Create BPJS mapping
                    mapping_result = self._create_bpjs_mapping(company)
                    debug_log(f"BPJS mapping creation result: {mapping_result}", "BPJS Setup")
                
                except Exception as e:
                    frappe.log_error(
                        f"Error setting up BPJS accounts for company {company}: {str(e)}\n\n"
                        f"Traceback: {frappe.get_traceback()}", 
                        "BPJS Setup Error"
                    )
                    debug_log(f"Error setting up BPJS accounts for {company}: {str(e)}", "BPJS Setup Error", trace=True)
                    continue
                    
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
            # Skip if mapping already exists
            if frappe.db.exists("BPJS Account Mapping", {"company": company}):
                debug_log(f"BPJS Account Mapping already exists for {company}", "BPJS Mapping")
                return None
                
            # Import create_default_mapping function
            try:
                from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import create_default_mapping
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
        """Update BPJS components in active salary structures"""
        try:
            debug_log("Starting update_salary_structures method", "BPJS Settings")
            
            # Find active salary structures
            salary_structures = frappe.get_all(
                "Salary Structure",
                filters={"docstatus": 1, "is_active": "Yes"},
                pluck="name"
            )
            
            if not salary_structures:
                debug_log("No active salary structures found", "BPJS Settings")
                return
                
            # Log for debug
            debug_log(f"Updating {len(salary_structures)} active salary structures with BPJS settings", "BPJS Settings")
            
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
            
            # Update each salary structure
            updated_count = 0
            for ss_name in salary_structures:
                try:
                    ss = frappe.get_doc("Salary Structure", ss_name)
                    debug_log(f"Processing salary structure: {ss_name}", "BPJS Settings")
                    
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
                                    debug_log(f"Updating {component_name} in deductions from {detail.amount} to {percent}", "BPJS Settings")
                                    detail.amount = percent
                                    changes_made = True
                                    break
                        
                        if not found:
                            missing_components.append(component_name)
                    
                    # Log warning about missing components
                    if missing_components:
                        debug_log(f"Salary Structure {ss_name} missing BPJS components: {', '.join(missing_components)}", "BPJS Settings")
                    
                    # Save if changes were made
                    if changes_made:
                        ss.flags.ignore_validate = True
                        ss.flags.ignore_mandatory = True
                        ss.save(ignore_permissions=True)
                        updated_count += 1
                        debug_log(f"Saved changes to {ss_name}", "BPJS Settings")
                        
                except Exception as e:
                    frappe.log_error(
                        f"Error updating salary structure {ss_name}: {str(e)}\n\n"
                        f"Traceback: {frappe.get_traceback()}", 
                        "BPJS Update Error"
                    )
                    debug_log(f"Error updating {ss_name}: {str(e)}", "BPJS Settings", trace=True)
                    continue
            
            if updated_count > 0:
                debug_log(f"Successfully updated {updated_count} salary structures", "BPJS Settings")
                
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
                debug_log(f"Scheduling retry for failed companies: {failed_companies}", "BPJS Settings")
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