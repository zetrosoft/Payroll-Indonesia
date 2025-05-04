# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-04 00:35:10 by dannyaudian

from __future__ import unicode_literals
import frappe
import os
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime
from payroll_indonesia.fixtures.setup import find_parent_account

# MODULE LEVEL FUNCTIONS - Used by hooks.py
def validate(doc, method=None):
    """Module level validation function for hooks"""
    if getattr(doc, "flags", {}).get("ignore_validate"):
        return
        
    doc.validate_data_types()
    doc.validate_percentages() 
    doc.validate_max_salary()
    doc.validate_account_types()

def setup_accounts(doc):
    """Module level setup_accounts called by hooks"""
    if not doc:
        return
    doc.setup_accounts()
    
def on_update(doc):
    """Module level on_update called by hooks"""
    if not doc:
        return
    try:
        doc.update_salary_structures()
        doc.ensure_bpjs_mapping_for_all_companies()
    except Exception as e:
        frappe.log_error(str(e)[:100], "BPJS Settings On Update Error")

# HELPER FUNCTIONS
def create_account(company, account_name, account_type, parent):
    """
    Create GL Account if not exists
    
    This function is standardized with the one in setup.py to ensure consistency
    
    Args:
        company: Company name
        account_name: Account name without company abbreviation
        account_type: Account type (Payable, Receivable, etc.)
        parent: Parent account name
        
    Returns:
        str: Full account name if created or already exists, None otherwise
    """
    try:
        abbr = frappe.get_cached_value('Company', company, 'abbr')
        pure_account_name = account_name.replace(f" - {abbr}", "")
        full_account_name = f"{pure_account_name} - {abbr}"
        
        # Skip if already exists
        if frappe.db.exists("Account", full_account_name):
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
        return full_account_name
        
    except Exception as e:
        frappe.log_error(str(e)[:100], "BPJS Account Creation Error")
        return None

def retry_bpjs_mapping(companies):
    """
    Background job to retry failed BPJS mapping creation
    Called via frappe.enqueue() from ensure_bpjs_mapping_for_all_companies
    
    Args:
        companies: List of company names to retry mapping for
    """
    if not companies:
        return
        
    try:
        from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import create_default_mapping
        
        for company in companies:
            if not frappe.db.exists("BPJS Account Mapping", {"company": company}):
                mapping_name = create_default_mapping(company)
                if mapping_name:
                    frappe.logger().info(_(f"Successfully created BPJS Account Mapping for {company} on retry"))
                else:
                    frappe.logger().warning(_(f"Failed again to create BPJS Account Mapping for {company}"))
    except Exception as e:
        frappe.log_error(str(e)[:100], "BPJS Mapping Retry Error")

def debug_log(message, title=None, max_length=500, trace=False):
    """
    Debug logging helper with consistent format
    
    Args:
        message: Message to log
        title: Optional title/context for the log
        max_length: Maximum message length (default: 500)
        trace: Whether to include traceback (default: False)
    """
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    
    if os.environ.get("DEBUG_BPJS"):
        # Truncate if message is too long to avoid memory issues
        message = str(message)[:max_length]
        
        if title:
            log_message = f"[{timestamp}] [{title}] {message}"
        else:
            log_message = f"[{timestamp}] {message}"
            
        frappe.logger().debug(f"[BPJS DEBUG] {log_message}")

def create_parent_account(company):
    """
    Create or get parent account for BPJS accounts
    
    Args:
        company: Company name
        
    Returns:
        str: Parent account name if created or already exists, None otherwise
    """
    try:
        abbr = frappe.get_cached_value('Company', company, 'abbr')
        parent_account = f"Duties and Taxes - {abbr}"
        parent_name = f"BPJS Payable - {abbr}"
        
        # Skip if already exists
        if frappe.db.exists("Account", parent_name):
            return parent_name
            
        # Create parent account
        frappe.get_doc({
            "doctype": "Account",
            "account_name": "BPJS Payable",
            "parent_account": parent_account,
            "company": company,
            "account_type": "Payable",
            "account_currency": frappe.get_cached_value('Company', company, 'default_currency'),
            "is_group": 1
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        
        return parent_name
    except Exception as e:
        frappe.log_error(f"Error creating parent account for {company}: {str(e)[:100]}", "BPJS Account Creation Error")
        return None

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
                frappe.throw(f"Nilai {field} harus berupa angka")
    
    def validate_percentages(self):
        """Validate BPJS percentage ranges"""
        validations = [
            ("kesehatan_employee_percent", 0, 5, "Persentase BPJS Kesehatan karyawan harus antara 0 dan 5%"),
            ("kesehatan_employer_percent", 0, 10, "Persentase BPJS Kesehatan perusahaan harus antara 0 dan 10%"),
            ("jht_employee_percent", 0, 5, "Persentase JHT karyawan harus antara 0 dan 5%"),
            ("jht_employer_percent", 0, 10, "Persentase JHT perusahaan harus antara 0 dan 10%"),
            ("jp_employee_percent", 0, 5, "Persentase JP karyawan harus antara 0 dan 5%"),
            ("jp_employer_percent", 0, 5, "Persentase JP perusahaan harus antara 0 dan 5%"),
            ("jkk_percent", 0, 5, "Persentase JKK harus antara 0 dan 5%"),
            ("jkm_percent", 0, 5, "Persentase JKM harus antara 0 dan 5%")
        ]
        
        for field, min_val, max_val, message in validations:
            value = flt(self.get(field))
            if value < min_val or value > max_val:
                frappe.throw(message)
    
    def validate_max_salary(self):
        """Validate maximum salary thresholds"""
        if flt(self.kesehatan_max_salary) <= 0:
            frappe.throw("Batas maksimal gaji BPJS Kesehatan harus lebih dari 0")
            
        if flt(self.jp_max_salary) <= 0:
            frappe.throw("Batas maksimal gaji JP harus lebih dari 0")
    
    def validate_account_types(self):
        """Validate that BPJS accounts are of the correct type"""
        account_fields = ["kesehatan_account", "jht_account", "jp_account", "jkk_account", "jkm_account"]
        
        for field in account_fields:
            account = self.get(field)
            if account:
                account_type = frappe.db.get_value("Account", account, "account_type")
                if account_type != "Payable":
                    frappe.throw(f"Akun {account} harus bertipe 'Payable'")
    
    def setup_accounts(self):
        """Setup GL accounts for BPJS components for all companies"""
        debug_log("Starting setup_accounts method")
        
        try:
            # Get companies to process
            default_company = frappe.defaults.get_defaults().get("company")
            if not default_company:
                companies = frappe.get_all("Company", pluck="name")
                if not companies:
                    frappe.msgprint("No company found. Please create a company before setting up BPJS accounts.")
                    return
            else:
                companies = [default_company]
        
            debug_log(f"Setting up accounts for companies: {companies}")
            
            # Loop through companies and create accounts
            for company in companies:
                try:
                    # Parent account where BPJS accounts will be created
                    parent_name = create_parent_account(company)
                    if not parent_name:
                        frappe.logger().warning(f"Failed to create parent account for {company}")
                        continue
                        
                    debug_log(f"Created/verified parent account: {parent_name}", f"Company: {company}")
                
                    # Define BPJS accounts to be created
                    bpjs_accounts = {
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
                
                    # Create accounts and update settings
                    for key, account_info in bpjs_accounts.items():
                        account = self.get(account_info["field"])
                        if not account:
                            account = create_account(
                                company=company,
                                account_name=account_info["account_name"],
                                account_type=account_info["account_type"],
                                parent=parent_name
                            )
                            if account:
                                self.set(account_info["field"], account)
                                debug_log(f"Set {account_info['field']} to {account}")
                
                    # Create BPJS mapping
                    self._create_bpjs_mapping(company)
                
                except Exception as e:
                    frappe.log_error(f"Error setting up BPJS accounts for company {company}: {str(e)[:100]}", "BPJS Setup Error")
                    debug_log(f"Error: {str(e)}", f"setup_accounts for {company}")
                    continue
                    
        except Exception as e:
            frappe.log_error(f"Error in setup_accounts: {str(e)[:100]}", "BPJS Setup Error")
    
    def _create_bpjs_mapping(self, company):
        """
        Create BPJS mapping for company
        
        Args:
            company: Company name
            
        Returns:
            str: Mapping name if created, None otherwise
        """
        try:
            # Skip if mapping already exists
            if frappe.db.exists("BPJS Account Mapping", {"company": company}):
                return None
                
            # Import create_default_mapping function
            try:
                from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import create_default_mapping
                mapping_name = create_default_mapping(company)
                if mapping_name:
                    debug_log(f"Created BPJS mapping: {mapping_name}", f"Company: {company}")
                    return mapping_name
            except ImportError:
                frappe.logger().warning("Could not import create_default_mapping, skipping mapping creation")
            except Exception as e:
                frappe.log_error(f"Error creating mapping for {company}: {str(e)[:100]}", "BPJS Mapping Error")
                
            return None
        except Exception as e:
            frappe.log_error(f"Error in _create_bpjs_mapping for {company}: {str(e)[:100]}", "BPJS Mapping Error")
            return None
    
    def on_update(self):
        """Update related documents when settings change"""
        debug_log("Starting on_update processing")
        
        try:
            # Update salary structure assignments if needed
            self.update_salary_structures()
        
            # Ensure all companies have BPJS mapping
            self.ensure_bpjs_mapping_for_all_companies()
        except Exception as e:
            frappe.log_error(f"Error in on_update: {str(e)[:100]}", "BPJS Settings Update Error")

    def update_salary_structures(self):
        """Update BPJS components in active salary structures"""
        try:
            debug_log("Starting update_salary_structures method")
            
            # Find active salary structures
            salary_structures = frappe.get_all(
                "Salary Structure",
                filters={"docstatus": 1, "is_active": "Yes"},
                pluck="name"
            )
            
            if not salary_structures:
                debug_log("No active salary structures found")
                return
                
            # Log for debug
            frappe.logger().info(f"Updating {len(salary_structures)} active salary structures with BPJS settings")
            
            # Get list of BPJS components to update
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
                    debug_log(f"Processing salary structure: {ss_name}")
                    
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
                                    debug_log(f"Component {component_name} uses custom formula, skipping")
                                    continue
                                
                                # Update rate if needed
                                debug_log(f"Updating {component_name} in earnings from {detail.amount} to {percent}")
                                detail.amount = percent
                                changes_made = True
                                break
                                
                        if not found:
                            # Check in deductions
                            for detail in ss.deductions:
                                if detail.salary_component == component_name:
                                    found = True
                                    if detail.amount_based_on_formula and detail.formula:
                                        debug_log(f"Component {component_name} uses custom formula, skipping")
                                        continue
                                    
                                    # Update rate if needed
                                    debug_log(f"Updating {component_name} in deductions from {detail.amount} to {percent}")
                                    detail.amount = percent
                                    changes_made = True
                                    break
                        
                        if not found:
                            missing_components.append(component_name)
                    
                    # Log warning about missing components
                    if missing_components:
                        frappe.logger().warning(
                            f"Salary Structure {ss_name} missing BPJS components: {', '.join(missing_components)[:100]}"
                        )
                    
                    # Save if changes were made
                    if changes_made:
                        ss.flags.ignore_validate = True
                        ss.flags.ignore_mandatory = True
                        ss.save(ignore_permissions=True)
                        updated_count += 1
                        debug_log(f"Saved changes to {ss_name}")
                        
                except Exception as e:
                    frappe.log_error(f"Error updating salary structure {ss_name}: {str(e)[:100]}", "BPJS Update Error")
                    debug_log(f"Error updating {ss_name}: {str(e)}")
                    continue
            
            if updated_count > 0:
                frappe.logger().info(f"Updated {updated_count} salary structures with new BPJS rates")
                debug_log(f"Successfully updated {updated_count} salary structures")
                
        except Exception as e:
            frappe.log_error(f"Error in update_salary_structures: {str(e)[:100]}", "BPJS Settings Update Error")
            debug_log(f"Critical error in update_salary_structures: {str(e)}")

    def ensure_bpjs_mapping_for_all_companies(self):
        """Ensure all companies have BPJS mapping"""
        try:
            debug_log("Starting ensure_bpjs_mapping_for_all_companies method")
            companies = frappe.get_all("Company", pluck="name")
            failed_companies = []
        
            for company in companies:
                # Check if mapping exists
                mapping_exists = frappe.db.exists("BPJS Account Mapping", {"company": company})
                debug_log(f"Company {company} mapping exists: {mapping_exists}")
            
                if not mapping_exists:
                    mapping_name = self._create_bpjs_mapping(company)
                    if not mapping_name:
                        failed_companies.append(company)
    
            # Schedule retry for failed companies
            if failed_companies:
                debug_log(f"Scheduling retry for failed companies: {failed_companies}")
                try:
                    frappe.enqueue(
                        method="payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.bpjs_settings.retry_bpjs_mapping",
                        companies=failed_companies,
                        queue="long",
                        timeout=1500
                    )
                except Exception as e:
                    frappe.log_error(f"Failed to schedule retry for BPJS mapping: {str(e)[:100]}", "BPJS Mapping Error")
                
        except Exception as e:
            frappe.log_error(f"Error ensuring BPJS mapping for all companies: {str(e)[:100]}", "BPJS Settings Update Error")
            debug_log(f"Critical error in ensure_bpjs_mapping_for_all_companies: {str(e)}")

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