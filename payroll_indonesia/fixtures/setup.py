import frappe
from frappe import _
from frappe.utils import getdate
from payroll_indonesia.payroll_indonesia.setup import setup_settings

def before_install():
    """Setup requirements before installing the app"""
    pass

def after_install():
    """Setup requirements after installing the app"""
    # Create Accounts first (required for salary components)
    create_accounts()
    
    # Setup additional requirements
    create_supplier_group()
    # Removing create_bpjs_supplier() since it's now handled by fixture
    
    # Setup Settings
    setup_settings()
    
    # Setup TER rates for PPh 21
    setup_pph21_ter()

def create_accounts():
    """Create required Accounts"""
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
    
    company = frappe.defaults.get_defaults().get("company")
    if not company:
        frappe.log_error("No default company found. Skipping account creation.")
        return
        
    for account in accounts:
        try:
            parent_account = frappe.db.get_value("Account", {
                "account_name": account["parent_account"],
                "company": company
            }, "name")
            
            if not parent_account:
                frappe.log_error(f"Parent account {account['parent_account']} not found for company {company}")
                continue
                
            account_name = account["account_name"] + " - " + frappe.db.get_value("Company", company, "abbr")
            
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
    """Create Government supplier group if not exists"""
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

def setup_pph21_ter():
    """Setup default TER rates based on PMK 168/2023"""
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
            if not frappe.db.exists(
                "PPh 21 TER Table",
                {
                    "status_pajak": rate_data["status_pajak"],
                    "income_from": rate_data["income_from"],
                    "income_to": rate_data["income_to"]
                }
            ):
                doc = frappe.new_doc("PPh 21 TER Table")
                doc.update(rate_data)
                doc.insert(ignore_permissions=True)
                count += 1
        
        if count > 0:
            frappe.msgprint(_(f"Created {count} default TER rates based on PMK 168/2023"))
            
    except Exception as e:
        frappe.log_error(f"Error setting up PPh 21 TER rates: {str(e)}")