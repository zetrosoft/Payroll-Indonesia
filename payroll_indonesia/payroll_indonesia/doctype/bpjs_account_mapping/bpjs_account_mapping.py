# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

# Import from centralized utils module
from payroll_indonesia.payroll_indonesia.utils import (
    get_default_config,
    debug_log,
    create_account,
    create_parent_liability_account,
    create_parent_expense_account,
)

# Import the map_gl_account function
from payroll_indonesia.config.gl_account_mapper import map_gl_account

__all__ = [
    "BPJSAccountMapping",
    "get_mapping_for_company",
    "create_default_mapping",
    "create_parent_account_for_mapping",
    "find_valid_parent",
    "setup_expense_accounts",
    "create_bpjs_settings",
    "diagnose_accounts",
    "validate",
    "on_update_mapping",
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
        mapping_name = frappe.db.get_value("BPJS Account Mapping", {"company": company}, "name")

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
            "jkm_employer_credit_account": mapping.jkm_employer_credit_account,
        }

        # Cache the result with appropriate TTL
        frappe.cache().set_value(cache_key, mapping_dict, expires_in_sec=3600)

        return mapping_dict
    except Exception as e:
        frappe.log_error(
            f"Error getting BPJS account mapping for company {company}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Mapping Error",
        )
        return None


@frappe.whitelist()
def create_default_mapping(company):
    """
    Create a default BPJS Account Mapping using map_gl_account from config
    
    Args:
        company (str): Company name

    Returns:
        str: Name of created mapping or None if failed
    """
    try:
        # Verify company is valid
        if not frappe.db.exists("Company", company):
            frappe.throw(_("Company {0} does not exist").format(company))

        # Check if mapping already exists
        existing_mapping = frappe.db.exists("BPJS Account Mapping", {"company": company})
        if existing_mapping:
            debug_log(
                f"BPJS Account Mapping already exists for {company}: {existing_mapping}",
                "BPJS Mapping",
            )
            return existing_mapping

        # Create parent accounts first for liabilities and expenses
        debug_log(f"Creating liability parent account for company {company}", "BPJS Mapping")
        liability_parent = create_parent_liability_account(company)
        if not liability_parent:
            error_msg = f"Failed to create BPJS Payable parent account for company {company}"
            debug_log(error_msg, "BPJS Mapping Error", trace=True)
            frappe.throw(_(error_msg))

        debug_log(f"Creating expense parent account for company {company}", "BPJS Mapping")
        expense_parent = create_parent_expense_account(company)
        if not expense_parent:
            error_msg = f"Failed to create BPJS Expenses parent account for company {company}"
            debug_log(error_msg, "BPJS Mapping Error", trace=True)
            frappe.throw(_(error_msg))

        # Create new mapping with ignore_validate flag
        debug_log(f"Creating new BPJS Account Mapping for company {company}", "BPJS Mapping")
        mapping = frappe.new_doc("BPJS Account Mapping")
        mapping.mapping_name = f"Default BPJS Mapping - {company}"
        mapping.company = company
        mapping.flags.ignore_validate = True

        # Define mapping between document fields and GL account keys and categories
        account_mapping_fields = {
            "kesehatan_employee_account": ("bpjs_kesehatan_payable", "bpjs_payable_accounts"),
            "kesehatan_employer_credit_account": ("bpjs_kesehatan_payable", "bpjs_payable_accounts"),
            "jht_employee_account": ("bpjs_jht_payable", "bpjs_payable_accounts"),
            "jht_employer_credit_account": ("bpjs_jht_payable", "bpjs_payable_accounts"),
            "jp_employee_account": ("bpjs_jp_payable", "bpjs_payable_accounts"),
            "jp_employer_credit_account": ("bpjs_jp_payable", "bpjs_payable_accounts"),
            "jkk_employer_credit_account": ("bpjs_jkk_payable", "bpjs_payable_accounts"),
            "jkm_employer_credit_account": ("bpjs_jkm_payable", "bpjs_payable_accounts"),
            "kesehatan_employer_debit_account": ("bpjs_kesehatan_employer_expense", "bpjs_expense_accounts"),
            "jht_employer_debit_account": ("bpjs_jht_employer_expense", "bpjs_expense_accounts"),
            "jp_employer_debit_account": ("bpjs_jp_employer_expense", "bpjs_expense_accounts"),
            "jkk_employer_debit_account": ("bpjs_jkk_employer_expense", "bpjs_expense_accounts"),
            "jkm_employer_debit_account": ("bpjs_jkm_employer_expense", "bpjs_expense_accounts")
        }
            
        # Map each account using the GL mapper function
        for field_name, (account_key, category) in account_mapping_fields.items():
            account = map_gl_account(company, account_key, category)
            if account and frappe.db.exists("Account", account):
                mapping.set(field_name, account)
                debug_log(
                    f"Set {field_name} to {account} using map_gl_account",
                    "BPJS Mapping"
                )
            else:
                debug_log(
                    f"Failed to map account for {field_name} using key {account_key} in category {category}",
                    "BPJS Mapping Warning"
                )

        # Insert mapping without strict validation
        try:
            debug_log(
                f"Attempting to insert BPJS Account Mapping document for {company}",
                "BPJS Mapping"
            )
            mapping.insert(ignore_permissions=True, ignore_mandatory=True)
        except Exception as e:
            frappe.db.rollback()
            error_msg = f"Failed to insert BPJS Account Mapping for {company}: {str(e)}"
            debug_log(error_msg, "BPJS Mapping Error", trace=True)
            frappe.log_error(
                f"{error_msg}\n\nTraceback: {frappe.get_traceback()}",
                "BPJS Mapping Creation Error"
            )
            frappe.throw(_(error_msg))

        # Try to fill in any missing accounts
        try:
            # Create any missing expense accounts if needed
            missing_fields = []
            for field_name, (account_key, category) in account_mapping_fields.items():
                if not mapping.get(field_name):
                    missing_fields.append(field_name)
                    
            if missing_fields:
                debug_log(
                    f"Missing accounts for fields: {', '.join(missing_fields)}. Setting up expense accounts.",
                    "BPJS Mapping"
                )
                setup_expense_accounts(mapping, expense_parent)
        except Exception as e:
            debug_log(
                f"Error in setup_expense_accounts: {str(e)}",
                "BPJS Mapping Error",
                trace=True
            )
            # Don't throw here, try to save what we have

        # Save changes after account setup
        try:
            mapping.save(ignore_permissions=True)
            frappe.db.commit()

            # Clear cache for the company
            frappe.cache().delete_value(f"bpjs_mapping_{company}")

            debug_log(
                f"Successfully created BPJS Account Mapping for {company}: {mapping.name}",
                "BPJS Mapping"
            )
            return mapping.name
        except Exception as e:
            frappe.db.rollback()
            error_msg = f"Failed to save BPJS Account Mapping for {company}: {str(e)}"
            debug_log(error_msg, "BPJS Mapping Error", trace=True)
            frappe.log_error(
                f"{error_msg}\n\nTraceback: {frappe.get_traceback()}",
                "BPJS Mapping Creation Error"
            )
            frappe.throw(_(error_msg))

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            f"Error creating default BPJS account mapping for {company}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Mapping Error",
        )
        debug_log(
            f"Critical error in create_default_mapping: {str(e)}",
            "BPJS Mapping Error",
            trace=True
        )
        # Re-raise with a clear message
        frappe.throw(
            _("Could not create BPJS Account Mapping for {0}: {1}").format(company, str(e)[:100])
        )
        return None


def create_parent_account_for_mapping(company, account_type):
    """
    Create or get parent account for BPJS accounts using the centralized utility functions

    Args:
        company (str): Company name
        account_type (str): Account type (Liability or Expense)

    Returns:
        str: Account name if created or found, None otherwise
    """
    try:
        if account_type == "Liability":
            return create_parent_liability_account(company)
        elif account_type == "Expense":
            return create_parent_expense_account(company)
        else:
            frappe.throw(
                _("Invalid account type: {0}. Must be 'Liability' or 'Expense'").format(
                    account_type
                )
            )
            return None
    except Exception as e:
        frappe.log_error(
            f"Error in create_parent_account_for_mapping for {company}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Account Creation Error",
        )
        debug_log(
            f"Error in create_parent_account_for_mapping for {company}: {str(e)}",
            "BPJS Account Creation Error",
            trace=True,
        )
        return None


def find_valid_parent(company, candidates):
    """
    Find first valid parent account from candidates list with improved diagnostics

    Args:
        company (str): Company name
        candidates (list): List of potential parent account names

    Returns:
        str: First valid parent account name or None if none found
    """
    if not candidates:
        debug_log("No parent candidates provided", "Account Lookup")
        return None

    # Log all candidates for debugging
    debug_log(f"Searching for parent accounts among: {', '.join(candidates)}", "Account Lookup")

    # Try exact matches
    for candidate in candidates:
        if frappe.db.exists("Account", candidate):
            debug_log(f"Found parent account: {candidate}", "Account Lookup")
            return candidate

    # If no exact match, try without company suffix
    company_data = frappe.get_doc("Company", company)
    if company_data and company_data.abbr:
        abbr = company_data.abbr
        for candidate in candidates:
            # Try matching just the account name without the company suffix
            base_name = candidate
            if f" - {abbr}" in candidate:
                base_name = candidate.replace(f" - {abbr}", "")

            matches = frappe.get_all(
                "Account", filters={"account_name": base_name, "company": company}, fields=["name"]
            )

            if matches:
                debug_log(
                    f"Found parent account by name match: {matches[0].name}", "Account Lookup"
                )
                return matches[0].name

    # No valid parent found
    debug_log(
        f"No valid parent account found among candidates for company {company}",
        "Account Lookup Error",
    )
    return None


def setup_expense_accounts(mapping_doc, expense_parent):
    """Setup expense accounts that don't already exist using map_gl_account"""
    try:
        company = mapping_doc.company
        
        # Define account field mappings with their corresponding GL account keys
        expense_account_fields = {
            "kesehatan_employer_debit_account": ("bpjs_kesehatan_employer_expense", "bpjs_expense_accounts"),
            "jht_employer_debit_account": ("bpjs_jht_employer_expense", "bpjs_expense_accounts"),
            "jp_employer_debit_account": ("bpjs_jp_employer_expense", "bpjs_expense_accounts"),
            "jkk_employer_debit_account": ("bpjs_jkk_employer_expense", "bpjs_expense_accounts"),
            "jkm_employer_debit_account": ("bpjs_jkm_employer_expense", "bpjs_expense_accounts"),
        }

        for field, (account_key, category) in expense_account_fields.items():
            # Skip if already filled
            if mapping_doc.get(field):
                continue
                
            # Try to map the account using map_gl_account
            try:
                account = map_gl_account(company, account_key, category)
                if account and frappe.db.exists("Account", account):
                    mapping_doc.set(field, account)
                    debug_log(f"Mapped expense account for {field} to {account}", "BPJS Account Setup")
                    continue
            except Exception as mapping_error:
                debug_log(
                    f"Error mapping GL account for {field}: {str(mapping_error)}",
                    "BPJS Account Setup Error",
                    trace=True,
                )
            
            # Fallback to traditional account creation if mapping fails
            abbr = frappe.get_cached_value("Company", company, "abbr")
            
            # Get account configurations from defaults.json
            config = get_default_config()
            bpjs_expense_accounts = config.get("gl_accounts", {}).get("bpjs_expense_accounts", {})
            
            # Get account info from config
            account_info = bpjs_expense_accounts.get(account_key, {})
            account_name = account_info.get("account_name")

            if not account_name:
                # Use default naming pattern if not in config
                base_name = (
                    field.replace("_debit_account", "")
                    .replace("_employer", " Employer")
                    .replace("_", " ")
                    .title()
                )
                account_name = f"BPJS {base_name} Expense"

            # Create new account
            full_account_name = f"{account_name} - {abbr}"

            if not frappe.db.exists("Account", full_account_name):
                account_type = account_info.get("account_type", "Expense Account")
                if account_type == "Expense":
                    account_type = "Expense Account"
                root_type = account_info.get("root_type", "Expense")

                try:
                    # Use the centralized create_account function
                    account = create_account(
                        company=company,
                        account_name=account_name,
                        account_type=account_type,
                        parent=expense_parent,
                        root_type=root_type,
                    )

                    if account:
                        debug_log(f"Created expense account: {account}", "BPJS Account Setup")
                        full_account_name = account
                    else:
                        debug_log(
                            f"Failed to create expense account: {account_name}",
                            "BPJS Account Setup Error",
                        )
                        continue

                except Exception as e:
                    debug_log(
                        f"Error creating expense account {account_name}: {str(e)}",
                        "BPJS Account Setup Error",
                        trace=True,
                    )
                    frappe.log_error(
                        f"Error creating expense account {account_name}: {str(e)}",
                        "BPJS Account Setup Error",
                    )
                    continue

            # Set in mapping document
            mapping_doc.set(field, full_account_name)

    except Exception as e:
        frappe.log_error(f"Error setting up expense accounts: {str(e)}", "BPJS Account Setup Error")
        debug_log(
            f"Error setting up expense accounts: {str(e)}", "BPJS Account Setup Error", trace=True
        )


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

        # Get BPJS configuration from defaults.json
        bpjs_config = get_default_config("bpjs")
        if not bpjs_config:
            frappe.throw(_("Cannot create BPJS Settings: Missing configuration in defaults.json"))

        # Create settings
        settings = frappe.new_doc("BPJS Settings")

        # Set values from config
        for key, value in bpjs_config.items():
            if hasattr(settings, key):
                settings.set(key, flt(value))

        # Set current user as owner and modified_by
        settings.owner = frappe.session.user
        settings.modified_by = frappe.session.user

        # Bypass validation during setup
        settings.flags.ignore_validate = True
        settings.flags.ignore_permissions = True
        settings.insert()
        frappe.db.commit()

        debug_log("Created default BPJS Settings", "BPJS Setup")
        return settings

    except Exception as e:
        frappe.log_error(
            f"Error creating default BPJS Settings: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Setup Error",
        )
        debug_log(f"Error creating default BPJS Settings: {str(e)}", "BPJS Setup Error", trace=True)
        return None


# Function for diagnostic purposes
@frappe.whitelist()
def diagnose_accounts():
    """
    Diagnose BPJS Account Mapping issues with enhanced diagnostics

    Returns:
        dict: Diagnostic information about BPJS accounts and mappings
    """
    results = {
        "timestamp": now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
        "settings_exists": False,
        "companies": [],
        "mappings": [],
        "issues": [],
        "system_info": {"frappe_version": frappe.__version__, "user": frappe.session.user},
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
                "jkm_account": settings.get("jkm_account", "Not Set"),
            }
        else:
            results["issues"].append("BPJS Settings doesn't exist")

        # Check companies and mappings
        companies = frappe.get_all("Company", pluck="name")
        for company in companies:
            company_info = {
                "name": company,
                "has_mapping": False,
                "issues": [],
                "abbr": frappe.get_cached_value("Company", company, "abbr"),
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
                    "accounts": {},
                }

                # Standardized account field list for consistency
                account_fields = [
                    "kesehatan_employee_account",
                    "jht_employee_account",
                    "jp_employee_account",
                    "kesehatan_employer_debit_account",
                    "jht_employer_debit_account",
                    "jp_employer_debit_account",
                    "jkk_employer_debit_account",
                    "jkm_employer_debit_account",
                    "kesehatan_employer_credit_account",
                    "jht_employer_credit_account",
                    "jp_employer_credit_account",
                    "jkk_employer_credit_account",
                    "jkm_employer_credit_account",
                ]

                for field in account_fields:
                    account = mapping_doc.get(field)
                    mapping_info["accounts"][field] = account or "Not Set"

                    if not account:
                        company_info["issues"].append(f"Missing account: {field}")
                    elif not frappe.db.exists("Account", account):
                        company_info["issues"].append(f"Account {account} does not exist")
                    else:
                        # Verify account type is correct
                        account_doc = frappe.get_doc("Account", account)
                        expected_type = "Expense" if "debit_account" in field else "Liability"
                        if account_doc.root_type != expected_type:
                            company_info["issues"].append(
                                f"Account {account} has wrong type: {account_doc.root_type} (expected {expected_type})"
                            )

                # Check parent accounts exist
                abbr = company_info["abbr"]

                # Get parent account names from config
                config = get_default_config()
                bpjs_payable_name = (
                    config.get("gl_accounts", {})
                    .get("parent_accounts", {})
                    .get("bpjs_payable", {})
                    .get("account_name", "BPJS Payable")
                )
                bpjs_expenses_name = (
                    config.get("gl_accounts", {})
                    .get("parent_accounts", {})
                    .get("bpjs_expenses", {})
                    .get("account_name", "BPJS Expenses")
                )

                # Check parent accounts
                required_parent_accounts = [
                    f"{bpjs_payable_name} - {abbr}",
                    f"{bpjs_expenses_name} - {abbr}",
                ]

                for parent in required_parent_accounts:
                    if not frappe.db.exists("Account", parent):
                        company_info["issues"].append(f"Parent account {parent} does not exist")
                    else:
                        # Verify parent account is a group
                        is_group = frappe.db.get_value("Account", parent, "is_group")
                        if not is_group:
                            company_info["issues"].append(
                                f"Account {parent} is not a group account"
                            )

                results["mappings"].append(mapping_info)
            else:
                company_info["issues"].append("No BPJS Account Mapping exists")

                # Check if parent accounts exist even without mapping
                abbr = company_info["abbr"]
                config = get_default_config()
                bpjs_payable_name = (
                    config.get("gl_accounts", {})
                    .get("parent_accounts", {})
                    .get("bpjs_payable", {})
                    .get("account_name", "BPJS Payable")
                )
                bpjs_expenses_name = (
                    config.get("gl_accounts", {})
                    .get("parent_accounts", {})
                    .get("bpjs_expenses", {})
                    .get("account_name", "BPJS Expenses")
                )

                for parent_name in [
                    f"{bpjs_payable_name} - {abbr}",
                    f"{bpjs_expenses_name} - {abbr}",
                ]:
                    if frappe.db.exists("Account", parent_name):
                        company_info["issues"].append(
                            f"Parent account {parent_name} exists but has no mapping"
                        )

            results["companies"].append(company_info)

            # Add company issues to global issues list
            if company_info["issues"]:
                for issue in company_info["issues"]:
                    results["issues"].append(f"{company}: {issue}")

        return results
    except Exception as e:
        frappe.log_error(
            f"Error in diagnose_accounts: {str(e)}\n\n" f"Traceback: {frappe.get_traceback()}",
            "BPJS Diagnostic Error",
        )
        debug_log(f"Error in diagnose_accounts: {str(e)}", "BPJS Diagnostic Error", trace=True)
        return {"error": str(e), "timestamp": results["timestamp"]}


# Module level functions for document hooks
def validate(doc, method=None):
    """
    Module level validation function for hooks

    Args:
        doc (obj): Document to validate
        method (str): Method that called this function (not used)
    """
    if getattr(doc, "flags", {}).get("ignore_validate"):
        debug_log(
            f"Skipping validation for {doc.name} during initial setup/migration", "BPJS Mapping"
        )
        return

    # Call document validation method
    doc.validate_duplicate_mapping()
    
    # Validate account fields against mapping from defaults.json
    company = doc.company
    validate_with_gl_mapper(doc, company)


def validate_with_gl_mapper(doc, company):
    """
    Validate account fields using map_gl_account function
    
    Args:
        doc: BPJS Account Mapping document
        company: Company to validate against
    """
    # Skip validation if in setup mode
    if getattr(doc, "flags", {}).get("ignore_validate"):
        return
        
    # Define mapping between document fields and GL account mapper keys and categories
    field_mapping = {
        # Employee accounts (liability)
        "kesehatan_employee_account": ("bpjs_kesehatan_payable", "bpjs_payable_accounts"),
        "jht_employee_account": ("bpjs_jht_payable", "bpjs_payable_accounts"),
        "jp_employee_account": ("bpjs_jp_payable", "bpjs_payable_accounts"),
        
        # Employer expense accounts
        "kesehatan_employer_debit_account": ("bpjs_kesehatan_employer_expense", "bpjs_expense_accounts"),
        "jht_employer_debit_account": ("bpjs_jht_employer_expense", "bpjs_expense_accounts"),
        "jp_employer_debit_account": ("bpjs_jp_employer_expense", "bpjs_expense_accounts"),
        "jkk_employer_debit_account": ("bpjs_jkk_employer_expense", "bpjs_expense_accounts"),
        "jkm_employer_debit_account": ("bpjs_jkm_employer_expense", "bpjs_expense_accounts"),
        
        # Employer liability accounts
        "kesehatan_employer_credit_account": ("bpjs_kesehatan_payable", "bpjs_payable_accounts"),
        "jht_employer_credit_account": ("bpjs_jht_payable", "bpjs_payable_accounts"),
        "jp_employer_credit_account": ("bpjs_jp_payable", "bpjs_payable_accounts"),
        "jkk_employer_credit_account": ("bpjs_jkk_payable", "bpjs_payable_accounts"),
        "jkm_employer_credit_account": ("bpjs_jkm_payable", "bpjs_payable_accounts")
    }
    
    # Validate and/or update each field
    failed_fields = []
    
    for field, (account_key, category) in field_mapping.items():
        try:
            # Get mapped account from defaults.json
            mapped_account = map_gl_account(company, account_key, category)
            
            # Check if field is set
            if not doc.get(field):
                # Set field if valid mapped account exists
                if mapped_account and frappe.db.exists("Account", mapped_account):
                    doc.set(field, mapped_account)
                    debug_log(f"Set {field} to mapped account {mapped_account}", "BPJS Mapping Validation")
                else:
                    failed_fields.append(field)
            # If field is set but doesn't match mapped account, show warning
            elif mapped_account and doc.get(field) != mapped_account:
                # Just warn but don't change
                frappe.msgprint(
                    _(f"Field {field} has account {doc.get(field)} but expected {mapped_account} based on GL mapping."),
                    indicator="orange",
                    alert=True
                )
                
            # Validate account exists
            if doc.get(field) and not frappe.db.exists("Account", doc.get(field)):
                failed_fields.append(field)
                doc.set(field, None)  # Clear invalid account
        
        except Exception as e:
            debug_log(
                f"Error validating {field} with map_gl_account: {str(e)}",
                "BPJS Mapping Validation Error",
                trace=True
            )
            failed_fields.append(field)
    
    # Raise ValidationError if any fields failed
    if failed_fields and not doc.flags.get("ignore_validation_errors"):
        frappe.throw(
            _("Failed to map the following accounts from defaults.json: {0}. Please check the configuration.").format(
                ", ".join(failed_fields)
            )
        )


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
    
    # Update accounts from GL mapping
    update_accounts_from_mapping(doc)


def update_accounts_from_mapping(doc):
    """
    Update empty account fields using map_gl_account function
    
    Args:
        doc: BPJS Account Mapping document
    """
    if doc.flags.get("skip_account_update"):
        return
        
    company = doc.company
    accounts_updated = False
    
    # Define mapping between document fields and GL account mapper keys and categories
    field_mapping = {
        # Employee accounts (liability)
        "kesehatan_employee_account": ("bpjs_kesehatan_payable", "bpjs_payable_accounts"),
        "jht_employee_account": ("bpjs_jht_payable", "bpjs_payable_accounts"),
        "jp_employee_account": ("bpjs_jp_payable", "bpjs_payable_accounts"),
        
        # Employer expense accounts
        "kesehatan_employer_debit_account": ("bpjs_kesehatan_employer_expense", "bpjs_expense_accounts"),
        "jht_employer_debit_account": ("bpjs_jht_employer_expense", "bpjs_expense_accounts"),
        "jp_employer_debit_account": ("bpjs_jp_employer_expense", "bpjs_expense_accounts"),
        "jkk_employer_debit_account": ("bpjs_jkk_employer_expense", "bpjs_expense_accounts"),
        "jkm_employer_debit_account": ("bpjs_jkm_employer_expense", "bpjs_expense_accounts"),
        
        # Employer liability accounts
        "kesehatan_employer_credit_account": ("bpjs_kesehatan_payable", "bpjs_payable_accounts"),
        "jht_employer_credit_account": ("bpjs_jht_payable", "bpjs_payable_accounts"),
        "jp_employer_credit_account": ("bpjs_jp_payable", "bpjs_payable_accounts"),
        "jkk_employer_credit_account": ("bpjs_jkk_payable", "bpjs_payable_accounts"),
        "jkm_employer_credit_account": ("bpjs_jkm_payable", "bpjs_payable_accounts")
    }
    
    # Update empty fields with mapped accounts
    for field, (account_key, category) in field_mapping.items():
        if not doc.get(field):
            try:
                account = map_gl_account(company, account_key, category)
                if account and frappe.db.exists("Account", account):
                    doc.set(field, account)
                    accounts_updated = True
                    debug_log(
                        f"Updated empty {field} with mapped account {account}",
                        "BPJS Mapping Update"
                    )
            except Exception as e:
                debug_log(
                    f"Error mapping account for field {field}: {str(e)}",
                    "BPJS Mapping Update Error"
                )
    
    # Save the document if any accounts were updated
    if accounts_updated:
        try:
            doc.flags.skip_account_update = True  # Prevent recursive updates
            doc.flags.ignore_validate = True
            doc.flags.ignore_permissions = True
            doc.save()
            debug_log(f"Saved BPJS Account Mapping {doc.name} after updating accounts", "BPJS Mapping Update")
        except Exception as e:
            debug_log(
                f"Error saving BPJS Account Mapping after updating accounts: {str(e)}",
                "BPJS Mapping Update Error"
            )


class BPJSAccountMapping(Document):
    def validate(self):
        """Validate required fields and account types"""
        # Skip validation if in migration/setup mode
        if getattr(self, "flags", {}).get("ignore_validate"):
            debug_log(
                f"Skipping validation for {self.name} during initial setup/migration",
                "BPJS Mapping",
            )
            return

        self.validate_duplicate_mapping()
        
        # Validate accounts using map_gl_account
        company = self.company
        self.resolve_accounts_with_mapper(company)
        self.validate_account_types()

    def validate_duplicate_mapping(self):
        """Ensure no duplicate mapping exists for the same company"""
        if not self.is_new():
            # Skip validation when updating the same document
            return

        existing = frappe.db.get_value(
            "BPJS Account Mapping",
            {"company": self.company, "name": ["!=", self.name]},
            "mapping_name",
        )

        if existing:
            frappe.throw(
                _("BPJS Account Mapping '{0}' already exists for company {1}").format(
                    existing, self.company
                )
            )
    
    def resolve_accounts_with_mapper(self, company):
        """
        Resolve and update account fields using map_gl_account function
        
        Args:
            company: Company to resolve accounts for
        """
        # Define mapping between document fields and GL account mapper keys and categories
        field_mapping = {
            # Employee accounts (liability)
            "kesehatan_employee_account": ("bpjs_kesehatan_payable", "bpjs_payable_accounts"),
            "jht_employee_account": ("bpjs_jht_payable", "bpjs_payable_accounts"),
            "jp_employee_account": ("bpjs_jp_payable", "bpjs_payable_accounts"),
            
            # Employer expense accounts
            "kesehatan_employer_debit_account": ("bpjs_kesehatan_employer_expense", "bpjs_expense_accounts"),
            "jht_employer_debit_account": ("bpjs_jht_employer_expense", "bpjs_expense_accounts"),
            "jp_employer_debit_account": ("bpjs_jp_employer_expense", "bpjs_expense_accounts"),
            "jkk_employer_debit_account": ("bpjs_jkk_employer_expense", "bpjs_expense_accounts"),
            "jkm_employer_debit_account": ("bpjs_jkm_employer_expense", "bpjs_expense_accounts"),
            
            # Employer liability accounts
            "kesehatan_employer_credit_account": ("bpjs_kesehatan_payable", "bpjs_payable_accounts"),
            "jht_employer_credit_account": ("bpjs_jht_payable", "bpjs_payable_accounts"),
            "jp_employer_credit_account": ("bpjs_jp_payable", "bpjs_payable_accounts"),
            "jkk_employer_credit_account": ("bpjs_jkk_payable", "bpjs_payable_accounts"),
            "jkm_employer_credit_account": ("bpjs_jkm_payable", "bpjs_payable_accounts")
        }
        
        # List to collect fields that failed mapping
        failed_fields = []
        
        # Process each field
        for field, (account_key, category) in field_mapping.items():
            try:
                # Only set value if field is empty
                if not self.get(field):
                    # Get mapped account name
                    account = map_gl_account(company, account_key, category)
                    
                    # Set field if account exists
                    if account and frappe.db.exists("Account", account):
                        self.set(field, account)
                        debug_log(
                            f"Mapped {field} to {account} using map_gl_account", 
                            "BPJS Mapping"
                        )
                    else:
                        # Account couldn't be mapped or doesn't exist
                        failed_fields.append(field)
                        debug_log(
                            f"Failed to map {field}: Account {account} doesn't exist", 
                            "BPJS Mapping Error"
                        )
            except Exception as e:
                failed_fields.append(field)
                debug_log(
                    f"Error mapping {field} with map_gl_account: {str(e)}", 
                    "BPJS Mapping Error",
                    trace=True
                )
        
        # Raise validation error if any fields couldn't be mapped
        if failed_fields and not self.flags.get("ignore_validation_errors"):
            frappe.throw(
                _("Failed to map the following accounts from defaults.json: {0}. Please check the configuration.").format(
                    ", ".join(failed_fields)
                )
            )

    def validate_account_types(self):
        """Validate that all accounts are of the correct type"""
        # Skip empty accounts in validation as those will be caught elsewhere
        if self.kesehatan_employee_account:
            self.validate_account_type(
                self.kesehatan_employee_account, ["Liability"], "BPJS Kesehatan Employee"
            )
        if self.jht_employee_account:
            self.validate_account_type(self.jht_employee_account, ["Liability"], "BPJS JHT Employee")
        if self.jp_employee_account:
            self.validate_account_type(self.jp_employee_account, ["Liability"], "BPJS JP Employee")

        # Employer expense accounts should be expense accounts
        if self.kesehatan_employer_debit_account:
            self.validate_account_type(
                self.kesehatan_employer_debit_account,
                ["Expense"],
                "BPJS Kesehatan Employer Expense",
            )
        if self.jht_employer_debit_account:
            self.validate_account_type(
                self.jht_employer_debit_account,
                ["Expense"],
                "BPJS JHT Employer Expense",
            )
        if self.jp_employer_debit_account:
            self.validate_account_type(
                self.jp_employer_debit_account,
                ["Expense"],
                "BPJS JP Employer Expense",
            )
        if self.jkk_employer_debit_account:
            self.validate_account_type(
                self.jkk_employer_debit_account,
                ["Expense"],
                "BPJS JKK Employer Expense",
            )
        if self.jkm_employer_debit_account:
            self.validate_account_type(
                self.jkm_employer_debit_account,
                ["Expense"],
                "BPJS JKM Employer Expense",
            )

        # Employer liability accounts should be liability accounts
        if self.kesehatan_employer_credit_account:
            self.validate_account_type(
                self.kesehatan_employer_credit_account,
                ["Liability"],
                "BPJS Kesehatan Employer Liability",
            )
        if self.jht_employer_credit_account:
            self.validate_account_type(
                self.jht_employer_credit_account, ["Liability"], "BPJS JHT Employer Liability"
            )
        if self.jp_employer_credit_account:
            self.validate_account_type(
                self.jp_employer_credit_account, ["Liability"], "BPJS JP Employer Liability"
            )
        if self.jkk_employer_credit_account:
            self.validate_account_type(
                self.jkk_employer_credit_account, ["Liability"], "BPJS JKK Employer Liability"
            )
        if self.jkm_employer_credit_account:
            self.validate_account_type(
                self.jkm_employer_credit_account, ["Liability"], "BPJS JKM Employer Liability"
            )

    def validate_account_type(self, account, allowed_root_types, account_description):
        """
        Validate that an account has the correct root type

        Args:
            account (str): Account name to validate
            allowed_root_types (list): List of allowed root types
            account_description (str): Description of the account for error messages
        """
        if not account:
            # Skip validation if account is not provided
            return

        account_doc = frappe.db.get_value(
            "Account", account, ["account_type", "root_type", "company"], as_dict=1
        )

        if not account_doc:
            frappe.throw(_("Account {0} does not exist").format(account))

        if account_doc.root_type not in allowed_root_types:
            frappe.throw(
                _("{0} account {1} must be a {2} account").format(
                    account_description, account, " or ".join(allowed_root_types)
                )
            )

        if account_doc.company != self.company:
            frappe.throw(
                _("Account {0} does not belong to company {1}").format(account, self.company)
            )

    def on_update(self):
        """Refresh cache and perform additional operations after update"""
        frappe.cache().delete_value(f"bpjs_mapping_{self.company}")
        debug_log(
            f"Cleared cache for BPJS mapping of company {self.company}", "BPJS Mapping Update"
        )
        
        # Update empty accounts using map_gl_account
        if not self.flags.get("skip_account_update"):
            company = self.company
            field_mapping = {
                # Employee accounts (liability)
                "kesehatan_employee_account": ("bpjs_kesehatan_payable", "bpjs_payable_accounts"),
                "jht_employee_account": ("bpjs_jht_payable", "bpjs_payable_accounts"),
                "jp_employee_account": ("bpjs_jp_payable", "bpjs_payable_accounts"),
                
                # Employer expense accounts
                "kesehatan_employer_debit_account": ("bpjs_kesehatan_employer_expense", "bpjs_expense_accounts"),
                "jht_employer_debit_account": ("bpjs_jht_employer_expense", "bpjs_expense_accounts"),
                "jp_employer_debit_account": ("bpjs_jp_employer_expense", "bpjs_expense_accounts"),
                "jkk_employer_debit_account": ("bpjs_jkk_employer_expense", "bpjs_expense_accounts"),
                "jkm_employer_debit_account": ("bpjs_jkm_employer_expense", "bpjs_expense_accounts"),
                
                # Employer liability accounts
                "kesehatan_employer_credit_account": ("bpjs_kesehatan_payable", "bpjs_payable_accounts"),
                "jht_employer_credit_account": ("bpjs_jht_payable", "bpjs_payable_accounts"),
                "jp_employer_credit_account": ("bpjs_jp_payable", "bpjs_payable_accounts"),
                "jkk_employer_credit_account": ("bpjs_jkk_payable", "bpjs_payable_accounts"),
                "jkm_employer_credit_account": ("bpjs_jkm_payable", "bpjs_payable_accounts")
            }
            
            # Flag to track if any accounts were updated
            accounts_updated = False
            
            # Only map empty fields to avoid overwriting user customizations
            for field, (account_key, category) in field_mapping.items():
                if not self.get(field):
                    try:
                        mapped_account = map_gl_account(company, account_key, category)
                        if mapped_account and frappe.db.exists("Account", mapped_account):
                            self.set(field, mapped_account)
                            accounts_updated = True
                            debug_log(
                                f"Updated {field} with mapped account {mapped_account}", 
                                "BPJS Mapping Update"
                            )
                    except Exception as e:
                        debug_log(
                            f"Error updating {field} with map_gl_account: {str(e)}", 
                            "BPJS Mapping Update Error",
                            trace=True
                        )
            
            # Save the document again if any accounts were updated
            if accounts_updated:
                self.flags.skip_account_update = True  # Prevent recursive updates
                self.save(ignore_permissions=True)
                debug_log(
                    f"Updated BPJS Account Mapping {self.name} with mapped accounts", 
                    "BPJS Mapping Update"
                )

    def get_accounts_for_component(self, component_type):
        """
        Get the accounts to use for a specific BPJS component

        Args:
            component_type (str): One of 'kesehatan', 'jht', 'jp', 'jkk', 'jkm'

        Returns:
            dict: Dictionary with employee_account, employer_debit, employer_credit keys
        """
        accounts = {"employee_account": None, "employer_debit": None, "employer_credit": None}

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
