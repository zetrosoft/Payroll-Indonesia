# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 03:15:12 by dannyaudian

import frappe
from frappe import _
from frappe.utils import getdate, flt

def before_install():
    """Setup requirements before installing the app"""
    try:
        # Check if system is ready for installation
        check_system_readiness()
    except Exception as e:
        frappe.log_error(f"Error in before_install: {str(e)}", "Payroll Indonesia Installation Error")

def after_install():
    """Setup requirements after installing the app with improved error handling"""
    frappe.logger().info("Starting Payroll Indonesia after_install process")
    
    # Create accounts first (required for salary components)
    account_success = False
    try:
        create_accounts()
        account_success = True
        frappe.logger().info("Successfully created accounts for Payroll Indonesia")
    except Exception as e:
        frappe.log_error(f"Error creating accounts: {str(e)}", "Account Creation Error")
        frappe.msgprint(_("Warning: Some accounts could not be created: {0}").format(str(e)))
    
    # Setup additional requirements
    supplier_success = False
    try:
        create_supplier_group()
        supplier_success = True
        frappe.logger().info("Successfully created supplier groups for Payroll Indonesia")
    except Exception as e:
        frappe.log_error(f"Error creating supplier group: {str(e)}", "Supplier Group Creation Error")
        frappe.msgprint(_("Warning: Supplier group could not be created: {0}").format(str(e)))
    
    # Setup Settings immediately (synchronously)
    pph21_settings = None
    try:
        pph21_settings = setup_pph21_defaults()
        frappe.logger().info("Successfully set up PPh 21 defaults")
    except Exception as e:
        frappe.log_error(f"Error setting up PPh 21 defaults: {str(e)}", "PPh 21 Setup Error")
        frappe.msgprint(_("Warning: PPh 21 Settings could not be configured: {0}").format(str(e)))
        
    ter_success = False
    try:
        setup_pph21_ter()
        ter_success = True
        frappe.logger().info("Successfully set up PPh 21 TER rates")
    except Exception as e:
        frappe.log_error(f"Error setting up PPh 21 TER: {str(e)}", "PPh 21 TER Setup Error")
        frappe.msgprint(_("Warning: PPh 21 TER rates could not be configured: {0}").format(str(e)))
        
    tax_slab_success = False
    try:
        setup_income_tax_slab()
        tax_slab_success = True
        frappe.logger().info("Successfully set up income tax slab")
    except Exception as e:
        frappe.log_error(f"Error setting up income tax slab: {str(e)}", "Tax Slab Setup Error")
        frappe.msgprint(_("Warning: Income tax slab could not be configured: {0}").format(str(e)))
    
    # Summary of installation
    success_items = []
    if account_success:
        success_items.append(_("accounts"))
    if supplier_success:
        success_items.append(_("supplier groups"))
    if pph21_settings:
        success_items.append(_("PPh 21 Settings"))
    if ter_success:
        success_items.append(_("TER rates"))
    if tax_slab_success:
        success_items.append(_("income tax slab"))
        
    # Display success message with details
    if success_items:
        success_msg = _(
            "Payroll Indonesia has been installed. Successfully configured: {0}"
        ).format(", ".join(success_items))
        
        indicator = "green" if len(success_items) >= 3 else "yellow"
        frappe.msgprint(success_msg, indicator=indicator, title=_("Installation Complete"))
    else:
        frappe.msgprint(
            _("Payroll Indonesia has been installed, but with configuration errors. Check error logs."),
            indicator="red", 
            title=_("Installation With Errors")
        )

def check_system_readiness():
    """Check if system is ready for Payroll Indonesia installation"""
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
            f"Required DocTypes missing for Payroll Indonesia: {', '.join(missing_doctypes)}",
            "Installation Prerequisites Error"
        )
        # Continue but log warning
        frappe.logger().warning(f"Some required DocTypes missing: {', '.join(missing_doctypes)}")
        
    # Check if company exists
    if not frappe.get_all("Company"):
        frappe.log_error(
            "No company found. Please create a company before installing Payroll Indonesia.",
            "Installation Prerequisites Error"
        )
        frappe.logger().warning("No company found. Some setup steps may fail.")
        
    # Check if fiscal year is set
    # fy = frappe.db.get_single_value('Global Defaults', 'current_fiscal_year')
    # if not fy:
    #     frappe.log_error(
    #         "Current fiscal year not set. Please set up a fiscal year before installing Payroll Indonesia.",
    #         "Installation Prerequisites Error" 
    #     )
    #     frappe.logger().warning("Current fiscal year not set. Some setup steps may fail.")
        
def create_accounts():
    """
    Create required Accounts for Indonesian payroll management
    with improved validation and error handling
    
    This creates all necessary expense accounts for salary components
    and liability accounts for taxes and social insurance
    """
    # Define accounts to create
    accounts = [
        # Expense Accounts
        {"account_name": "Beban Gaji Pokok", "parent_account": "Direct Expenses", "account_type": "Expense Account"},
        {"account_name": "Beban Tunjangan Makan", "parent_account": "Direct Expenses", "account_type": "Expense Account"},
        {"account_name": "Beban Tunjangan Transport", "parent_account": "Direct Expenses", "account_type": "Expense Account"},
        {"account_name": "Beban Insentif", "parent_account": "Direct Expenses", "account_type": "Expense Account"},
        {"account_name": "Beban Bonus", "parent_account": "Direct Expenses", "account_type": "Expense Account"},
        {"account_name": "Beban BPJS JHT", "parent_account": "Direct Expenses", "account_type": "Expense Account"},
        {"account_name": "Beban BPJS JP", "parent_account": "Direct Expenses", "account_type": "Expense Account"},
        {"account_name": "Beban BPJS JKK", "parent_account": "Direct Expenses", "account_type": "Expense Account"},
        {"account_name": "Beban BPJS JKM", "parent_account": "Direct Expenses", "account_type": "Expense Account"},
        {"account_name": "Beban BPJS Kesehatan", "parent_account": "Direct Expenses", "account_type": "Expense Account"},
        # Liability Accounts
        {"account_name": "Hutang PPh 21", "parent_account": "Duties and Taxes", "account_type": "Tax"},
        {"account_name": "Hutang BPJS JHT", "parent_account": "Accounts Payable", "account_type": "Payable"},
        {"account_name": "Hutang BPJS JP", "parent_account": "Accounts Payable", "account_type": "Payable"},
        {"account_name": "Hutang BPJS Kesehatan", "parent_account": "Accounts Payable", "account_type": "Payable"}
    ]
    
    # Get default company
    company = frappe.defaults.get_defaults().get("company")
    if not company:
        companies = frappe.get_all("Company", fields=["name"])
        if companies:
            company = companies[0].name
        else:
            frappe.log_error("No company found. Cannot create accounts.", "Account Creation Error")
            raise ValueError(_("No company found. Please create a company first."))
        
    # Get company abbreviation
    company_abbr = frappe.db.get_value("Company", company, "abbr")
    if not company_abbr:
        frappe.log_error(f"Company {company} has no abbreviation", "Account Creation Error")
        raise ValueError(_("Company {0} has no abbreviation defined.").format(company))
    
    # Track created accounts
    created_accounts = []
    failed_accounts = []
        
    # Loop through accounts list and create each account
    for account in accounts:
        try:
            # Get the full parent account name including company abbreviation
            parent_account_filter = {
                "account_name": account["parent_account"],
                "company": company
            }
            
            # Try exact match first
            parent_account = frappe.db.get_value("Account", parent_account_filter, "name")
            
            # If not found, try with company abbreviation
            if not parent_account:
                parent_account = frappe.db.get_value(
                    "Account", 
                    {"name": f"{account['parent_account']} - {company_abbr}"}, 
                    "name"
                )
                
            # If still not found, try a broader search
            if not parent_account:
                possible_parents = frappe.get_all(
                    "Account", 
                    filters={"company": company, "is_group": 1, "account_type": account["account_type"]},
                    fields=["name"]
                )
                
                if possible_parents:
                    parent_account = possible_parents[0].name
                    frappe.logger().warning(
                        f"Parent account {account['parent_account']} not found, using {parent_account} instead"
                    )
                
            if not parent_account:
                frappe.log_error(
                    f"Parent account {account['parent_account']} not found for company {company}", 
                    "Account Creation Error"
                )
                failed_accounts.append(account["account_name"])
                continue
                
            # Create the account name with company abbreviation
            account_name = f"{account['account_name']} - {company_abbr}"
            
            # Skip if account already exists
            if frappe.db.exists("Account", account_name):
                frappe.logger().info(f"Account {account_name} already exists, skipping creation")
                continue
                
            # Create the account
            doc = frappe.new_doc("Account")
            doc.account_name = account["account_name"]
            doc.parent_account = parent_account
            doc.account_type = account["account_type"]
            doc.company = company
            doc.is_group = 0
            doc.insert(ignore_permissions=True)
            
            created_accounts.append(account["account_name"])
            
        except Exception as e:
            frappe.log_error(f"Error creating account {account['account_name']}: {str(e)}", "Account Creation Error")
            failed_accounts.append(account["account_name"])
    
    # Log summary
    if created_accounts:
        frappe.logger().info(f"Created {len(created_accounts)} accounts: {', '.join(created_accounts)}")
        
    if failed_accounts:
        frappe.log_error(
            f"Failed to create {len(failed_accounts)} accounts: {', '.join(failed_accounts)}",
            "Account Creation Summary"
        )
        
    if not created_accounts and not failed_accounts:
        frappe.logger().info("No new accounts were created, all accounts already exist")
        
    return created_accounts

def create_supplier_group():
    """
    Create Government supplier group if not exists
    with improved error handling
    
    This group is needed for government-related suppliers like tax office and BPJS
    """
    try:
        # Check if DocType exists
        if not frappe.db.exists("DocType", "Supplier Group"):
            frappe.log_error("Supplier Group DocType not found", "Supplier Group Creation Error")
            return False
            
        # Check if group already exists
        if frappe.db.exists("Supplier Group", "Government"):
            frappe.logger().info("Government supplier group already exists")
            return True
            
        # Check if parent group exists
        if not frappe.db.exists("Supplier Group", "All Supplier Groups"):
            frappe.log_error(
                "Parent group 'All Supplier Groups' not found",
                "Supplier Group Creation Error"
            )
            return False
            
        # Create the group
        group = frappe.new_doc("Supplier Group")
        group.supplier_group_name = "Government"
        group.parent_supplier_group = "All Supplier Groups"
        group.is_group = 0
        group.insert()
        
        frappe.logger().info("Successfully created Government supplier group")
        return True
        
    except Exception as e:
        frappe.log_error(f"Failed to create Government supplier group: {str(e)}", "Supplier Group Creation Error")
        return False

def setup_pph21_defaults():
    """
    Setup default PPh 21 configuration with TER method as default
    with improved validation and error handling

    Sets up the income tax settings with complete PTKP values and tax brackets
    according to Indonesian tax regulations
    
    Returns:
        object: PPh 21 Settings document or None on error
    """
    try:
        # Check if PPh 21 Settings DocType exists
        if not frappe.db.exists("DocType", "PPh 21 Settings"):
            frappe.log_error("DocType 'PPh 21 Settings' tidak ditemukan. Pastikan DocType sudah diinstall dengan benar.", "PPh 21 Setup Error")
            return None
        
        # Check if settings already exist
        settings = None
        settings_exist = frappe.db.exists("PPh 21 Settings", "PPh 21 Settings")
        
        if settings_exist:
            # Get existing settings
            settings = frappe.get_doc("PPh 21 Settings", "PPh 21 Settings")
            frappe.logger().info("PPh 21 Settings already exists, updating configuration...")
            
            # Verify required child tables exist
            if not hasattr(settings, 'ptkp_table') or not hasattr(settings, 'bracket_table'):
                frappe.log_error(
                    "PPh 21 Settings missing required child tables (ptkp_table or bracket_table)",
                    "PPh 21 Setup Error"
                )
                return None
                
            # Clear existing tables to avoid duplicates
            settings.ptkp_table = []
            settings.bracket_table = []
        else:
            # Create new settings document
            settings = frappe.new_doc("PPh 21 Settings")
        
        # Set TER as default calculation method
        settings.calculation_method = "TER"
        settings.use_ter = 1
        settings.ter_notes = "Tarif Efektif Rata-rata (TER) sesuai PMK-168/PMK.010/2023 tentang Tarif Rata-rata Pajak Penghasilan Pasal 21 Undang-Undang Nomor 7 Tahun 2021"
        
        # Add complete PTKP values (sesuai PMK terbaru)
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
        
        # Add each PTKP value to the settings
        for status, amount in ptkp_values.items():
            description = ""
            
            # Add description for better readability
            if status.startswith("TK"):
                tanggungan = status[2:]
                description = f"Tidak Kawin, {tanggungan} Tanggungan"
            elif status.startswith("K"):
                tanggungan = status[1:]
                description = f"Kawin, {tanggungan} Tanggungan" 
            elif status.startswith("HB"):
                tanggungan = status[2:]
                description = f"Kawin (Penghasilan Istri Digabung), {tanggungan} Tanggungan"
                
            # Add to ptkp_table
            ptkp_row = {
                "status_pajak": status,
                "ptkp_amount": flt(amount),
                "description": description
            }
                
            settings.append("ptkp_table", ptkp_row)
        
        # Add tax brackets (sesuai pasal 17 UU HPP)
        brackets = [
            {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
            {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
            {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
            {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
            {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
        ]
        
        # Add each tax bracket to the settings
        for bracket in brackets:
            settings.append("bracket_table", {
                "income_from": flt(bracket["income_from"]),
                "income_to": flt(bracket["income_to"]),
                "tax_rate": flt(bracket["tax_rate"])
            })
        
        # Save settings
        if settings_exist:
            settings.save(ignore_permissions=True)
            frappe.logger().info("Updated existing PPh 21 Settings")
        else:
            settings.insert(ignore_permissions=True)
            frappe.logger().info("Created new PPh 21 Settings")
            
        frappe.msgprint(_("PPh 21 Settings configured successfully with TER method"))
        return settings
        
    except Exception as e:
        frappe.log_error(f"Error in setup_pph21_defaults: {str(e)}", "PPh 21 Setup Error")
        frappe.msgprint(_("Error setting up PPh 21: {0}").format(str(e)), indicator="red")
        return None

def setup_pph21_ter():
    """
    Setup default TER rates based on PMK-168/PMK.010/2023
    with improved validation and error handling

    TER (Tarif Efektif Rata-rata) adalah metode perhitungan alternatif 
    untuk PPh 21 yang menggunakan tarif yang sudah ditetapkan berdasarkan 
    rentang penghasilan dan status PTKP
    
    Returns:
        bool: True if setup is successful, False otherwise
    """
    try:
        # Check if the doctype exists
        if not frappe.db.exists("DocType", "PPh 21 TER Table"):
            frappe.log_error("PPh 21 TER Table DocType not found. Skipping TER setup.", "TER Setup Error")
            return False
        
        # Clear existing TER rates to avoid duplicates
        try:
            frappe.db.sql("DELETE FROM `tabPPh 21 TER Table`")
            frappe.db.commit()
        except Exception as e:
            frappe.log_error(f"Error clearing existing TER rates: {str(e)}", "TER Setup Error")
            # Continue anyway, we'll just have duplicates
        
        # Define status lists and TER rate structure
        status_list = ["TK0", "TK1", "TK2", "TK3", "K0", "K1", "K2", "K3", "HB0", "HB1", "HB2", "HB3"]
        
        # Dictionary berisi semua rate TER berdasarkan PMK-168/PMK.010/2023
        ter_rates = {
            # TK0 (Tidak Kawin 0 Tanggungan)
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
            
            # TK1 (Tidak Kawin 1 Tanggungan)
            "TK1": [
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
            ],
            
            # TK2 (Tidak Kawin 2 Tanggungan)
            "TK2": [
                {"income_from": 0, "income_to": 5250000, "rate": 0},
                {"income_from": 5250000, "income_to": 6000000, "rate": 0.5},
                {"income_from": 6000000, "income_to": 7000000, "rate": 1.0},
                {"income_from": 7000000, "income_to": 8000000, "rate": 1.5},
                {"income_from": 8000000, "income_to": 9000000, "rate": 2.0},
                {"income_from": 9000000, "income_to": 10000000, "rate": 2.5},
                {"income_from": 10000000, "income_to": 12000000, "rate": 3.0},
                {"income_from": 12000000, "income_to": 16000000, "rate": 3.75},
                {"income_from": 16000000, "income_to": 23000000, "rate": 4.75},
                {"income_from": 23000000, "income_to": 500000000, "rate": 6.75},
                {"income_from": 500000000, "income_to": 0, "rate": 9.25}
            ],
            
            # TK3 (Tidak Kawin 3 Tanggungan)
            "TK3": [
                {"income_from": 0, "income_to": 5625000, "rate": 0},
                {"income_from": 5625000, "income_to": 6500000, "rate": 0.5},
                {"income_from": 6500000, "income_to": 7500000, "rate": 1.0},
                {"income_from": 7500000, "income_to": 8500000, "rate": 1.5},
                {"income_from": 8500000, "income_to": 9500000, "rate": 1.75},
                {"income_from": 9500000, "income_to": 10500000, "rate": 2.25},
                {"income_from": 10500000, "income_to": 13000000, "rate": 2.75},
                {"income_from": 13000000, "income_to": 16500000, "rate": 3.5},
                {"income_from": 16500000, "income_to": 24500000, "rate": 4.5},
                {"income_from": 24500000, "income_to": 500000000, "rate": 6.5},
                {"income_from": 500000000, "income_to": 0, "rate": 9.0}
            ],
            
            # K0 (Kawin 0 Tanggungan)
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
            ],
            
            # K1 (Kawin 1 Tanggungan)
            "K1": [
                {"income_from": 0, "income_to": 5250000, "rate": 0},
                {"income_from": 5250000, "income_to": 6000000, "rate": 0.5},
                {"income_from": 6000000, "income_to": 7000000, "rate": 1.0},
                {"income_from": 7000000, "income_to": 8000000, "rate": 1.5},
                {"income_from": 8000000, "income_to": 9000000, "rate": 2.0},
                {"income_from": 9000000, "income_to": 10000000, "rate": 2.5},
                {"income_from": 10000000, "income_to": 12000000, "rate": 3.0},
                {"income_from": 12000000, "income_to": 16000000, "rate": 3.75},
                {"income_from": 16000000, "income_to": 23000000, "rate": 4.75},
                {"income_from": 23000000, "income_to": 500000000, "rate": 6.75},
                {"income_from": 500000000, "income_to": 0, "rate": 9.25}
            ],
            
            # K2 (Kawin 2 Tanggungan)
            "K2": [
                {"income_from": 0, "income_to": 5625000, "rate": 0},
                {"income_from": 5625000, "income_to": 6500000, "rate": 0.5},
                {"income_from": 6500000, "income_to": 7500000, "rate": 1.0},
                {"income_from": 7500000, "income_to": 8500000, "rate": 1.5},
                {"income_from": 8500000, "income_to": 9500000, "rate": 1.75},
                {"income_from": 9500000, "income_to": 10500000, "rate": 2.25},
                {"income_from": 10500000, "income_to": 13000000, "rate": 2.75},
                {"income_from": 13000000, "income_to": 16500000, "rate": 3.5},
                {"income_from": 16500000, "income_to": 24500000, "rate": 4.5},
                {"income_from": 24500000, "income_to": 500000000, "rate": 6.5},
                {"income_from": 500000000, "income_to": 0, "rate": 9.0}
            ],
            
            # K3 (Kawin 3 Tanggungan)
            "K3": [
                {"income_from": 0, "income_to": 6000000, "rate": 0},
                {"income_from": 6000000, "income_to": 7000000, "rate": 0.5},
                {"income_from": 7000000, "income_to": 8000000, "rate": 1.0},
                {"income_from": 8000000, "income_to": 9000000, "rate": 1.25},
                {"income_from": 9000000, "income_to": 10000000, "rate": 1.75},
                {"income_from": 10000000, "income_to": 11000000, "rate": 2.0},
                {"income_from": 11000000, "income_to": 14000000, "rate": 2.5},
                {"income_from": 14000000, "income_to": 17000000, "rate": 3.25},
                {"income_from": 17000000, "income_to": 26000000, "rate": 4.25},
                {"income_from": 26000000, "income_to": 500000000, "rate": 6.25},
                {"income_from": 500000000, "income_to": 0, "rate": 8.75}
            ],
            
            # HB0 (Kawin Penghasilan Istri-Suami Digabung 0 Tanggungan)
            "HB0": [
                {"income_from": 0, "income_to": 9375000, "rate": 0},
                {"income_from": 9375000, "income_to": 10500000, "rate": 0.5},
                {"income_from": 10500000, "income_to": 12500000, "rate": 1.0},
                {"income_from": 12500000, "income_to": 14500000, "rate": 1.75},
                {"income_from": 14500000, "income_to": 16500000, "rate": 2.25},
                {"income_from": 16500000, "income_to": 18500000, "rate": 2.75},
                {"income_from": 18500000, "income_to": 23000000, "rate": 3.5},
                {"income_from": 23000000, "income_to": 31000000, "rate": 4.25},
                {"income_from": 31000000, "income_to": 43000000, "rate": 5.25},
                {"income_from": 43000000, "income_to": 500000000, "rate": 7.25},
                {"income_from": 500000000, "income_to": 0, "rate": 9.75}
            ],
            
            # HB1 (Kawin Penghasilan Istri-Suami Digabung 1 Tanggungan)
            "HB1": [
                {"income_from": 0, "income_to": 9750000, "rate": 0},
                {"income_from": 9750000, "income_to": 11000000, "rate": 0.5},
                {"income_from": 11000000, "income_to": 13000000, "rate": 1.0},
                {"income_from": 13000000, "income_to": 15000000, "rate": 1.5},
                {"income_from": 15000000, "income_to": 17000000, "rate": 2.0},
                {"income_from": 17000000, "income_to": 19000000, "rate": 2.5},
                {"income_from": 19000000, "income_to": 24000000, "rate": 3.25},
                {"income_from": 24000000, "income_to": 32000000, "rate": 4.0},
                {"income_from": 32000000, "income_to": 46000000, "rate": 5.0},
                {"income_from": 46000000, "income_to": 500000000, "rate": 7.0},
                {"income_from": 500000000, "income_to": 0, "rate": 9.5}
            ],
            
            # HB2 (Kawin Penghasilan Istri-Suami Digabung 2 Tanggungan)
            "HB2": [
                {"income_from": 0, "income_to": 10125000, "rate": 0},
                {"income_from": 10125000, "income_to": 11500000, "rate": 0.5},
                {"income_from": 11500000, "income_to": 13500000, "rate": 1.0},
                {"income_from": 13500000, "income_to": 15500000, "rate": 1.25},
                {"income_from": 15500000, "income_to": 17500000, "rate": 1.75},
                {"income_from": 17500000, "income_to": 19500000, "rate": 2.25},
                {"income_from": 19500000, "income_to": 25000000, "rate": 3.0},
                {"income_from": 25000000, "income_to": 33000000, "rate": 3.75},
                {"income_from": 33000000, "income_to": 49000000, "rate": 4.75},
                {"income_from": 49000000, "income_to": 500000000, "rate": 6.75},
                {"income_from": 500000000, "income_to": 0, "rate": 9.25}
            ],
            
            # HB3 (Kawin Penghasilan Istri-Suami Digabung 3 Tanggungan)
            "HB3": [
                {"income_from": 0, "income_to": 10500000, "rate": 0},
                {"income_from": 10500000, "income_to": 12000000, "rate": 0.5},
                {"income_from": 12000000, "income_to": 14000000, "rate": 0.75},
                {"income_from": 14000000, "income_to": 16000000, "rate": 1.25},
                {"income_from": 16000000, "income_to": 18000000, "rate": 1.5},
                {"income_from": 18000000, "income_to": 20000000, "rate": 2.0},
                {"income_from": 20000000, "income_to": 26000000, "rate": 2.75},
                {"income_from": 26000000, "income_to": 34000000, "rate": 3.5},
                {"income_from": 34000000, "income_to": 52000000, "rate": 4.5},
                {"income_from": 52000000, "income_to": 500000000, "rate": 6.5},
                {"income_from": 500000000, "income_to": 0, "rate": 9.0}
            ]
        }
        
        # Counter for record count
        count = 0
        error_count = 0
        
        # Loop through all tax statuses and create TER rates
        for status in status_list:
            if status in ter_rates:
                # Loop through all rate brackets for this tax status
                for rate_data in ter_rates[status]:
                    try:
                        # Create an informative description
                        description = f"{status} "
                        
                        if rate_data["income_to"] == 0:
                            description += f"di atas Rp{rate_data['income_from']:,.0f}"
                        elif rate_data["income_from"] == 0:
                            description += f"s.d Rp{rate_data['income_to']:,.0f}"
                        else:
                            description += f"Rp{rate_data['income_from']:,.0f} s.d Rp{rate_data['income_to']:,.0f}"
                        
                        # Create a new TER record
                        doc = frappe.get_doc({
                            "doctype": "PPh 21 TER Table",
                            "status_pajak": status,
                            "income_from": flt(rate_data["income_from"]),
                            "income_to": flt(rate_data["income_to"]),
                            "rate": flt(rate_data["rate"]),
                            "description": description
                        })
                        
                        doc.insert(ignore_permissions=True)
                        count += 1
                    except Exception as e:
                        error_count += 1
                        frappe.log_error(
                            f"Error creating TER rate for {status} ({description}): {str(e)}",
                            "TER Rate Creation Error"
                        )
                        continue
            else:
                frappe.log_error(f"No TER rates defined for status {status}", "TER Setup Error")
        
        # Commit changes
        frappe.db.commit()
        
        # Log results
        if count > 0:
            frappe.logger().info(f"Created {count} TER rates for {len(status_list)} tax statuses")
            
            if error_count > 0:
                frappe.msgprint(
                    _("Created {0} TER rates with {1} errors. See error log for details.").format(count, error_count),
                    indicator="yellow"
                )
            else:
                frappe.msgprint(
                    _("Successfully created {0} TER rates for {1} tax statuses according to PMK-168/PMK.010/2023").format(
                        count, len(status_list)
                    ),
                    indicator="green"
                )
            return True
        else:
            frappe.log_error("Failed to create any TER rates", "TER Setup Error")
            frappe.msgprint(_("Failed to create TER rates. See error log for details."), indicator="red")
            return False
            
    except Exception as e:
        frappe.log_error(f"Error setting up PPh 21 TER rates: {str(e)}", "TER Setup Error")
        frappe.msgprint(_("Error setting up TER rates: {0}").format(str(e)), indicator="red")
        return False

def setup_income_tax_slab():
    """
    Create default Income Tax Slab for Indonesia
    with improved validation and error handling
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Validate Income Tax Slab DocType exists
        if not frappe.db.exists("DocType", "Income Tax Slab"):
            frappe.log_error("Income Tax Slab DocType not found", "Tax Slab Setup Error")
            return False
        
        # Check if default slab already exists
        if frappe.db.exists("Income Tax Slab", {"currency": "IDR", "is_default": 1}):
            frappe.logger().info("Default Income Tax Slab for Indonesia already exists")
            return True
        
        # Get company for the tax slab
        company = frappe.db.get_default("company")
        if not company:
            companies = frappe.get_all("Company")
            if companies:
                company = companies[0].name
            else:
                frappe.log_error("No company found for Income Tax Slab", "Tax Slab Setup Error")
                return False
        
        # Create the tax slab
        tax_slab = frappe.new_doc("Income Tax Slab")
        tax_slab.name = "Indonesia Tax Slab - IDR"
        tax_slab.effective_from = getdate("2023-01-01")
        tax_slab.company = company
        tax_slab.currency = "IDR"
        tax_slab.is_default = 1
        tax_slab.disabled = 0
        
        # Add tax slabs based on current regulations
        tax_slabs = [
            {"from_amount": 0, "to_amount": 60000000, "percent_deduction": 5},
            {"from_amount": 60000000, "to_amount": 250000000, "percent_deduction": 15},
            {"from_amount": 250000000, "to_amount": 500000000, "percent_deduction": 25},
            {"from_amount": 500000000, "to_amount": 5000000000, "percent_deduction": 30},
            {"from_amount": 5000000000, "to_amount": 0, "percent_deduction": 35}
        ]
        
        # Add each slab to the tax slab document
        for slab in tax_slabs:
            tax_slab.append("slabs", {
                "from_amount": flt(slab["from_amount"]),
                "to_amount": flt(slab["to_amount"]),
                "percent_deduction": flt(slab["percent_deduction"])
            })
            
        # Insert the document
        tax_slab.insert(ignore_permissions=True)
        frappe.db.commit()
        
        frappe.logger().info("Created default Income Tax Slab for Indonesia")
        frappe.msgprint(_("Created default Income Tax Slab for Indonesia"))
        return True
        
    except Exception as e:
        frappe.log_error(f"Error creating Income Tax Slab: {str(e)}", "Tax Slab Setup Error")
        frappe.msgprint(_("Error creating Income Tax Slab: {0}").format(str(e)), indicator="red")
        return False