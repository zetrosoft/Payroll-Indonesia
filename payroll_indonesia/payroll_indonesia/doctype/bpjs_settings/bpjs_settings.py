# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-06 15:51:10 by dannyaudian

from __future__ import unicode_literals
import frappe
import os
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime

# Import utility functions from utils.py
from payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.utils import (
    get_default_config, debug_log, find_parent_account, create_account,
    create_parent_liability_account, create_parent_expense_account
)

__all__ = [
    'validate',
    'setup_accounts',
    'on_update',
    'retry_bpjs_mapping',
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
        # Call the class instance methods directly to avoid passing 'method' parameter
        if hasattr(doc, 'update_salary_structures'):
            doc.update_salary_structures()
        if hasattr(doc, 'ensure_bpjs_mapping_for_all_companies'):
            doc.ensure_bpjs_mapping_for_all_companies()
    except Exception as e:
        frappe.log_error(f"Error in on_update: {str(e)}\n\n{frappe.get_traceback()}", "BPJS Settings On Update Error")

def retry_bpjs_mapping(companies):
    """
    Wrapper for utility function that retries failed BPJS mapping creation
    
    Args:
        companies (list): List of company names to retry mapping for
    """
    from payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.utils import retry_bpjs_mapping as retry_mapping
    retry_mapping(companies)

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
        # Get numeric fields from config
        config = get_default_config()
        
        # Combine fields from percentage validations and salary thresholds
        numeric_fields = []
        validation_rules = config.get("bpjs_settings", {}).get("validation_rules", {})
        
        for rule in validation_rules.get("percentage_ranges", []):
            if "field" in rule and rule["field"] not in numeric_fields:
                numeric_fields.append(rule["field"])
                
        for rule in validation_rules.get("salary_thresholds", []):
            if "field" in rule and rule["field"] not in numeric_fields:
                numeric_fields.append(rule["field"])
        
        # Fallback to hardcoded fields if config not available
        if not numeric_fields:
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
        """Validate BPJS percentage ranges using config"""
        # Get validation rules from config
        config = get_default_config()
        validation_rules = config.get("bpjs_settings", {}).get("validation_rules", {})
        percentage_rules = validation_rules.get("percentage_ranges", [])
        
        if percentage_rules:
            # Use rules from config
            for rule in percentage_rules:
                field = rule.get("field")
                min_val = rule.get("min", 0)
                max_val = rule.get("max", 5)
                error_msg = rule.get("error_msg", f"{field} must be between {min_val}% and {max_val}%")
                
                if hasattr(self, field):
                    value = flt(self.get(field))
                    if value < min_val or value > max_val:
                        frappe.throw(_(error_msg))
        else:
            # Fallback to hardcoded validations
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
        """Validate maximum salary thresholds using config"""
        # Get validation rules from config
        config = get_default_config()
        validation_rules = config.get("bpjs_settings", {}).get("validation_rules", {})
        salary_rules = validation_rules.get("salary_thresholds", [])
        
        if salary_rules:
            # Use rules from config
            for rule in salary_rules:
                field = rule.get("field")
                min_val = rule.get("min", 0)
                error_msg = rule.get("error_msg", f"{field} must be greater than {min_val}")
                
                if hasattr(self, field):
                    value = flt(self.get(field))
                    if value <= min_val:
                        frappe.throw(_(error_msg))
        else:
            # Fallback to hardcoded validations
            if flt(self.kesehatan_max_salary) <= 0:
                frappe.throw(_("BPJS Kesehatan maximum salary must be greater than 0"))
                
            if flt(self.jp_max_salary) <= 0:
                frappe.throw(_("JP maximum salary must be greater than 0"))
    
    def validate_account_types(self):
        """Validate that BPJS accounts are of the correct type"""
        # Get account fields from config
        config = get_default_config()
        account_fields = config.get("bpjs_settings", {}).get("account_fields", [])
        
        # Fallback to hardcoded fields
        if not account_fields:
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
                    config = get_default_config()
                    bpjs_payable_accounts = config.get("gl_accounts", {}).get("bpjs_payable_accounts", {})
                    
                    # If no config found, use hardcoded accounts
                    if not bpjs_payable_accounts:
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
                    else:
                        # Build from config
                        bpjs_liability_accounts = {}
                        for key, account_info in bpjs_payable_accounts.items():
                            field_name = key.replace("payable", "account")
                            bpjs_liability_accounts[field_name] = {
                                "account_name": account_info.get("account_name"),
                                "account_type": "Payable",
                                "field": field_name
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
                
                    # Define expense accounts with standardized names from config
                    if expense_parent:
                        bpjs_expense_accounts = {}
                        expense_accounts_from_config = config.get("gl_accounts", {}).get("bpjs_expense_accounts", {})
                        
                        if expense_accounts_from_config:
                            for key, account_info in expense_accounts_from_config.items():
                                bpjs_expense_accounts[key] = account_info.get("account_name")
                        else:
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
                
                # Get account mapping config
                config = get_default_config()
                account_mapping = config.get("gl_accounts", {}).get("bpjs_account_mapping", {})
                
                debug_log(f"Creating new BPJS Account Mapping for {company}", "BPJS Mapping")
                mapping_name = create_default_mapping(company, account_mapping)
                
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
                f"Error in BPJSSettings.on_update: {str(e)}\n\n"
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
        
            # Get list of BPJS components to update from config
            config = get_default_config()
            bpjs_components_map = config.get("bpjs_settings", {}).get("bpjs_components", {})
            
            # Fallback to hardcoded mapping if not in config
            if not bpjs_components_map:
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
            else:
                # Build components from config mapping
                bpjs_components = {}
                for component_name, field_name in bpjs_components_map.items():
                    if hasattr(self, field_name):
                        bpjs_components[component_name] = self.get(field_name)
        
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
        # Get app info from config
        config = get_default_config()
        app_info = config.get("app_info", {"version": "1.0.0"})
        
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
        
        result = {
            "app_info": app_info,
            "export_date": now_datetime().strftime('%Y-%m-%d %H:%M:%S'),
            "export_user": frappe.session.user,
            "settings": {}
        }
        
        for field in fields_to_export:
            result["settings"][field] = flt(self.get(field))
            
        return result