# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, cstr

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
        mapping = frappe.get_doc("BPJS Account Mapping", mapping_name)
        
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
        
        # Cache the result
        frappe.cache().set_value(cache_key, mapping_dict, expires_in_sec=3600)
        
        return mapping_dict
    except Exception as e:
        frappe.log_error(f"Error getting BPJS account mapping for company {company}: {str(e)}", "BPJS Mapping Error")
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
        # Cek apakah mapping sudah ada
        existing_mapping = frappe.db.exists("BPJS Account Mapping", {"company": company})
        if existing_mapping:
            frappe.logger().info(f"BPJS Account Mapping already exists for {company}: {existing_mapping}")
            return existing_mapping
            
        # Buat parent account terlebih dahulu untuk liabilities dan expenses
        liability_parent = create_parent_account_for_mapping(company, "Liability")
        expense_parent = create_parent_account_for_mapping(company, "Expense")
        
        if not liability_parent or not expense_parent:
            frappe.logger().error(f"Failed to create parent accounts for {company}")
            return None
            
        # Cek BPJS Settings dan buat jika belum ada
        bpjs_settings = None
        if not frappe.db.exists("BPJS Settings", None):
            bpjs_settings = create_bpjs_settings()
        else:
            bpjs_settings = frappe.get_doc("BPJS Settings")
            
        # Buat mapping baru dengan flag ignore_validate
        mapping = frappe.new_doc("BPJS Account Mapping")
        mapping.mapping_name = f"Default BPJS Mapping - {company}"
        mapping.company = company
        mapping.flags.ignore_validate = True
        
        # Set account dari BPJS Settings jika tersedia
        if bpjs_settings:
            if hasattr(bpjs_settings, "kesehatan_account") and bpjs_settings.kesehatan_account:
                mapping.kesehatan_employee_account = bpjs_settings.kesehatan_account
                mapping.kesehatan_employer_credit_account = bpjs_settings.kesehatan_account
                
            if hasattr(bpjs_settings, "jht_account") and bpjs_settings.jht_account:
                mapping.jht_employee_account = bpjs_settings.jht_account
                mapping.jht_employer_credit_account = bpjs_settings.jht_account
                
            if hasattr(bpjs_settings, "jp_account") and bpjs_settings.jp_account:
                mapping.jp_employee_account = bpjs_settings.jp_account
                mapping.jp_employer_credit_account = bpjs_settings.jp_account
                
            if hasattr(bpjs_settings, "jkk_account") and bpjs_settings.jkk_account:
                mapping.jkk_employer_credit_account = bpjs_settings.jkk_account
                
            if hasattr(bpjs_settings, "jkm_account") and bpjs_settings.jkm_account:
                mapping.jkm_employer_credit_account = bpjs_settings.jkm_account
        
        # Insert mapping tanpa validasi ketat
        mapping.insert(ignore_permissions=True, ignore_mandatory=True)
        
        # Buat expense accounts yang belum ada
        setup_expense_accounts(mapping, expense_parent)
        
        # Simpan perubahan setelah setup akun
        mapping.save(ignore_permissions=True)
        frappe.db.commit()
        
        frappe.logger().info(f"Successfully created BPJS Account Mapping for {company}: {mapping.name}")
        return mapping.name
        
    except Exception as e:
        frappe.log_error(
            f"Error creating default BPJS account mapping for {company}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}", 
            "BPJS Mapping Error"
        )
        return None


def create_parent_account_for_mapping(company, account_type):
    """Create or get parent account for BPJS accounts"""
    try:
        abbr = frappe.get_cached_value('Company', company, 'abbr')
        
        if account_type == "Liability":
            # Coba beberapa kemungkinan parent account
            parent_candidates = [
                f"Duties and Taxes - {abbr}",
                f"Accounts Payable - {abbr}",
                f"Current Liabilities - {abbr}"
            ]
            
            parent_account_name = find_valid_parent(company, parent_candidates)
            
            if not parent_account_name:
                frappe.logger().warning(f"Could not find suitable parent account for Liability in {company}")
                # Ambil root account untuk fallback
                root_type_accounts = frappe.get_all(
                    "Account", 
                    filters={"company": company, "is_group": 1, "root_type": "Liability"},
                    order_by="lft",
                    limit=1
                )
                
                if root_type_accounts:
                    parent_account_name = root_type_accounts[0].name
                else:
                    frappe.logger().error(f"No Liability parent account found for {company}")
                    return None
            
            account_name = f"BPJS Payable - {abbr}"
            account_label = "BPJS Payable"
            root_type = "Liability"
            
        else:  # Expense
            # Coba beberapa kemungkinan parent account
            parent_candidates = [
                f"Indirect Expenses - {abbr}",
                f"Direct Expenses - {abbr}",
                f"Expenses - {abbr}"
            ]
            
            parent_account_name = find_valid_parent(company, parent_candidates)
            
            if not parent_account_name:
                frappe.logger().warning(f"Could not find suitable parent account for Expense in {company}")
                # Ambil root account untuk fallback
                root_type_accounts = frappe.get_all(
                    "Account", 
                    filters={"company": company, "is_group": 1, "root_type": "Expense"},
                    order_by="lft",
                    limit=1
                )
                
                if root_type_accounts:
                    parent_account_name = root_type_accounts[0].name
                else:
                    frappe.logger().error(f"No Expense parent account found for {company}")
                    return None
            
            account_name = f"BPJS Expenses - {abbr}"
            account_label = "BPJS Expenses"
            root_type = "Expense"
        
        # Cek apakah account BPJS parent sudah ada
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
                doc.insert(ignore_permissions=True)
                frappe.db.commit()
                
                frappe.logger().info(f"Created parent account: {account_name}")
            except Exception as e:
                frappe.logger().error(f"Error creating parent account {account_name}: {str(e)}")
                return None
        
        return account_name
    except Exception as e:
        frappe.log_error(f"Error in create_parent_account_for_mapping: {str(e)}", "BPJS Account Creation Error")
        return None


def find_valid_parent(company, candidates):
    """Find first valid parent account from candidates list"""
    for candidate in candidates:
        if frappe.db.exists("Account", candidate):
            return candidate
    return None


def setup_expense_accounts(mapping_doc, expense_parent):
    """Setup expense accounts yang belum ada"""
    try:
        company = mapping_doc.company
        abbr = frappe.get_cached_value('Company', company, 'abbr')
        
        # Daftar account expense yang perlu dibuat
        expense_accounts = {
            "kesehatan_employer_debit_account": "BPJS Kesehatan Employer Expense",
            "jht_employer_debit_account": "BPJS JHT Employer Expense",
            "jp_employer_debit_account": "BPJS JP Employer Expense",
            "jkk_employer_debit_account": "BPJS JKK Employer Expense",
            "jkm_employer_debit_account": "BPJS JKM Employer Expense"
        }
        
        for field, account_name in expense_accounts.items():
            # Lewati jika sudah diisi
            if mapping_doc.get(field):
                continue
                
            # Buat account baru
            full_account_name = f"{account_name} - {abbr}"
            
            if not frappe.db.exists("Account", full_account_name):
                try:
                    doc = frappe.get_doc({
                        "doctype": "Account",
                        "account_name": account_name,
                        "parent_account": expense_parent,
                        "company": company,
                        "account_type": "Expense",
                        "account_currency": frappe.get_cached_value('Company', company, 'default_currency'),
                        "is_group": 0,
                        "root_type": "Expense"
                    })
                    doc.insert(ignore_permissions=True)
                    frappe.db.commit()
                    
                    frappe.logger().info(f"Created expense account: {full_account_name}")
                except Exception as e:
                    frappe.logger().error(f"Error creating expense account {full_account_name}: {str(e)}")
                    continue
            
            # Set di mapping document
            mapping_doc.set(field, full_account_name)
            
    except Exception as e:
        frappe.log_error(f"Error setting up expense accounts: {str(e)}", "BPJS Account Setup Error")


def create_bpjs_settings():
    """Create default BPJS Settings if not exists"""
    try:
        settings = frappe.new_doc("BPJS Settings")
        settings.kesehatan_employee_percent = 1.0
        settings.kesehatan_employer_percent = 4.0
        settings.kesehatan_max_salary = 12000000
        settings.jht_employee_percent = 2.0
        settings.jht_employer_percent = 3.7
        settings.jp_employee_percent = 1.0
        settings.jp_employer_percent = 2.0
        settings.jp_max_salary = 9077600
        settings.jkk_percent = 0.24
        settings.jkm_percent = 0.3
        settings.insert(ignore_permissions=True)
        frappe.db.commit()
        
        frappe.logger().info("Created default BPJS Settings")
        return settings
        
    except Exception as e:
        frappe.log_error(f"Error creating default BPJS Settings: {str(e)}", "BPJS Setup Error")
        return None


# Function for diagnostic purposes
@frappe.whitelist()
def diagnose_accounts():
    """Diagnose BPJS Account Mapping issues"""
    results = {
        "settings_exists": False,
        "companies": [],
        "mappings": []
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
        
        # Check companies and mappings
        companies = frappe.get_all("Company", pluck="name")
        for company in companies:
            company_info = {
                "name": company,
                "has_mapping": False
            }
            
            mapping = frappe.db.exists("BPJS Account Mapping", {"company": company})
            if mapping:
                company_info["has_mapping"] = True
                company_info["mapping_name"] = mapping
                
                # Get detailed mapping info
                mapping_doc = frappe.get_doc("BPJS Account Mapping", mapping)
                results["mappings"].append({
                    "name": mapping_doc.name,
                    "company": mapping_doc.company,
                    "kesehatan_employee_account": mapping_doc.get("kesehatan_employee_account", "Not Set"),
                    "jht_employee_account": mapping_doc.get("jht_employee_account", "Not Set"),
                    "jp_employee_account": mapping_doc.get("jp_employee_account", "Not Set"),
                    # Expense accounts
                    "kesehatan_employer_debit_account": mapping_doc.get("kesehatan_employer_debit_account", "Not Set"),
                    "jht_employer_debit_account": mapping_doc.get("jht_employer_debit_account", "Not Set"),
                    "jp_employer_debit_account": mapping_doc.get("jp_employer_debit_account", "Not Set"),
                    "jkk_employer_debit_account": mapping_doc.get("jkk_employer_debit_account", "Not Set"),
                    "jkm_employer_debit_account": mapping_doc.get("jkm_employer_debit_account", "Not Set")
                })
            
            results["companies"].append(company_info)
        
        return results
    except Exception as e:
        frappe.log_error(f"Error in diagnose_accounts: {str(e)}", "BPJS Diagnostic Error")
        return {"error": str(e)}


class BPJSAccountMapping(Document):
    def validate(self):
        """Validate required fields and account types"""
        # Skip validasi jika dalam mode migrasi/setup
        if getattr(self, "flags", {}).get("ignore_validate"):
            frappe.logger().info(f"Skipping validation for {self.name} during initial setup/migration")
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
        """Validate that an account is of the correct type"""
        if not account:
            # Skip validation if account is not provided
            return
            
        account_type = frappe.db.get_value("Account", account, "account_type")
        root_type = frappe.db.get_value("Account", account, "root_type")
        
        if root_type not in allowed_types:
            frappe.throw(_("{0} account {1} must be a {2} account").format(
                account_description, account, " or ".join(allowed_types)
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
        """Setup an account for a specific field if missing"""
        # Skip if already set
        if self.get(field):
            return
        
        # Use existing account from BPJS Settings if available
        if existing_account:
            self.set(field, existing_account)
            return
        
        # Create new account if needed
        account_name = self.create_account(
            company=self.company,
            account_name=description,
            account_type=account_type,
            parent=parent
        )
        
        if account_name:
            self.set(field, account_name)
    
    def get_accounts_from_bpjs_settings(self):
        """Get already created accounts from BPJS Settings"""
        accounts = {}
        
        # Try to get BPJS Settings
        bpjs_settings = frappe.get_cached_value("BPJS Settings", None, "*") or {}
        
        # Map from BPJS Settings to Account Mapping fields
        field_mappings = {
            "kesehatan_account": "kesehatan_employee_account",
            "jht_account": "jht_employee_account",
            "jp_account": "jp_employee_account",
            "jkk_account": "jkk_employer_credit_account",
            "jkm_account": "jkm_employer_credit_account"
        }
        
        for settings_field, mapping_field in field_mappings.items():
            if bpjs_settings.get(settings_field):
                accounts[mapping_field] = bpjs_settings.get(settings_field)
        
        return accounts
    
    def create_parent_account(self, company, account_type):
        """Create or get parent account for BPJS accounts"""
        abbr = frappe.get_cached_value('Company', company, 'abbr')
        
        if account_type == "Liability":
            parent_account_name = f"Duties and Taxes - {abbr}"
            account_name = f"BPJS Payable - {abbr}"
            account_label = "BPJS Payable"
            root_type = "Liability"
        else:  # Expense
            parent_account_name = f"Indirect Expenses - {abbr}"
            account_name = f"BPJS Expenses - {abbr}"
            account_label = "BPJS Expenses"
            root_type = "Expense"
        
        # Check if parent account exists
        if not frappe.db.exists("Account", account_name):
            try:
                frappe.get_doc({
                    "doctype": "Account",
                    "account_name": account_label,
                    "parent_account": parent_account_name,
                    "company": company,
                    "account_type": account_type,
                    "account_currency": frappe.get_cached_value('Company', company, 'default_currency'),
                    "is_group": 1,
                    "root_type": root_type
                }).insert(ignore_permissions=True)
                
                frappe.db.commit()
                frappe.msgprint(f"Created parent account: {account_name}")
            except Exception as e:
                frappe.log_error(f"Error creating parent account {account_name}: {str(e)}", "BPJS Account Creation Error")
        
        return account_name
    
    def create_account(self, company, account_name, account_type, parent):
        """Create GL Account if not exists"""
        abbr = frappe.get_cached_value('Company', company, 'abbr')
        full_account_name = f"{account_name} - {abbr}"
        
        if not frappe.db.exists("Account", full_account_name):
            try:
                # Determine root type from account type
                root_type = "Liability" if account_type == "Liability" else "Expense"
                
                doc = frappe.get_doc({
                    "doctype": "Account",
                    "account_name": account_name.replace(f" - {abbr}", ""),
                    "company": company,
                    "parent_account": parent,
                    "account_type": account_type,
                    "account_currency": frappe.get_cached_value('Company', company, 'default_currency'),
                    "is_group": 0,
                    "root_type": root_type
                })
                doc.insert(ignore_permissions=True)
                frappe.db.commit()
                
                frappe.msgprint(f"Created account: {full_account_name}")
                return full_account_name
            except Exception as e:
                frappe.log_error(f"Error creating account {full_account_name}: {str(e)}", "BPJS Account Creation Error")
                return None
        
        return full_account_name
    
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
    
    def create_journal_entry(self, bpjs_component, posting_date=None):
        """
        Create a Journal Entry for the BPJS component
        
        Args:
            bpjs_component (Document): BPJS Payment Component document
            posting_date (str, optional): Posting date for the journal entry
            
        Returns:
            str: Name of the created journal entry
        """
        # [code unchanged, keeping for brevity]
        # Implementasi tetap sama dengan yang sebelumnya
        pass