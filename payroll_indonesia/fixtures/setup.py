import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def before_install():
    """Setup requirements before installing the app"""
    pass

def after_install():
    """Setup requirements after installing the app"""
    # Create Salary Components
    create_salary_components()
    
    # Create Salary Structures
    create_salary_structures()
    
    # Create Accounts
    create_accounts()

def create_salary_components():
    """Create required Salary Components"""
    components = [
        {
            "doctype": "Salary Component",
            "salary_component": "Gaji Pokok",
            "type": "Earning",
            "is_tax_applicable": 1,
            "is_payable": 1,
            "accounts": [{
                "company": frappe.defaults.get_defaults().company,
                "default_account": "Beban Gaji Pokok - IDR"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "Tunjangan Makan",
            "type": "Earning",
            "is_tax_applicable": 1,
            "is_payable": 1,
            "accounts": [{
                "company": frappe.defaults.get_defaults().company,
                "default_account": "Beban Tunjangan Makan - IDR"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "Tunjangan Transport",
            "type": "Earning",
            "is_tax_applicable": 1,
            "is_payable": 1,
            "accounts": [{
                "company": frappe.defaults.get_defaults().company,
                "default_account": "Beban Tunjangan Transport - IDR"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "Insentif",
            "type": "Earning",
            "is_tax_applicable": 1,
            "is_payable": 1,
            "accounts": [{
                "company": frappe.defaults.get_defaults().company,
                "default_account": "Beban Insentif - IDR"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "BPJS Kesehatan",
            "type": "Deduction",
            "accounts": [{
                "company": frappe.defaults.get_defaults().company,
                "default_account": "Hutang BPJS Kesehatan - IDR"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "BPJS TK",
            "type": "Deduction",
            "accounts": [{
                "company": frappe.defaults.get_defaults().company,
                "default_account": "Hutang BPJS TK - IDR"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "PPh 21",
            "type": "Deduction",
            "variable_based_on_taxable_salary": 1,
            "accounts": [{
                "company": frappe.defaults.get_defaults().company,
                "default_account": "Hutang PPh 21 - IDR"
            }]
        }
    ]
    
    for component in components:
        if not frappe.db.exists("Salary Component", component["salary_component"]):
            doc = frappe.new_doc("Salary Component")
            for key, value in component.items():
                if key != "accounts":
                    doc.set(key, value)
            
            if "accounts" in component:
                for account in component["accounts"]:
                    doc.append("accounts", account)
            
            doc.insert(ignore_permissions=True)
            doc.submit()
            frappe.db.commit()

def create_salary_structures():
    """Create required Salary Structures"""
    # Ensure the Salary Components exist first
    create_salary_components()
    
    structures = [
        {
            "doctype": "Salary Structure",
            "name": "Struktur Gaji Tetap G1",
            "is_active": "Yes",
            "payroll_frequency": "Monthly",
            "payment_account": "Cash - IDR",
            "earnings": [
                {"salary_component": "Gaji Pokok", "amount_based_on_formula": 1, "formula": "base"},
                {"salary_component": "Tunjangan Makan", "amount": 500000},
                {"salary_component": "Tunjangan Transport", "amount": 300000},
                {"salary_component": "Insentif", "amount": 0, "formula": "base * 0.1", "amount_based_on_formula": 1, "condition": "performance_rating > 3"}
            ],
            "deductions": [
                {"salary_component": "BPJS Kesehatan", "amount": 0, "formula": "base * 0.01", "amount_based_on_formula": 1},
                {"salary_component": "BPJS TK", "amount": 0, "formula": "base * 0.03", "amount_based_on_formula": 1},
                {"salary_component": "PPh 21", "amount": 0, "formula": "", "amount_based_on_formula": 0}
            ]
        },
        {
            "doctype": "Salary Structure",
            "name": "Struktur Freelance",
            "is_active": "Yes",
            "payroll_frequency": "Monthly",
            "payment_account": "Cash - IDR",
            "earnings": [
                {"salary_component": "Gaji Pokok", "amount_based_on_formula": 1, "formula": "base"}
            ],
            "deductions": [
                {"salary_component": "PPh 21", "amount": 0, "formula": "", "amount_based_on_formula": 0}
            ]
        }
    ]
    
    for structure in structures:
        if not frappe.db.exists("Salary Structure", structure["name"]):
            doc = frappe.new_doc("Salary Structure")
            
            for key, value in structure.items():
                if key not in ["earnings", "deductions"]:
                    doc.set(key, value)
            
            # Add earnings
            for earning in structure.get("earnings", []):
                doc.append("earnings", earning)
                
            # Add deductions
            for deduction in structure.get("deductions", []):
                doc.append("deductions", deduction)
                
            # Set defaults
            company = frappe.defaults.get_defaults().company
            if company:
                doc.company = company
                
            doc.insert(ignore_permissions=True)
            frappe.db.commit()

def create_accounts():
    """Create required Accounts"""
    accounts = [
        {"account_name": "Beban Gaji Pokok", "parent_account": "Direct Expenses", "account_type": "Expense Account"},
        {"account_name": "Beban Tunjangan Makan", "parent_account": "Direct Expenses", "account_type": "Expense Account"},
        {"account_name": "Beban Tunjangan Transport", "parent_account": "Direct Expenses", "account_type": "Expense Account"},
        {"account_name": "Beban Insentif", "parent_account": "Direct Expenses", "account_type": "Expense Account"},
        {"account_name": "Hutang BPJS Kesehatan", "parent_account": "Accounts Payable", "account_type": "Payable"},
        {"account_name": "Hutang BPJS TK", "parent_account": "Accounts Payable", "account_type": "Payable"},
        {"account_name": "Hutang PPh 21", "parent_account": "Accounts Payable", "account_type": "Payable"}
    ]
    
    company = frappe.defaults.get_defaults().company
    
    if not company:
        return
        
    for account in accounts:
        # Check if parent account exists and get full name
        parent_account = frappe.db.get_value("Account", {
            "account_name": account["parent_account"],
            "company": company
        }, "name")
        
        if not parent_account:
            continue  # Skip if parent doesn't exist
            
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