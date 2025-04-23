import frappe
from frappe import _
from frappe.utils import getdate

def before_install():
    """Setup requirements before installing the app"""
    pass

def after_install():
    """Setup requirements after installing the app"""
    # Create Accounts first (required for salary components)
    try:
        create_accounts()
    except Exception as e:
        frappe.log_error(f"Error creating accounts: {str(e)}")
        frappe.msgprint(f"Warning: Some accounts could not be created: {str(e)}")
    
    # Setup additional requirements
    try:
        create_supplier_group()
    except Exception as e:
        frappe.log_error(f"Error creating supplier group: {str(e)}")
        frappe.msgprint(f"Warning: Supplier group could not be created: {str(e)}")
    
    # Setup Settings - delay to ensure DocTypes are installed
    frappe.enqueue(
        setup_pph21_defaults,
        queue='default',
        timeout=600,
        is_async=True
    )
    
    frappe.enqueue(
        setup_pph21_ter,
        queue='default',
        timeout=600,
        is_async=True
    )
    """Setup requirements after installing the app"""
    # Create Accounts first (required for salary components)
    create_accounts()
    
    # Setup additional requirements
    create_supplier_group()
    # Removing create_bpjs_supplier() since it's now handled by fixture
    
    # Setup Settings
    setup_pph21_defaults()
    setup_pph21_ter()

def create_accounts():
    """Create required Accounts for Indonesian payroll management

    This creates all necessary expense accounts for salary components
    and liability accounts for taxes and social insurance
    """
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
        frappe.log_error("No default company found. Skipping account creation.")
        return
        
    # Loop through accounts list and create each account
    for account in accounts:
        try:
            # Get the full parent account name including company abbreviation
            parent_account = frappe.db.get_value("Account", {
                "account_name": account["parent_account"],
                "company": company
            }, "name")
            
            if not parent_account:
                frappe.log_error(f"Parent account {account['parent_account']} not found for company {company}")
                continue
                
            # Create the account name with company abbreviation
            account_name = account["account_name"] + " - " + frappe.db.get_value("Company", company, "abbr")
            
            # Create account if it doesn't exist
            if not frappe.db.exists("Account", account_name):
                doc = frappe.new_doc("Account")
                doc.account_name = account["account_name"]
                doc.parent_account = parent_account
                doc.account_type = account["account_type"]
                doc.company = company
                doc.is_group = 0
                doc.insert(ignore_permissions=True)
                frappe.db.commit()
        except Exception as e:
            frappe.log_error(f"Error creating account {account['account_name']}: {str(e)}")

def create_supplier_group():
    """Create Government supplier group if not exists

    This group is needed for government-related suppliers like tax office and BPJS
    """
    if not frappe.db.exists("Supplier Group", "Government"):
        try:
            group = frappe.new_doc("Supplier Group")
            group.supplier_group_name = "Government"
            group.parent_supplier_group = "All Supplier Groups"
            group.is_group = 0
            group.insert()
            frappe.db.commit()
        except Exception as e:
            frappe.log_error(f"Failed to create Government supplier group: {str(e)}")

def setup_pph21_defaults():
    """Setup default PPh 21 configuration

    Sets up the income tax settings with default PTKP values and tax brackets
    according to Indonesian tax regulations
    """
    try:
        # Check if PPh 21 Settings DocType exists
        if not frappe.db.exists("DocType", "PPh 21 Settings"):
            frappe.log_error("DocType 'PPh 21 Settings' tidak ditemukan. Pastikan DocType sudah diinstall dengan benar.")
            frappe.msgprint("DocType 'PPh 21 Settings' tidak ditemukan. Skipping PPh 21 setup.")
            return
        
        # Check if we need to create or just update
        doc_exists = frappe.db.exists("PPh 21 Settings", "PPh 21 Settings")
        
        if not doc_exists:
            try:
                # Create new PPh 21 Settings
                settings = frappe.new_doc("PPh 21 Settings")
                settings.calculation_method = "Progressive"
                settings.use_ter = 0
                
                # Add default PTKP values (sesuai peraturan terbaru)
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
                    try:
                        ptkp_row = {}
                        ptkp_row["status_pajak"] = status
                        ptkp_row["ptkp_amount"] = amount
                        
                        # Add description for better readability
                        if status.startswith("TK"):
                            tanggungan = status[2:]
                            ptkp_row["description"] = f"Tidak Kawin, {tanggungan} Tanggungan"
                        elif status.startswith("K"):
                            tanggungan = status[1:]
                            ptkp_row["description"] = f"Kawin, {tanggungan} Tanggungan" 
                        elif status.startswith("HB"):
                            tanggungan = status[2:]
                            ptkp_row["description"] = f"Kawin (Penghasilan Istri Digabung), {tanggungan} Tanggungan"
                            
                        settings.append("ptkp_table", ptkp_row)
                    except Exception as e:
                        frappe.log_error(f"Error adding PTKP row: {str(e)}")
                
                # Add default tax brackets (pasal 17 UU PPh)
                brackets = [
                    {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                    {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
                    {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
                    {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
                    {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
                ]
                
                # Add each tax bracket to the settings
                for bracket in brackets:
                    try:
                        settings.append("bracket_table", bracket)
                    except Exception as e:
                        frappe.log_error(f"Error adding bracket row: {str(e)}")
                
                try:
                    settings.insert(ignore_permissions=True)
                    frappe.db.commit()
                    frappe.msgprint("Setup PPh 21 Settings completed successfully")
                except Exception as e:
                    frappe.log_error(f"Error saving PPh 21 Settings: {str(e)}")
                    frappe.msgprint(f"Error saving PPh 21 Settings: {str(e)}")
            except Exception as e:
                frappe.log_error(f"Error creating PPh 21 Settings: {str(e)}")
                frappe.msgprint(f"Error creating PPh 21 Settings: {str(e)}")
        else:
            # Settings exist but check if bracket table is populated
            try:
                settings = frappe.get_doc("PPh 21 Settings", "PPh 21 Settings")
                
                # Check if tables are empty and need to be populated
                if not settings.bracket_table or len(settings.bracket_table) == 0:
                    # Brackets empty, populate defaults
                    brackets = [
                        {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                        {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
                        {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
                        {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
                        {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
                    ]
                    
                    for bracket in brackets:
                        settings.append("bracket_table", bracket)
                    
                    settings.save()
                    frappe.db.commit()
                    frappe.msgprint("Added default tax brackets to PPh 21 Settings")
            except Exception as e:
                frappe.log_error(f"Error updating PPh 21 Settings: {str(e)}")
                frappe.msgprint(f"Error updating PPh 21 Settings: {str(e)}")
    
    except Exception as e:
        frappe.log_error(f"Unexpected error in setup_pph21_defaults: {str(e)}")
        frappe.msgprint(f"Warning: PPh 21 setup encountered an error: {str(e)}")
    """Setup default PPh 21 configuration

    Sets up the income tax settings with default PTKP values and tax brackets
    according to Indonesian tax regulations
    """
    try:
        # Check if PPh 21 Settings already exists
        if not frappe.db.exists("DocType", "PPh 21 Settings"):
            frappe.throw("DocType 'PPh 21 Settings' tidak ditemukan. Pastikan DocType sudah diinstall dengan benar.")
            
        if not frappe.db.exists("PPh 21 Settings", "PPh 21 Settings"):
            # Create new PPh 21 Settings
            settings = frappe.new_doc("PPh 21 Settings")
            settings.doctype = "PPh 21 Settings"  # Explicitly set doctype
            settings.calculation_method = "Progressive"
            settings.use_ter = 0
            
            # Check if child tables exist in doctype definition
            doctype = frappe.get_doc("DocType", "PPh 21 Settings")
            has_ptkp_table = any(table.fieldname == "ptkp_table" for table in doctype.get("fields", []) if table.fieldtype == "Table")
            has_bracket_table = any(table.fieldname == "bracket_table" for table in doctype.get("fields", []) if table.fieldtype == "Table")
            
            if not has_ptkp_table:
                frappe.throw("Child table 'ptkp_table' tidak ditemukan dalam DocType 'PPh 21 Settings'")
            
            if not has_bracket_table:
                frappe.throw("Child table 'bracket_table' tidak ditemukan dalam DocType 'PPh 21 Settings'")
            
            # Add default PTKP values (sesuai peraturan terbaru)
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
                try:
                    ptkp_row = settings.append("ptkp_table")
                    ptkp_row.status_pajak = status
                    ptkp_row.ptkp_amount = amount
                    
                    # Add description for better readability
                    if status.startswith("TK"):
                        tanggungan = status[2:]
                        ptkp_row.description = f"Tidak Kawin, {tanggungan} Tanggungan"
                    elif status.startswith("K"):
                        tanggungan = status[1:]
                        ptkp_row.description = f"Kawin, {tanggungan} Tanggungan"
                    elif status.startswith("HB"):
                        tanggungan = status[2:]
                        ptkp_row.description = f"Kawin (Penghasilan Istri Digabung), {tanggungan} Tanggungan"
                except Exception as e:
                    frappe.log_error(f"Error adding PTKP row: {str(e)}")
                    raise
            
            # Add default tax brackets (pasal 17 UU PPh)
            brackets = [
                {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
                {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
                {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
                {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
            ]
            
            # Add each tax bracket to the settings
            for bracket in brackets:
                try:
                    bracket_row = settings.append("bracket_table")
                    bracket_row.income_from = bracket["income_from"]
                    bracket_row.income_to = bracket["income_to"]
                    bracket_row.tax_rate = bracket["tax_rate"]
                except Exception as e:
                    frappe.log_error(f"Error adding bracket row: {str(e)}")
                    raise
            
            try:
                settings.insert(ignore_permissions=True)  # Use insert instead of save for new doc
                frappe.db.commit()
                frappe.msgprint("Setup PPh 21 Settings completed successfully")
            except Exception as e:
                frappe.log_error(f"Error saving PPh 21 Settings: {str(e)}")
                raise
        else:
            # Settings exist but check if bracket table is populated
            settings = frappe.get_doc("PPh 21 Settings", "PPh 21 Settings")
            
            # Check if tables are empty and need to be populated
            if hasattr(settings, 'bracket_table') and len(settings.bracket_table) == 0:
                # Brackets empty, populate defaults
                brackets = [
                    {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                    {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
                    {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
                    {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
                    {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
                ]
                
                for bracket in brackets:
                    settings.append("bracket_table", bracket)
                
                settings.save()
                frappe.db.commit()
                frappe.msgprint("Added default tax brackets to PPh 21 Settings")
    
    except Exception as e:
        frappe.log_error(f"Error in setup_pph21_defaults: {str(e)}")
        frappe.throw(f"Error setting up PPh 21 Settings: {str(e)}")

def setup_pph21_ter():
    """Setup default TER rates based on PMK 168/2023

    TER (Tax Equivalent Rate) is an alternative calculation method
    for PPh 21 income tax that uses predefined rates based on income ranges
    """
    try:
        # Check if the doctype exists
        if not frappe.db.exists("DocType", "PPh 21 TER Table"):
            frappe.log_error("PPh 21 TER Table DocType not found. Skipping TER setup.")
            return
            
        # Update PPh 21 Settings to enable TER
        if frappe.db.exists("DocType", "PPh 21 Settings"):
            settings = frappe.get_single("PPh 21 Settings")
            settings.calculation_method = "TER"
            settings.use_ter = 1
            settings.save()
            
        # Create TER rates based on PMK 168/2023
        # These are sample rates - replace with actual rates from PMK 168/2023
        default_rates = [
            # TK0 - Tidak Kawin 0 Tanggungan
            {"status_pajak": "TK0", "income_from": 0, "income_to": 4500000, "rate": 0.0},
            {"status_pajak": "TK0", "income_from": 4500000, "income_to": 5000000, "rate": 0.5},
            {"status_pajak": "TK0", "income_from": 5000000, "income_to": 6000000, "rate": 1.0},
            {"status_pajak": "TK0", "income_from": 6000000, "income_to": 7000000, "rate": 1.75},
            {"status_pajak": "TK0", "income_from": 7000000, "income_to": 8000000, "rate": 2.5},
            {"status_pajak": "TK0", "income_from": 8000000, "income_to": 9000000, "rate": 3.0},
            {"status_pajak": "TK0", "income_from": 9000000, "income_to": 10000000, "rate": 3.5},
            {"status_pajak": "TK0", "income_from": 10000000, "income_to": 15000000, "rate": 4.5},
            {"status_pajak": "TK0", "income_from": 15000000, "income_to": 20000000, "rate": 5.5},
            {"status_pajak": "TK0", "income_from": 20000000, "income_to": 500000000, "rate": 7.5},
            {"status_pajak": "TK0", "income_from": 500000000, "income_to": 0, "rate": 10.0, "is_highest_bracket": 1},
            
            # K0 - Kawin 0 Tanggungan
            {"status_pajak": "K0", "income_from": 0, "income_to": 4875000, "rate": 0.0},
            {"status_pajak": "K0", "income_from": 4875000, "income_to": 5500000, "rate": 0.5},
            {"status_pajak": "K0", "income_from": 5500000, "income_to": 6500000, "rate": 1.0},
            {"status_pajak": "K0", "income_from": 6500000, "income_to": 7500000, "rate": 1.75},
            {"status_pajak": "K0", "income_from": 7500000, "income_to": 8500000, "rate": 2.25},
            {"status_pajak": "K0", "income_from": 8500000, "income_to": 9500000, "rate": 2.75},
            {"status_pajak": "K0", "income_from": 9500000, "income_to": 11000000, "rate": 3.25},
            {"status_pajak": "K0", "income_from": 11000000, "income_to": 15500000, "rate": 4.0},
            {"status_pajak": "K0", "income_from": 15500000, "income_to": 21500000, "rate": 5.0},
            {"status_pajak": "K0", "income_from": 21500000, "income_to": 500000000, "rate": 7.0},
            {"status_pajak": "K0", "income_from": 500000000, "income_to": 0, "rate": 9.5, "is_highest_bracket": 1},
            
            # Tambahkan status dan range lainnya (K1, K2, K3, TK1, TK2, TK3, HB0, HB1, HB2, HB3)
            # berdasarkan PMK 168/2023
        ]
        
        # Create TER rate records if they don't exist
        count = 0
        for rate_data in default_rates:
            # Check if the specific TER rate already exists
            if not frappe.db.exists(
                "PPh 21 TER Table",
                {
                    "status_pajak": rate_data["status_pajak"],
                    "income_from": rate_data["income_from"],
                    "income_to": rate_data["income_to"]
                }
            ):
                # Create new TER rate record
                doc = frappe.new_doc("PPh 21 TER Table")
                doc.update(rate_data)
                doc.insert(ignore_permissions=True)
                count += 1
        
        if count > 0:
            frappe.msgprint(_(f"Created {count} default TER rates based on PMK 168/2023"))
            
    except Exception as e:
        frappe.log_error(f"Error setting up PPh 21 TER rates: {str(e)}")