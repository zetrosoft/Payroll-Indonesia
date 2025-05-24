# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-24 05:34:21 by dannyaudian

import frappe
from frappe.utils import getdate, flt

# Import utility functions from centralized utils module
from payroll_indonesia.payroll_indonesia.utils import (
    get_default_config,
    debug_log,
    create_account,
    find_parent_account,
)

# Import GL account mapper
from payroll_indonesia.config.gl_account_mapper import map_gl_account

__all__ = [
    "before_install",
    "after_install",
    "after_sync",
    "check_system_readiness",
    "setup_accounts",
    "setup_pph21",
    "create_supplier_group",
    "create_bpjs_supplier",
    "setup_salary_components",
    "display_installation_summary",
]


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
            f"Error during before_install: {str(e)}\n\n" f"Traceback: {frappe.get_traceback()}",
            "Payroll Indonesia Installation Error",
        )
        debug_log(
            f"Error during before_install: {str(e)}",
            "Payroll Indonesia Installation Error",
            trace=True,
        )


def after_install():
    """
    Setup requirements after installing the app

    Creates accounts, sets up tax configuration, configures BPJS and more.
    The custom fields are handled by the fixtures automatically.
    """

    debug_log("Starting Payroll Indonesia after_install process", "Installation")

    # Load configuration defaults
    config = get_default_config()

    # Track setup results
    results = {
        "accounts": False,
        "suppliers": False,
        "pph21_settings": False,
        "salary_components": False,
        "bpjs_setup": False,
    }

    try:
        # Create accounts first (required for salary components)
        results["accounts"] = setup_accounts(config)
        debug_log("Account setup completed", "Installation")
    except Exception as e:
        frappe.log_error(
            f"Error during account setup: {str(e)}\n\n" f"Traceback: {frappe.get_traceback()}",
            "Account Setup Error",
        )
        debug_log(f"Error during account setup: {str(e)}", "Account Setup Error", trace=True)

    try:
        # Setup suppliers
        supplier_results = create_supplier_group()
        # Only attempt creating BPJS supplier if supplier group creation was successful
        if supplier_results and config.get("suppliers", {}).get("bpjs", {}):
            supplier_results = create_bpjs_supplier(config)
        results["suppliers"] = supplier_results
        debug_log("Supplier setup completed", "Installation")
    except Exception as e:
        frappe.log_error(
            f"Error during supplier setup: {str(e)}\n\n" f"Traceback: {frappe.get_traceback()}",
            "Supplier Setup Error",
        )
        debug_log(f"Error during supplier setup: {str(e)}", "Supplier Setup Error", trace=True)

    try:
        # Setup tax configuration and TER rates
        pph21_results = setup_pph21(config)
        results["pph21_settings"] = pph21_results
        debug_log("PPh 21 setup completed", "Installation")
    except Exception as e:
        frappe.log_error(
            f"Error during PPh 21 setup: {str(e)}\n\n" f"Traceback: {frappe.get_traceback()}",
            "PPh 21 Setup Error",
        )
        debug_log(f"Error during PPh 21 setup: {str(e)}", "PPh 21 Setup Error", trace=True)

    try:
        # Setup salary components
        results["salary_components"] = setup_salary_components(config)
        debug_log("Salary components setup completed", "Installation")
    except Exception as e:
        frappe.log_error(
            f"Error during salary components setup: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Salary Components Setup Error",
        )
        debug_log(
            f"Error during salary components setup: {str(e)}",
            "Salary Components Setup Error",
            trace=True,
        )

    try:
        # Setup BPJS - Use module function to create a single instance
        from payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.bpjs_settings import (
            setup_bpjs_settings,
        )

        results["bpjs_setup"] = setup_bpjs_settings()
        debug_log("BPJS setup completed", "Installation")
    except Exception as e:
        frappe.log_error(
            f"Error during BPJS setup: {str(e)}\n\n" f"Traceback: {frappe.get_traceback()}",
            "BPJS Setup Error",
        )
        debug_log(f"Error during BPJS setup: {str(e)}", "BPJS Setup Error", trace=True)

    # Commit all changes
    try:
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(
            f"Error committing changes: {str(e)}\n\n" f"Traceback: {frappe.get_traceback()}",
            "Installation Database Error",
        )
        debug_log(f"Error committing changes: {str(e)}", "Installation Database Error", trace=True)

    # Display installation summary
    display_installation_summary(results, config)


def after_sync():
    """
    Setup function that runs after app sync

    Updates BPJS settings if they exist
    """

    try:
        debug_log("Starting after_sync process", "App Sync")

        # Check if BPJS Settings already exist
        if frappe.db.exists("DocType", "BPJS Settings") and frappe.db.exists(
            "BPJS Settings", "BPJS Settings"
        ):
            # Use module function to update from latest defaults
            from payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.bpjs_settings import (
                update_bpjs_settings,
            )

            updated = update_bpjs_settings()
            debug_log(f"Updated BPJS Settings: {updated}", "App Sync")

        # Ensure TER settings are updated for PMK 168/2023
        if frappe.db.exists("DocType", "PPh 21 Settings") and frappe.db.exists(
            "PPh 21 Settings", "PPh 21 Settings"
        ):
            # Check if we need to update TER settings
            config = get_default_config()
            if config and "ptkp_to_ter_mapping" in config:
                update_ptkp_ter_mapping(config)
                debug_log("Updated PTKP to TER mapping for PMK 168/2023", "App Sync")

            # Update TER rates if needed
            if config and "ter_rates" in config:
                # Check if TER rates are already in new format (TER A, TER B, TER C)
                has_new_format = frappe.db.exists(
                    "PPh 21 TER Table", {"status_pajak": ["in", ["TER A", "TER B", "TER C"]]}
                )
                if not has_new_format:
                    setup_pph21_ter(config, force_update=True)
                    debug_log("Updated TER rates to PMK 168/2023 format", "App Sync")
    except Exception as e:
        frappe.log_error(
            f"Error during after_sync: {str(e)}\n\n" f"Traceback: {frappe.get_traceback()}",
            "Payroll Indonesia Sync Error",
        )
        debug_log(f"Error during after_sync: {str(e)}", "Payroll Indonesia Sync Error", trace=True)


def update_ptkp_ter_mapping(config):
    """
    Update or create PTKP to TER mapping based on PMK 168/2023

    Args:
        config (dict): Configuration data from defaults.json

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get mapping from config
        ptkp_to_ter_mapping = config.get("ptkp_to_ter_mapping", {})
        if not ptkp_to_ter_mapping:
            debug_log("No PTKP to TER mapping found in config", "TER Mapping Update")
            return False

        # Get or create mapping DocType
        mapping_doctype = "PTKP TER Mapping"
        if not frappe.db.exists("DocType", mapping_doctype):
            debug_log(f"{mapping_doctype} DocType does not exist", "TER Mapping Update")
            return False

        # Delete existing mappings
        try:
            frappe.db.sql(f"DELETE FROM `tab{mapping_doctype}`")
            frappe.db.commit()
            debug_log("Cleared existing PTKP to TER mappings", "TER Mapping Update")
        except Exception as e:
            frappe.log_error(
                f"Error clearing existing PTKP to TER mappings: {str(e)}", "TER Mapping Error"
            )
            debug_log(
                f"Error clearing existing PTKP to TER mappings: {str(e)}",
                "TER Mapping Error",
                trace=True,
            )

        # Create new mappings
        count = 0
        for ptkp_status, ter_category in ptkp_to_ter_mapping.items():
            try:
                mapping = frappe.new_doc(mapping_doctype)
                mapping.ptkp_status = ptkp_status
                mapping.ter_category = ter_category

                # Add description based on TER category
                if ter_category == "TER A":
                    mapping.description = "PTKP TK/0 (Rp 54 juta/tahun)"
                elif ter_category == "TER B":
                    mapping.description = "PTKP K/0, TK/1, TK/2, K/1 (Rp 58,5-63 juta/tahun)"
                elif ter_category == "TER C":
                    mapping.description = "PTKP dengan nilai lebih tinggi (> Rp 63 juta/tahun)"
                else:
                    mapping.description = f"Pemetaan {ptkp_status} ke {ter_category}"

                mapping.flags.ignore_permissions = True
                mapping.insert(ignore_permissions=True)
                count += 1
            except Exception as e:
                frappe.log_error(
                    f"Error creating mapping for {ptkp_status} to {ter_category}: {str(e)}",
                    "TER Mapping Error",
                )
                debug_log(
                    f"Error creating mapping for {ptkp_status} to {ter_category}: {str(e)}",
                    "TER Mapping Error",
                    trace=True,
                )

        # Commit changes
        frappe.db.commit()
        debug_log(f"Created {count} PTKP to TER mappings for PMK 168/2023", "TER Mapping Update")
        return count > 0

    except Exception as e:
        frappe.log_error(
            f"Error updating PTKP to TER mapping: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "TER Mapping Error",
        )
        debug_log(f"Error updating PTKP to TER mapping: {str(e)}", "TER Mapping Error", trace=True)
        return False


def check_system_readiness():
    """
    Check if system is ready for Payroll Indonesia installation

    Returns:
        bool: True if ready, False otherwise
    """

    # Check if required DocTypes exist
    required_core_doctypes = [
        "Salary Component",
        "Salary Structure",
        "Salary Slip",
        "Employee",
        "Company",
        "Account",
    ]

    missing_doctypes = []
    for doctype in required_core_doctypes:
        if not frappe.db.exists("DocType", doctype):
            missing_doctypes.append(doctype)

    if missing_doctypes:
        debug_log(
            f"Required DocTypes missing: {', '.join(missing_doctypes)}", "System Readiness Check"
        )
        frappe.log_error(
            f"Required DocTypes missing: {', '.join(missing_doctypes)}", "System Readiness Check"
        )
        debug_log(
            f"Required DocTypes missing: {', '.join(missing_doctypes)}",
            "System Readiness Check",
            trace=True,
        )

    # Check if company exists
    company_records = frappe.get_all("Company")
    if not company_records:
        debug_log("No company found. Some setup steps may fail.", "System Readiness Check")
        frappe.log_error("No company found", "System Readiness Check")
        debug_log("No company found", "System Readiness Check", trace=True)

    # Return True so installation can continue with warnings
    return True


def setup_accounts(config):
    """
    Create required Accounts for Indonesian payroll management using find_parent_account utility
    
    Args:
        config (dict): Configuration data from defaults.json

    Returns:
        bool: True if successful, False otherwise
    """
    # Validate configuration
    if not config:
        debug_log("No configuration data available for creating accounts", "Account Setup")
        return False

    gl_accounts = config.get("gl_accounts", {})
    if not gl_accounts:
        debug_log("No GL accounts configuration found in defaults.json", "Account Setup Error")
        return False

    # Get all companies
    company_records = frappe.get_all("Company", pluck="name")
    if not company_records:
        debug_log("No company found. Cannot create accounts.", "Account Setup Error")
        return False

    # Track overall success
    overall_success = True
    
    # Account sections to process
    account_sections = [
        "expense_accounts",
        "payable_accounts",
        "bpjs_expense_accounts",
        "bpjs_payable_accounts"
    ]

    # Track account creation statistics
    statistics = {
        "companies_processed": 0,
        "companies_with_errors": 0,
        "total_accounts_created": 0,
        "total_accounts_failed": 0,
        "root_accounts_created": 0,
        "root_accounts_failed": 0
    }

    # Process each company
    for company in company_records:
        company_success = True
        company_stats = {
            "accounts_created": 0,
            "accounts_failed": 0,
            "categories_processed": 0
        }
        
        try:
            debug_log(f"Creating accounts for company: {company}", "Account Setup")
            
            # First create the root account defined in config
            root_account_config = gl_accounts.get("root_account")
            if root_account_config:
                root_name = root_account_config.get("account_name")
                root_type = root_account_config.get("account_type")
                root_is_group = root_account_config.get("is_group", 1)
                root_account_root_type = root_account_config.get("root_type")
                
                # Determine parent account for root based on root_type
                if root_account_root_type == "Asset":
                    parent_account = "Application of Funds (Assets)"
                elif root_account_root_type in ["Liability", "Equity"]:
                    parent_account = "Source of Funds (Liabilities)"
                elif root_account_root_type in ["Income", "Expense"]:
                    parent_account = f"{root_account_root_type} - {company}"
                else:
                    parent_account = None
                    # Try to find a suitable parent using find_parent_account
                    parent_account = find_parent_account(company, root_type, root_account_root_type)
                    if not parent_account:
                        debug_log(
                            f"Could not find parent for root account {root_name} in company {company}",
                            "Account Setup Error"
                        )
                        parent_account = "Application of Funds (Assets)"  # fallback
                
                # Create root account
                root_account_name = create_account(
                    company=company,
                    account_name=root_name,
                    account_type=root_type,
                    parent=parent_account,
                    root_type=root_account_root_type,
                    is_group=root_is_group
                )
                
                if root_account_name:
                    debug_log(f"Created root account: {root_account_name}", "Account Setup")
                    statistics["root_accounts_created"] += 1
                    company_stats["accounts_created"] += 1
                else:
                    debug_log(f"Failed to create root account for {company}", "Account Setup Error")
                    statistics["root_accounts_failed"] += 1
                    company_success = False
                    continue
            else:
                root_account_name = None
                debug_log("No root account configuration found, using find_parent_account for each section", "Account Setup")
            
            # Process each account section
            for section in account_sections:
                try:
                    # Skip if section doesn't exist in config
                    if section not in gl_accounts:
                        debug_log(f"Section '{section}' not found in GL accounts config", "Account Setup")
                        continue
                        
                    company_stats["categories_processed"] += 1
                    
                    # Determine account type and root type based on section
                    if section == "expense_accounts" or section == "bpjs_expense_accounts":
                        account_type = "Expense Account"
                        root_type = "Expense"
                    elif section == "payable_accounts" or section == "bpjs_payable_accounts":
                        account_type = "Payable"
                        root_type = "Liability"
                    else:
                        account_type = "Expense Account"  # Default
                        root_type = "Expense"  # Default
                    
                    # Find appropriate parent account
                    # First try using the root account we created, if available
                    if root_account_name and frappe.db.exists("Account", root_account_name):
                        parent_account = root_account_name
                        debug_log(f"Using root account {parent_account} as parent for {section}", "Account Setup")
                    else:
                        # Fall back to find_parent_account
                        parent_account = find_parent_account(company, account_type, root_type)
                        
                        if not parent_account:
                            debug_log(
                                f"Could not find suitable parent account for {account_type} (root_type: {root_type}) in company {company}",
                                "Account Setup Error"
                            )
                            company_success = False
                            company_stats["accounts_failed"] += len(gl_accounts.get(section, {}))
                            continue
                        
                        debug_log(
                            f"Found parent account {parent_account} for {account_type} in company {company}",
                            "Account Setup"
                        )
                    
                    # Process accounts in this section
                    accounts_config = gl_accounts.get(section, {})
                    for key, account_info in accounts_config.items():
                        try:
                            # Extract account properties
                            account_name = account_info.get("account_name")
                            item_account_type = account_info.get("account_type", account_type)
                            item_root_type = account_info.get("root_type", root_type)
                            
                            if not account_name:
                                debug_log(f"Missing account_name for {key}", "Account Setup Error")
                                company_stats["accounts_failed"] += 1
                                continue
                            
                            # Create account using utility function
                            full_account_name = create_account(
                                company=company,
                                account_name=account_name,
                                account_type=item_account_type,
                                parent=parent_account,
                                root_type=item_root_type
                            )
                            
                            if full_account_name:
                                company_stats["accounts_created"] += 1
                                debug_log(f"Created account: {full_account_name}", "Account Setup")
                            else:
                                company_stats["accounts_failed"] += 1
                                company_success = False
                                debug_log(f"Failed to create account for {key}", "Account Setup Error")
                                
                        except Exception as account_error:
                            company_stats["accounts_failed"] += 1
                            company_success = False
                            debug_log(
                                f"Error creating account for {key}: {str(account_error)}",
                                "Account Setup Error",
                                trace=True
                            )
                    
                    debug_log(
                        f"Processed {section} for {company}: created {company_stats['accounts_created']} accounts",
                        "Account Setup"
                    )
                        
                except Exception as e:
                    company_success = False
                    debug_log(
                        f"Error processing section '{section}' for {company}: {str(e)}",
                        "Account Setup Error",
                        trace=True
                    )
            
            # Update statistics at company level
            statistics["companies_processed"] += 1
            statistics["total_accounts_created"] += company_stats["accounts_created"]
            statistics["total_accounts_failed"] += company_stats["accounts_failed"]
            
            if not company_success:
                statistics["companies_with_errors"] += 1
                
            # Commit changes for this company
            frappe.db.commit()
            
            # Log company summary
            debug_log(
                f"Company {company} account setup: created {company_stats['accounts_created']}, "
                f"failed {company_stats['accounts_failed']}, status: {'Success' if company_success else 'Failed'}",
                "Account Setup Summary"
            )

        except Exception as e:
            frappe.log_error(
                f"Error setting up accounts for company {company}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Account Creation Critical Error",
            )
            debug_log(
                f"Error setting up accounts for company {company}: {str(e)}",
                "Account Creation Critical Error",
                trace=True,
            )
            statistics["companies_with_errors"] += 1
            overall_success = False

    # Log overall statistics
    debug_log(
        f"Account setup complete: processed {statistics['companies_processed']} companies, "
        f"{statistics['companies_with_errors']} had errors. "
        f"Created {statistics['total_accounts_created']} accounts (including {statistics['root_accounts_created']} root accounts), "
        f"failed to create {statistics['total_accounts_failed']} accounts (including {statistics['root_accounts_failed']} root accounts).",
        "Account Setup Final Summary"
    )

    # If any root account creation failed, consider the whole process failed
    if statistics["root_accounts_failed"] > 0:
        overall_success = False

    return overall_success


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
            f"Failed to create supplier group: {str(e)}\n\n" f"Traceback: {frappe.get_traceback()}",
            "Supplier Setup Error",
        )
        debug_log(f"Failed to create supplier group: {str(e)}", "Supplier Setup Error", trace=True)
        return False


def create_bpjs_supplier(config):
    """
    Create BPJS supplier entity from config

    Args:
        config (dict): Configuration data from defaults.json

    Returns:
        bool: True if successful, False otherwise
    """

    try:
        supplier_config = config.get("suppliers", {}).get("bpjs", {})
        if not supplier_config:
            debug_log("No BPJS supplier configuration found", "Supplier Setup")
            return False

        supplier_name = supplier_config.get("supplier_name", "BPJS")

        # Skip if already exists
        if frappe.db.exists("Supplier", supplier_name):
            debug_log(f"Supplier {supplier_name} already exists", "Supplier Setup")
            return True

        # Ensure supplier group exists
        supplier_group = supplier_config.get("supplier_group", "Government")
        if not frappe.db.exists("Supplier Group", supplier_group):
            supplier_group = "BPJS Provider"  # Try alternative
            if not frappe.db.exists("Supplier Group", supplier_group):
                supplier_group = "Government"  # Fallback
                if not frappe.db.exists("Supplier Group", supplier_group):
                    debug_log("No suitable supplier group exists", "Supplier Setup")
                    return False

        # Create supplier
        supplier = frappe.new_doc("Supplier")
        supplier.supplier_name = supplier_name
        supplier.supplier_group = supplier_group
        supplier.supplier_type = supplier_config.get("supplier_type", "Government")
        supplier.country = supplier_config.get("country", "Indonesia")
        supplier.default_currency = supplier_config.get("default_currency", "IDR")

        supplier.flags.ignore_permissions = True
        supplier.insert(ignore_permissions=True)

        frappe.db.commit()
        debug_log(f"Created supplier: {supplier_name}", "Supplier Setup")
        return True

    except Exception as e:
        frappe.log_error(
            f"Failed to create BPJS supplier: {str(e)}\n\n" f"Traceback: {frappe.get_traceback()}",
            "Supplier Setup Error",
        )
        debug_log(f"Failed to create BPJS supplier: {str(e)}", "Supplier Setup Error", trace=True)
        return False


def setup_pph21(config):
    """
    Setup PPh 21 tax settings including TER and tax slabs

    Args:
        config (dict): Configuration from defaults.json

    Returns:
        bool: True if successful, False otherwise
    """

    try:
        # Setup PPh 21 Settings first
        pph21_settings = setup_pph21_defaults(config)
        if not pph21_settings:
            debug_log("Failed to setup PPh 21 defaults", "PPh 21 Setup Error")
            return False

        # Setup TER rates using PMK 168/2023 format
        ter_result = setup_pph21_ter(config)

        # Setup income tax slab
        tax_slab_result = setup_income_tax_slab(config)

        return ter_result and tax_slab_result
    except Exception as e:
        frappe.log_error(
            f"Error in PPh 21 setup: {str(e)}\n\n" f"Traceback: {frappe.get_traceback()}",
            "PPh 21 Setup Error",
        )
        debug_log(f"Error in PPh 21 setup: {str(e)}", "PPh 21 Setup Error", trace=True)
        return False


def setup_pph21_defaults(config):
    """
    Setup default PPh 21 configuration with TER method using config data

    Args:
        config (dict): Configuration data from defaults.json

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

        # Set TER as default calculation method from config
        tax_config = config.get("tax", {})
        settings.calculation_method = tax_config.get("tax_calculation_method", "TER")
        settings.use_ter = tax_config.get("use_ter", 1)
        settings.use_gross_up = tax_config.get("use_gross_up", 0)
        settings.npwp_mandatory = tax_config.get("npwp_mandatory", 0)
        settings.biaya_jabatan_percent = tax_config.get("biaya_jabatan_percent", 5.0)
        settings.biaya_jabatan_max = tax_config.get("biaya_jabatan_max", 500000.0)
        settings.umr_default = tax_config.get("umr_default", 4900000.0)
        settings.ter_notes = "Tarif Efektif Rata-rata (TER) sesuai PMK-168/PMK.010/2023 dengan 3 kategori (TER A, B, C)"

        # Add PTKP values from config
        ptkp_values = config.get("ptkp", {})
        if not ptkp_values:
            debug_log("No PTKP values found in config, using defaults", "PPh 21 Setup")
            # Fallback to defaults
            ptkp_values = {
                "TK0": 54000000,
                "TK1": 58500000,
                "TK2": 63000000,
                "TK3": 67500000,
                "K0": 58500000,
                "K1": 63000000,
                "K2": 67500000,
                "K3": 72000000,
                "HB0": 112500000,
                "HB1": 117000000,
                "HB2": 121500000,
                "HB3": 126000000,
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

            # Get associated TER category
            ter_category = ""
            ptkp_to_ter_mapping = config.get("ptkp_to_ter_mapping", {})
            if ptkp_to_ter_mapping and status in ptkp_to_ter_mapping:
                ter_category = f" → {ptkp_to_ter_mapping[status]} (PMK 168/2023)"

            settings.append(
                "ptkp_table",
                {
                    "status_pajak": status,
                    "ptkp_amount": flt(amount),
                    "description": f"{description}{ter_category}",
                },
            )

        # Add tax brackets from config
        tax_brackets = config.get("tax_brackets", [])
        if not tax_brackets:
            debug_log("No tax brackets found in config, using defaults", "PPh 21 Setup")
            # Fallback to defaults
            tax_brackets = [
                {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
                {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
                {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
                {"income_from": 5000000000, "income_to": 0, "tax_rate": 35},
            ]

        for bracket in tax_brackets:
            settings.append(
                "bracket_table",
                {
                    "income_from": flt(bracket["income_from"]),
                    "income_to": flt(bracket["income_to"]),
                    "tax_rate": flt(bracket["tax_rate"]),
                },
            )

        # Save settings
        settings.flags.ignore_permissions = True
        settings.flags.ignore_validate = True
        if settings.is_new():
            settings.insert(ignore_permissions=True)
        else:
            settings.save(ignore_permissions=True)

        # Commit changes
        frappe.db.commit()

        debug_log("PPh 21 Settings configured successfully with PMK 168/2023 notes", "PPh 21 Setup")
        return settings

    except Exception as e:
        frappe.log_error(
            f"Error setting up PPh 21: {str(e)}\n\n" f"Traceback: {frappe.get_traceback()}",
            "PPh 21 Setup Error",
        )
        debug_log(f"Error setting up PPh 21: {str(e)}", "PPh 21 Setup Error", trace=True)
        return None


def setup_pph21_ter(config, force_update=False):
    """
    Setup default TER rates based on PMK-168/PMK.010/2023 using config data

    Args:
        config (dict): Configuration data from defaults.json
        force_update (bool): Force update even if entries exist

    Returns:
        bool: True if successful, False otherwise
    """

    try:
        # Skip if DocType doesn't exist
        if not frappe.db.exists("DocType", "PPh 21 TER Table"):
            debug_log("PPh 21 TER Table DocType doesn't exist", "TER Setup Error")
            return False

        # Check if already setup with new categories
        if not force_update:
            cat_a_exists = frappe.db.exists("PPh 21 TER Table", {"status_pajak": "TER A"})
            cat_b_exists = frappe.db.exists("PPh 21 TER Table", {"status_pajak": "TER B"})
            cat_c_exists = frappe.db.exists("PPh 21 TER Table", {"status_pajak": "TER C"})

            if cat_a_exists and cat_b_exists and cat_c_exists:
                debug_log("TER categories already setup for PMK 168/2023", "TER Setup")
                return True

        # Clear existing TER rates
        try:
            frappe.db.sql("DELETE FROM `tabPPh 21 TER Table`")
            frappe.db.commit()
            debug_log("Cleared existing TER rates", "TER Setup")
        except Exception as e:
            frappe.log_error(
                f"Error clearing existing TER rates: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "TER Setup Error",
            )
            debug_log(f"Error clearing existing TER rates: {str(e)}", "TER Setup Error", trace=True)

        # Get TER rates from config
        ter_rates = config.get("ter_rates", {})
        if not ter_rates:
            debug_log("No TER rates found in config", "TER Setup Error")
            return False

        # Create TER rates
        count = 0
        status_list = list(ter_rates.keys())

        for status in status_list:
            # Determine the highest bracket for each status
            status_rates = ter_rates[status]
            status_rates_count = len(status_rates)

            # Add description prefix based on TER category
            category_description = ""
            if status == "TER A":
                category_description = "PTKP TK/0 (Rp 54 juta/tahun) - "
            elif status == "TER B":
                category_description = "PTKP K/0, TK/1, TK/2, K/1 (Rp 58,5-63 juta/tahun) - "
            elif status == "TER C":
                category_description = "PTKP nilai tinggi (> Rp 63 juta/tahun) - "

            for idx, rate_data in enumerate(status_rates):
                try:
                    # Check if this is the highest bracket
                    is_highest = (
                        (idx == status_rates_count - 1)
                        or (rate_data["income_to"] == 0)
                        or ("is_highest_bracket" in rate_data and rate_data["is_highest_bracket"])
                    )

                    # Create description
                    if rate_data["income_to"] == 0:
                        description = (
                            f"{category_description}{status} > Rp{rate_data['income_from']:,.0f}"
                        )
                    elif rate_data["income_from"] == 0:
                        description = (
                            f"{category_description}{status} ≤ Rp{rate_data['income_to']:,.0f}"
                        )
                    else:
                        description = f"{category_description}{status} Rp{rate_data['income_from']:,.0f}-Rp{rate_data['income_to']:,.0f}"

                    # Check if entry already exists
                    existing = frappe.db.exists(
                        "PPh 21 TER Table",
                        {
                            "status_pajak": status,
                            "income_from": flt(rate_data["income_from"]),
                            "income_to": flt(rate_data["income_to"]),
                        },
                    )

                    if existing:
                        # Update existing entry
                        ter_entry = frappe.get_doc("PPh 21 TER Table", existing)
                        ter_entry.rate = flt(rate_data["rate"])
                        ter_entry.description = description
                        ter_entry.is_highest_bracket = 1 if is_highest else 0
                        ter_entry.pmk_168 = 1  # Flag for PMK 168/2023
                        ter_entry.flags.ignore_permissions = True
                        ter_entry.save(ignore_permissions=True)
                        debug_log(f"Updated TER rate for {status}", "TER Setup")
                    else:
                        # Create TER entry with is_highest_bracket flag
                        ter_entry = frappe.get_doc(
                            {
                                "doctype": "PPh 21 TER Table",
                                "status_pajak": status,
                                "income_from": flt(rate_data["income_from"]),
                                "income_to": flt(rate_data["income_to"]),
                                "rate": flt(rate_data["rate"]),
                                "description": description,
                                "is_highest_bracket": 1 if is_highest else 0,
                                "pmk_168": 1,  # Flag for PMK 168/2023
                            }
                        )

                        ter_entry.flags.ignore_permissions = True
                        ter_entry.insert(ignore_permissions=True)

                    count += 1
                except Exception as e:
                    frappe.log_error(
                        f"Error creating TER rate for {status} with rate {rate_data['rate']}: {str(e)}\n\n"
                        f"Traceback: {frappe.get_traceback()}",
                        "TER Rate Error",
                    )
                    debug_log(
                        f"Error creating TER rate for {status} with rate {rate_data['rate']}: {str(e)}",
                        "TER Rate Error",
                        trace=True,
                    )

        # Commit all changes
        frappe.db.commit()
        debug_log(f"Processed {count} TER rates successfully for PMK 168/2023", "TER Setup")
        return count > 0

    except Exception as e:
        frappe.log_error(
            f"Error setting up TER rates: {str(e)}\n\n" f"Traceback: {frappe.get_traceback()}",
            "TER Setup Error",
        )
        debug_log(f"Error setting up TER rates: {str(e)}", "TER Setup Error", trace=True)
        return False


def setup_income_tax_slab(config):
    """
    Create Income Tax Slab for Indonesia using config data

    Args:
        config (dict): Configuration data from defaults.json

    Returns:
        bool: True if successful, False otherwise
    """

    try:
        # Skip if already exists
        if frappe.db.exists("Income Tax Slab", {"currency": "IDR", "is_default": 1}):
            debug_log("Income Tax Slab already exists", "Tax Slab Setup")
            return True

        # Get company
        company = frappe.db.get_default("company")
        if not company:
            companies = frappe.get_all("Company", pluck="name")
            if companies:
                company = companies[0]
            else:
                debug_log("No company found for income tax slab", "Tax Slab Setup Error")
                return False

        # Get tax brackets from config
        tax_brackets = config.get("tax_brackets", [])
        if not tax_brackets:
            debug_log("No tax brackets found in config, using defaults", "Tax Slab Setup")
            # Fallback to defaults
            tax_brackets = [
                {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
                {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
                {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
                {"income_from": 5000000000, "income_to": 0, "tax_rate": 35},
            ]

        # Create tax slab
        tax_slab = frappe.new_doc("Income Tax Slab")
        tax_slab.name = "Indonesia Income Tax"
        tax_slab.title = "Indonesia Income Tax"
        tax_slab.effective_from = getdate("2023-01-01")
        tax_slab.company = company
        tax_slab.currency = config.get("defaults", {}).get("currency", "IDR")
        tax_slab.is_default = 1
        tax_slab.disabled = 0

        # Add tax brackets
        for bracket in tax_brackets:
            from_amount = flt(bracket["income_from"])
            to_amount = flt(bracket["income_to"])
            percent = flt(bracket["tax_rate"])

            tax_slab.append(
                "slabs",
                {"from_amount": from_amount, "to_amount": to_amount, "percent_deduction": percent},
            )

        # Save with flags to bypass validation
        tax_slab.flags.ignore_permissions = True
        tax_slab.flags.ignore_mandatory = True
        tax_slab.insert()

        debug_log(f"Created income tax slab: {tax_slab.name}", "Tax Slab Setup")
        return True

    except Exception as e:
        # Try an alternative approach
        try:
            # Import the utility function that handles this more robustly
            from payroll_indonesia.utilities.tax_slab import create_income_tax_slab

            result = create_income_tax_slab()

            if result:
                debug_log("Created income tax slab via utility function", "Tax Slab Setup")
                return True

            frappe.log_error(
                f"Failed to create income tax slab: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Tax Slab Setup Error",
            )
            debug_log(
                f"Failed to create income tax slab: {str(e)}", "Tax Slab Setup Error", trace=True
            )
            return False

        except Exception as backup_error:
            frappe.log_error(
                f"Both methods failed to create income tax slab. Original error: {str(e)}\n"
                f"Backup method error: {str(backup_error)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Tax Slab Setup Critical Error",
            )
            debug_log(
                f"Critical error creating income tax slab: {str(backup_error)}",
                "Tax Slab Setup Error",
                trace=True,
            )
            return False


def setup_salary_components(config):
    """
    Create or update salary components using config data

    Args:
        config (dict): Configuration data from defaults.json

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get components from config
        components = config.get("salary_components", {})
        if not components:
            debug_log("No salary components found in config", "Salary Component Setup")
            return False

        # Process earnings and deductions
        success_count = 0
        total_count = 0

        # Process all component types
        for component_type in ["earnings", "deductions"]:
            if component_type not in components:
                continue

            # Process each component definition
            for comp_data in components[component_type]:
                try:
                    total_count += 1

                    # Check if component already exists
                    component_name = comp_data.get("name")

                    if not component_name:
                        debug_log(
                            "Component name is missing in config", "Salary Component Setup Error"
                        )
                        continue

                    if frappe.db.exists("Salary Component", component_name):
                        component = frappe.get_doc("Salary Component", component_name)
                        # Update existing component
                        is_new = False
                    else:
                        # Create new component
                        component = frappe.new_doc("Salary Component")
                        component.salary_component = component_name
                        is_new = True

                    # Set basic properties
                    component.salary_component_abbr = comp_data.get(
                        "abbr", component_name[:3].upper()
                    )
                    component.type = "Earning" if component_type == "earnings" else "Deduction"

                    # Set tax properties if provided
                    if "is_tax_applicable" in comp_data:
                        component.is_tax_applicable = comp_data.get("is_tax_applicable")

                    if "variable_based_on_taxable_salary" in comp_data:
                        component.variable_based_on_taxable_salary = comp_data.get(
                            "variable_based_on_taxable_salary"
                        )

                    if "statistical_component" in comp_data:
                        component.statistical_component = comp_data.get("statistical_component")

                    if "do_not_include_in_total" in comp_data:
                        component.do_not_include_in_total = comp_data.get("do_not_include_in_total")

                    if "exempted" in comp_data:
                        component.exempted = comp_data.get("exempted")

                    # Set description with PMK 168/2023 reference for PPh 21 component
                    if component_name == "PPh 21":
                        component.description = "PPh 21 (PMK 168/2023)"

                        # Set TER flag if supports_ter is in the component data
                        if "supports_ter" in comp_data and comp_data.get("supports_ter"):
                            # Check if custom field exists
                            if frappe.db.exists("Custom Field", "Salary Component-supports_ter"):
                                component.supports_ter = 1
                                component.description += " dengan dukungan TER A,B,C"

                    # Set roundoff
                    component.round_to_the_nearest_integer = 1

                    # Save component
                    component.flags.ignore_permissions = True

                    if is_new:
                        component.insert(ignore_permissions=True)
                        debug_log(
                            f"Created salary component: {component_name}", "Salary Component Setup"
                        )
                    else:
                        component.save(ignore_permissions=True)
                        debug_log(
                            f"Updated salary component: {component_name}", "Salary Component Setup"
                        )

                    success_count += 1

                except Exception as e:
                    frappe.log_error(
                        f"Error creating/updating salary component {comp_data.get('name', 'unknown')}: {str(e)}\n\n"
                        f"Traceback: {frappe.get_traceback()}",
                        "Salary Component Setup Error",
                    )
                    debug_log(
                        f"Error creating/updating salary component {comp_data.get('name', 'unknown')}: {str(e)}",
                        "Salary Component Setup Error",
                        trace=True,
                    )

        # Setup default salary structure
        try:
            from payroll_indonesia.override.salary_structure import (
                create_salary_components,
                create_default_salary_structure,
            )

            # Create components required for default structure
            create_salary_components()
            # Create default structure
            create_default_salary_structure()
            debug_log("Created default salary structure", "Salary Component Setup")
        except Exception as e:
            frappe.log_error(
                f"Error creating default salary structure: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Structure Setup Error",
            )
            debug_log(
                f"Error creating default salary structure: {str(e)}",
                "Salary Structure Setup Error",
                trace=True,
            )

        # Log summary
        debug_log(
            f"Processed {success_count} of {total_count} salary components successfully",
            "Salary Component Setup",
        )
        return success_count > 0

    except Exception as e:
        frappe.log_error(
            f"Error setting up salary components: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Salary Component Setup Error",
        )
        debug_log(
            f"Error setting up salary components: {str(e)}",
            "Salary Component Setup Error",
            trace=True,
        )
        return False


def display_installation_summary(results, config):
    """
    Display installation summary

    Args:
        results (dict): Results of each setup step
        config (dict): Configuration data
    """

    debug_log(
        "=== PAYROLL INDONESIA INSTALLATION SUMMARY ===\n"
        f"Accounts setup: {'Success' if results.get('accounts') else 'Failed'}\n"
        f"Suppliers setup: {'Success' if results.get('suppliers') else 'Failed'}\n"
        f"PPh 21 settings: {'Success' if results.get('pph21_settings') else 'Failed'}\n"
        f"Salary components: {'Success' if results.get('salary_components') else 'Failed'}\n"
        f"BPJS settings: {'Success' if results.get('bpjs_setup') else 'Failed'}\n"
        "===================================\n"
        "PMK 168/2023 Implementation: DONE\n"
        "===================================",
        "Installation Summary",
    )
