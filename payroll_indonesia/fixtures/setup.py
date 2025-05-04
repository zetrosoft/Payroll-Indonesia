# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-04 00:35:28 by dannyaudian

import frappe
from frappe import _
from frappe.utils import getdate, flt, now_datetime
import json
import os

# Constants for default values
DEFAULT_CONFIG_PATH = "payroll_indonesia/payroll_indonesia/config/defaults.json"
DEFAULT_BPJS_VALUES = {
    "kesehatan_employee_percent": 1.0,
    "kesehatan_employer_percent": 4.0,
    "kesehatan_max_salary": 12000000.0,
    "jht_employee_percent": 2.0,
    "jht_employer_percent": 3.7,
    "jp_employee_percent": 1.0,
    "jp_employer_percent": 2.0,
    "jp_max_salary": 9077600.0,
    "jkk_percent": 0.24,
    "jkm_percent": 0.3
}

def before_install():
    """Setup requirements before installing the app"""
    try:
        # Check if system is ready for installation
        check_system_readiness()
    except Exception as e:
        frappe.log_error(str(e)[:100], "Payroll Indonesia Installation Error")

def after_install():
    """Setup requirements after installing the app with improved error handling"""
    frappe.logger().info("Starting Payroll Indonesia after_install process")
    
    # Track setup results
    results = {
        "accounts": False,
        "suppliers": False,
        "pph21_settings": False,
        "ter_rates": False,
        "tax_slab": False,
        "bpjs_setup": False
    }
    
    try:
        # Create accounts first (required for salary components)
        results["accounts"] = create_accounts()
        frappe.logger().info("Account setup completed")
    except Exception as e:
        frappe.log_error(str(e)[:100], "Account Setup Error")
        
    try:
        # Setup suppliers
        results["suppliers"] = create_supplier_group()
        frappe.logger().info("Supplier group setup completed")
    except Exception as e:
        frappe.log_error(str(e)[:100], "Supplier Setup Error")
        
    try:
        # Setup tax configuration
        pph21_settings = setup_pph21_defaults()
        results["pph21_settings"] = bool(pph21_settings)
        frappe.logger().info("PPh 21 setup completed")
    except Exception as e:
        frappe.log_error(str(e)[:100], "PPh 21 Setup Error")
        
    try:
        # Setup TER rates
        results["ter_rates"] = setup_pph21_ter()
        frappe.logger().info("TER rates setup completed")
    except Exception as e:
        frappe.log_error(str(e)[:100], "TER Setup Error")
        
    try:
        # Setup tax slab
        results["tax_slab"] = setup_income_tax_slab()
        frappe.logger().info("Tax slab setup completed")
    except Exception as e:
        frappe.log_error(str(e)[:100], "Tax Slab Setup Error")
    
    try:
        # Setup BPJS
        results["bpjs_setup"] = setup_bpjs()
        frappe.logger().info("BPJS setup completed")
    except Exception as e:
        frappe.log_error(str(e)[:100], "BPJS Setup Error")
        
    # Commit all changes
    frappe.db.commit()
    
    # Display installation summary
    display_installation_summary(results)

def display_installation_summary(results):
    """Display summary of installation results"""
    success_items = []
    failed_items = []
    
    for item, success in results.items():
        if success:
            success_items.append(_(item))
        else:
            failed_items.append(_(item))
    
    if success_items:
        success_msg = _("Payroll Indonesia has been installed. Successfully configured: {0}").format(
            ", ".join(success_items)
        )
        indicator = "green" if len(failed_items) == 0 else "yellow"
        frappe.msgprint(success_msg, indicator=indicator, title=_("Installation Complete"))
    
    if failed_items:
        failed_msg = _("The following components had setup issues: {0}").format(
            ", ".join(failed_items)
        )
        frappe.msgprint(failed_msg, indicator="red", title=_("Setup Issues"))

def check_system_readiness():
    """
    Check if system is ready for Payroll Indonesia installation
    
    Returns:
        bool: True if ready, False otherwise
    """
    # Check if required DocTypes exist
    required_core_doctypes = [
        "Salary Component", "Salary Structure", "Salary Slip", 
        "Employee", "Company", "Account"
    ]
    
    missing_doctypes = []
    for doctype in required_core_doctypes:
        if not frappe.db.exists("DocType", doctype):
            missing_doctypes.append(doctype)
            
    if missing_doctypes:
        frappe.log_error(
            f"Required DocTypes missing: {', '.join(missing_doctypes)}",
            "System Readiness Check"
        )
        frappe.logger().warning(f"Missing DocTypes: {', '.join(missing_doctypes)}")
        
    # Check if company exists
    if not frappe.get_all("Company"):
        frappe.log_error("No company found", "System Readiness Check")
        frappe.logger().warning("No company found. Some setup steps may fail.")
        
    # Return True so installation can continue with warnings
    return True

def create_accounts():
    """
    Create required Accounts for Indonesian payroll management
    
    Returns:
        bool: True if successful, False otherwise
    """
    # Define accounts to create
    accounts = [
        # Expense Accounts
        {"account_name": "Beban Gaji Pokok", "parent_account": "Direct Expenses", "account_type": "Expense"},
        {"account_name": "Beban Tunjangan Makan", "parent_account": "Direct Expenses", "account_type": "Expense"},
        {"account_name": "Beban Tunjangan Transport", "parent_account": "Direct Expenses", "account_type": "Expense"},
        {"account_name": "Beban Insentif", "parent_account": "Direct Expenses", "account_type": "Expense"},
        {"account_name": "Beban Bonus", "parent_account": "Direct Expenses", "account_type": "Expense"},
        {"account_name": "Beban BPJS JHT", "parent_account": "Direct Expenses", "account_type": "Expense"},
        {"account_name": "Beban BPJS JP", "parent_account": "Direct Expenses", "account_type": "Expense"},
        {"account_name": "Beban BPJS JKK", "parent_account": "Direct Expenses", "account_type": "Expense"},
        {"account_name": "Beban BPJS JKM", "parent_account": "Direct Expenses", "account_type": "Expense"},
        {"account_name": "Beban BPJS Kesehatan", "parent_account": "Direct Expenses", "account_type": "Expense"},
        # Liability Accounts
        {"account_name": "Hutang PPh 21", "parent_account": "Duties and Taxes", "account_type": "Tax"},
        {"account_name": "Hutang BPJS JHT", "parent_account": "Duties and Taxes", "account_type": "Payable"},
        {"account_name": "Hutang BPJS JP", "parent_account": "Duties and Taxes", "account_type": "Payable"},
        {"account_name": "Hutang BPJS Kesehatan", "parent_account": "Duties and Taxes", "account_type": "Payable"},
        {"account_name": "Hutang BPJS JKK", "parent_account": "Duties and Taxes", "account_type": "Payable"},
        {"account_name": "Hutang BPJS JKM", "parent_account": "Duties and Taxes", "account_type": "Payable"}
    ]
    
    # Get default company
    company = frappe.defaults.get_defaults().get("company")
    if not company:
        companies = frappe.get_all("Company", pluck="name")
        if companies:
            company = companies[0]
        else:
            frappe.logger().warning("No company found. Cannot create accounts.")
            return False
        
    # Get company abbreviation
    company_abbr = frappe.db.get_value("Company", company, "abbr")
    if not company_abbr:
        frappe.logger().warning(f"Company {company} has no abbreviation")
        return False
    
    # Track accounts
    created_accounts = []
    failed_accounts = []
        
    # Create each account
    for account in accounts:
        try:
            # Find parent account
            parent_account = find_parent_account(company, account["parent_account"], company_abbr, account["account_type"])
            if not parent_account:
                failed_accounts.append(account["account_name"])
                continue
                
            # Create account using standardized function
            account_name = create_account(
                company=company,
                account_name=account["account_name"],
                account_type=account["account_type"],
                parent=parent_account
            )
            
            if account_name:
                created_accounts.append(account["account_name"])
            else:
                failed_accounts.append(account["account_name"])
            
        except Exception as e:
            frappe.log_error(f"Error creating account {account['account_name']}: {str(e)[:100]}", "Account Creation Error")
            failed_accounts.append(account["account_name"])
    
    # Log summary
    if created_accounts:
        frappe.logger().info(f"Created {len(created_accounts)} accounts")
        
    if failed_accounts:
        frappe.log_error(f"Failed to create {len(failed_accounts)} accounts", "Account Creation Summary")
        
    return len(failed_accounts) < len(accounts) // 2  # Success if less than half failed

def create_account(company, account_name, account_type, parent):
    """
    Create GL Account if not exists
    
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
        timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
        frappe.logger().info(f"[{timestamp}] Creating account: {full_account_name}")
        
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
        
        return full_account_name
        
    except Exception as e:
        frappe.log_error(f"Error creating account {account_name}: {str(e)[:100]}", "Account Creation Error")
        return None

def find_parent_account(company, parent_name, company_abbr, account_type):
    """
    Find parent account with multiple fallback options
    
    Args:
        company: Company name
        parent_name: Parent account name
        company_abbr: Company abbreviation
        account_type: Account type to find appropriate parent
        
    Returns:
        str: Parent account name if found, None otherwise
    """
    # Try exact name
    parent = frappe.db.get_value("Account", {"account_name": parent_name, "company": company}, "name")
    if parent:
        return parent
        
    # Try with company abbreviation
    parent = frappe.db.get_value("Account", {"name": f"{parent_name} - {company_abbr}"}, "name")
    if parent:
        return parent
        
    # Try any group account of correct type
    root_type = "Expense" if account_type == "Expense" else "Liability"
    parents = frappe.get_all(
        "Account", 
        filters={"company": company, "is_group": 1, "root_type": root_type},
        pluck="name",
        limit=1
    )
    if parents:
        return parents[0]
        
    return None

def create_supplier_group():
    """
    Create Government supplier group for tax and BPJS entities
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Skip if already exists
        if frappe.db.exists("Supplier Group", "Government"):
            return True
            
        # Create the group
        group = frappe.new_doc("Supplier Group")
        group.supplier_group_name = "Government"
        group.parent_supplier_group = "All Supplier Groups"
        group.is_group = 0
        group.insert(ignore_permissions=True)
        
        frappe.logger().info("Created Government supplier group")
        return True
        
    except Exception as e:
        frappe.log_error(f"Failed to create supplier group: {str(e)[:100]}", "Supplier Setup Error")
        return False

def setup_pph21_defaults():
    """
    Setup default PPh 21 configuration with TER method
    
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
        
        # Set TER as default calculation method
        settings.calculation_method = "TER"
        settings.use_ter = 1
        settings.ter_notes = "Tarif Efektif Rata-rata (TER) sesuai PMK-168/PMK.010/2023"
        
        # Add PTKP values
        ptkp_values = {
            "TK0": 54000000,  # tidak kawin, 0 tanggungan
            "TK1": 58500000,  # tidak kawin, 1 tanggungan
            "TK2": 63000000,  # tidak kawin, 2 tanggungan
            "TK3": 67500000,  # tidak kawin, 3 tanggungan
            "K0": 58500000,   # kawin, 0 tanggungan
            "K1": 63000000,   # kawin, 1 tanggungan
            "K2": 67500000,   # kawin, 2 tanggungan
            "K3": 72000000,   # kawin, 3 tanggungan
            "HB0": 112500000, # kawin penghasilan istri digabung, 0 tanggungan
            "HB1": 117000000, # kawin penghasilan istri digabung, 1 tanggungan
            "HB2": 121500000, # kawin penghasilan istri digabung, 2 tanggungan
            "HB3": 126000000  # kawin penghasilan istri digabung, 3 tanggungan
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
                
            settings.append("ptkp_table", {
                "status_pajak": status,
                "ptkp_amount": flt(amount),
                "description": description
            })
        
        # Add tax brackets
        brackets = [
            {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
            {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
            {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
            {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
            {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
        ]
        
        for bracket in brackets:
            settings.append("bracket_table", {
                "income_from": flt(bracket["income_from"]),
                "income_to": flt(bracket["income_to"]),
                "tax_rate": flt(bracket["tax_rate"])
            })
        
        # Save settings
        settings.flags.ignore_permissions = True
        settings.flags.ignore_validate = True
        if settings.is_new():
            settings.insert()
        else:
            settings.save()
            
        frappe.logger().info("PPh 21 Settings configured successfully")
        return settings
        
    except Exception as e:
        frappe.log_error(f"Error setting up PPh 21: {str(e)[:100]}", "PPh 21 Setup Error")
        return None

def setup_pph21_ter():
    """
    Setup default TER rates based on PMK-168/PMK.010/2023
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Skip if DocType doesn't exist
        if not frappe.db.exists("DocType", "PPh 21 TER Table"):
            return False
        
        # Clear existing TER rates
        try:
            frappe.db.sql("DELETE FROM `tabPPh 21 TER Table`")
            frappe.db.commit()
        except Exception:
            pass
        
        # Load TER rates from JSON file
        ter_rates = get_ter_rates()
        if not ter_rates:
            return False
            
        # Create TER rates
        count = 0
        status_list = list(ter_rates.keys())
        
        for status in status_list:
            for rate_data in ter_rates[status]:
                try:
                    # Create description
                    if rate_data["income_to"] == 0:
                        description = f"{status} > Rp{rate_data['income_from']:,.0f}"
                    elif rate_data["income_from"] == 0:
                        description = f"{status} ≤ Rp{rate_data['income_to']:,.0f}"
                    else:
                        description = f"{status} Rp{rate_data['income_from']:,.0f}-Rp{rate_data['income_to']:,.0f}"
                    
                    frappe.get_doc({
                        "doctype": "PPh 21 TER Table",
                        "status_pajak": status,
                        "income_from": flt(rate_data["income_from"]),
                        "income_to": flt(rate_data["income_to"]),
                        "rate": flt(rate_data["rate"]),
                        "description": description
                    }).insert(ignore_permissions=True)
                    
                    count += 1
                except Exception as e:
                    frappe.log_error(f"Error creating TER rate: {str(e)[:100]}", "TER Rate Error")
        
        frappe.db.commit()
        frappe.logger().info(f"Created {count} TER rates")
        return count > 0
            
    except Exception as e:
        frappe.log_error(f"Error setting up TER rates: {str(e)[:100]}", "TER Setup Error")
        return False

def get_ter_rates():
    """
    Get TER rates either from file or hardcoded defaults
    
    Returns:
        dict: TER rates by status
    """
    try:
        # Check if file exists
        ter_path = frappe.get_app_path("payroll_indonesia", "payroll_indonesia", "config", "ter_rates.json")
        if os.path.exists(ter_path):
            with open(ter_path, "r") as f:
                return json.load(f)
    except Exception:
        pass
        
    # Return hardcoded minimal rates (TK0 & K0 only for brevity)
    return {
        "TK0": [
            {"income_from": 0, "income_to": 4500000, "rate": 0},
            {"income_from": 4500000, "income_to": 5000000, "rate": 0.5},
            {"income_from": 5000000, "income_to": 6000000, "rate": 1.0},
            {"income_from": 6000000, "income_to": 7000000, "rate": 1.75},
            {"income_from": 7000000, "income_to": 8000000, "rate": 2.5},
            {"income_from": 8000000, "income_to": 9000000, "rate": 3.0},
            {"income_from": 9000000, "income_to": 10000000, "rate": 3.5},
            {"income_from": 10000000, "income_to": 15000000, "rate": 4.5},
            {"income_from": 15000000, "income_to": 20000000, "rate": 5.5},
            {"income_from": 20000000, "income_to": 500000000, "rate": 7.5},
            {"income_from": 500000000, "income_to": 0, "rate": 10.0}
        ],
        "K0": [
            {"income_from": 0, "income_to": 4875000, "rate": 0},
            {"income_from": 4875000, "income_to": 5500000, "rate": 0.5},
            {"income_from": 5500000, "income_to": 6500000, "rate": 1.0},
            {"income_from": 6500000, "income_to": 7500000, "rate": 1.75},
            {"income_from": 7500000, "income_to": 8500000, "rate": 2.25},
            {"income_from": 8500000, "income_to": 9500000, "rate": 2.75},
            {"income_from": 9500000, "income_to": 11000000, "rate": 3.25},
            {"income_from": 11000000, "income_to": 15500000, "rate": 4.0},
            {"income_from": 15500000, "income_to": 21500000, "rate": 5.0},
            {"income_from": 21500000, "income_to": 500000000, "rate": 7.0},
            {"income_from": 500000000, "income_to": 0, "rate": 9.5}
        ]
    }

def setup_income_tax_slab():
    """
    Create Income Tax Slab for Indonesia
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Skip if already exists
        if frappe.db.exists("Income Tax Slab", {"currency": "IDR", "is_default": 1}):
            return True
        
        # Get company
        company = frappe.db.get_default("company")
        if not company:
            companies = frappe.get_all("Company", pluck="name")
            if companies:
                company = companies[0]
            else:
                return False
        
        # Create tax slab
        tax_slab = frappe.new_doc("Income Tax Slab")
        tax_slab.title = "Indonesia Income Tax" 
        tax_slab.effective_from = getdate("2023-01-01")
        tax_slab.company = company
        tax_slab.currency = "IDR"
        tax_slab.is_default = 1
        tax_slab.disabled = 0

        # Add tax brackets
        tax_slab.append("slabs", {"from_amount": 0, "to_amount": 60000000, "percent_deduction": 5})
        tax_slab.append("slabs", {"from_amount": 60000000, "to_amount": 250000000, "percent_deduction": 15})
        tax_slab.append("slabs", {"from_amount": 250000000, "to_amount": 500000000, "percent_deduction": 25})
        tax_slab.append("slabs", {"from_amount": 500000000, "to_amount": 5000000000, "percent_deduction": 30})
        tax_slab.append("slabs", {"from_amount": 5000000000, "to_amount": 0, "percent_deduction": 35})
            
        # Save
        tax_slab.insert(ignore_permissions=True)
        frappe.db.commit()
        
        frappe.logger().info("Created Income Tax Slab for Indonesia")
        return True
        
    except Exception as e:
        frappe.log_error(f"Error creating Income Tax Slab: {str(e)[:100]}", "Tax Slab Setup Error")
        return False

def setup_bpjs():
    """
    Setup BPJS configurations and accounts
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create BPJS Settings
        settings = create_bpjs_settings()
        if not settings:
            return False
            
        # Let BPJS Settings handle account and mapping creation
        settings.setup_accounts()
        frappe.db.commit()
        
        return True
    except Exception as e:
        frappe.log_error(f"Error setting up BPJS: {str(e)[:100]}", "BPJS Setup Error")
        return False

def create_bpjs_settings():
    """
    Create and configure BPJS Settings
    
    Returns:
        object: BPJS Settings document if successful, None otherwise
    """
    try:
        # Check if already exists
        if frappe.db.exists("BPJS Settings", "BPJS Settings"):
            settings = frappe.get_doc("BPJS Settings", "BPJS Settings")
        else:
            # Load defaults from config or use hardcoded values
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
        
        frappe.logger().info("BPJS Settings configured")
        return settings
        
    except Exception as e:
        frappe.log_error(f"Error creating BPJS Settings: {str(e)[:100]}", "BPJS Setup Error")
        return None

def get_default_bpjs_values():
    """
    Get default BPJS values from config file or use defaults
    
    Returns:
        dict: Default BPJS values
    """
    try:
        # Try to load from file
        config_path = frappe.get_app_path("payroll_indonesia", DEFAULT_CONFIG_PATH)
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                values = json.load(f)
                
                # Validate required keys
                for key in DEFAULT_BPJS_VALUES:
                    if key not in values:
                        values[key] = DEFAULT_BPJS_VALUES[key]
                        
                return values
    except Exception:
        pass
        
    # Return hardcoded defaults
    return DEFAULT_BPJS_VALUES

def create_account_hooks():
    """
    Create hooks for account updates
    
    Returns:
        bool: True if successful, False otherwise
    """
    account_hooks_path = frappe.get_app_path("payroll_indonesia", "payroll_indonesia", "account_hooks.py")
    
    try:
        with open(account_hooks_path, "w") as f:
            f.write("""import frappe
from frappe.utils import now_datetime

def account_on_update(doc, method=None):
    \"\"\"Hook when accounts are updated\"\"\"
    if doc.account_type in ["Payable", "Expense", "Liability"] and ("BPJS" in doc.account_name):
        # Update BPJS mappings
        update_bpjs_mappings(doc)

def update_bpjs_mappings(account_doc):
    \"\"\"Update BPJS mappings that use this account\"\"\"
    # Get all mappings for this company
    mappings = frappe.get_all(
        "BPJS Account Mapping",
        filters={"company": account_doc.company},
        pluck="name"
    )
    
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    
    for mapping_name in mappings:
        mapping = frappe.get_doc("BPJS Account Mapping", mapping_name)
        
        # Check all account fields for a match
        account_fields = [
            "kesehatan_employee_account", "jht_employee_account", "jp_employee_account",
            "kesehatan_employer_debit_account", "jht_employer_debit_account",
            "jp_employer_debit_account", "jkk_employer_debit_account", "jkm_employer_debit_account",
            "kesehatan_employer_credit_account", "jht_employer_credit_account",
            "jp_employer_credit_account", "jkk_employer_credit_account", "jkm_employer_credit_account"
        ]
        
        updated = False
        for field in account_fields:
            if hasattr(mapping, field) and getattr(mapping, field) == account_doc.name:
                # Account is being used in this mapping
                updated = True
        
        if updated:
            # Clear cache for this mapping
            frappe.cache().delete_value(f"bpjs_mapping_{mapping.company}")
            frappe.logger().info(f"[{timestamp}] Cleared cache for BPJS mapping {mapping_name} due to account update")
""")
        return True
    except Exception as e:
        frappe.log_error(f"Error creating account_hooks.py: {str(e)[:100]}", "Setup Error")
        return False

def debug_log(message, title=None, max_length=500):
    """
    Debug logging helper with consistent format
    
    Args:
        message: Message to log
        title: Optional title/context for the log
        max_length: Maximum message length (default: 500)
    """
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    
    # Truncate if message is too long to avoid memory issues
    message = str(message)[:max_length]
    
    if title:
        log_message = f"[{timestamp}] [{title}] {message}"
    else:
        log_message = f"[{timestamp}] {message}"
        
    frappe.logger().debug(f"[SETUP] {log_message}")