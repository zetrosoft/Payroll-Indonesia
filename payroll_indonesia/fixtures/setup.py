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

# Removed create_bpjs_supplier() function as it's now handled by fixtures