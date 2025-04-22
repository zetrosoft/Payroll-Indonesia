import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def before_install():
    """Setup requirements before installing the app"""
    pass

def after_install():
    """Setup requirements after installing the app"""
    # Create Accounts first (required for salary components)
    create_accounts()
    
    # Create Salary Components
    create_salary_components()
    
    # Create Salary Structures
    create_salary_structures()

def create_salary_components():
    """Create required Salary Components"""
    components = [
        # Earnings
        {
            "doctype": "Salary Component",
            "salary_component": "Gaji Pokok",
            "salary_component_abbr": "GP",
            "type": "Earning",
            "is_tax_applicable": 1,
            "description": "Gaji Pokok Karyawan",
            "accounts": [{
                "company": "%",
                "default_account": "Beban Gaji Pokok - %"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "Tunjangan Makan",
            "salary_component_abbr": "TM",
            "type": "Earning",
            "is_tax_applicable": 1,
            "description": "Tunjangan Makan Karyawan",
            "accounts": [{
                "company": "%",
                "default_account": "Beban Tunjangan Makan - %"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "Tunjangan Transport",
            "salary_component_abbr": "TT",
            "type": "Earning",
            "is_tax_applicable": 1,
            "description": "Tunjangan Transport Karyawan",
            "accounts": [{
                "company": "%",
                "default_account": "Beban Tunjangan Transport - %"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "Insentif",
            "salary_component_abbr": "INS",
            "type": "Earning",
            "is_tax_applicable": 1,
            "description": "Insentif Karyawan",
            "accounts": [{
                "company": "%",
                "default_account": "Beban Insentif - %"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "Bonus",
            "salary_component_abbr": "BON",
            "type": "Earning",
            "is_tax_applicable": 1,
            "description": "Bonus Karyawan",
            "accounts": [{
                "company": "%",
                "default_account": "Beban Bonus - %"
            }]
        },
        # Deductions
        {
            "doctype": "Salary Component",
            "salary_component": "PPh 21",
            "salary_component_abbr": "PPH21",
            "type": "Deduction",
            "variable_based_on_taxable_salary": 1,
            "description": "Pajak Penghasilan Pasal 21",
            "accounts": [{
                "company": "%",
                "default_account": "Hutang PPh 21 - %"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "BPJS JHT Employee",
            "salary_component_abbr": "BPJSJHT",
            "type": "Deduction",
            "description": "BPJS Jaminan Hari Tua - Potongan Karyawan",
            "accounts": [{
                "company": "%",
                "default_account": "Hutang BPJS JHT - %"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "BPJS JP Employee",
            "salary_component_abbr": "BPJSJP",
            "type": "Deduction",
            "description": "BPJS Jaminan Pensiun - Potongan Karyawan",
            "accounts": [{
                "company": "%",
                "default_account": "Hutang BPJS JP - %"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "BPJS Kesehatan Employee",
            "salary_component_abbr": "BPJSKES",
            "type": "Deduction",
            "description": "BPJS Kesehatan - Potongan Karyawan",
            "accounts": [{
                "company": "%",
                "default_account": "Hutang BPJS Kesehatan - %"
            }]
        },
        # Statistical Components (Employer Share)
        {
            "doctype": "Salary Component",
            "salary_component": "BPJS JHT Employer",
            "salary_component_abbr": "BPJSJHTE",
            "type": "Deduction",
            "statistical_component": 1,
            "description": "BPJS Jaminan Hari Tua - Kontribusi Perusahaan",
            "accounts": [{
                "company": "%",
                "default_account": "Beban BPJS JHT - %"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "BPJS JP Employer",
            "salary_component_abbr": "BPJSJPE",
            "type": "Deduction",
            "statistical_component": 1,
            "description": "BPJS Jaminan Pensiun - Kontribusi Perusahaan",
            "accounts": [{
                "company": "%",
                "default_account": "Beban BPJS JP - %"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "BPJS JKK",
            "salary_component_abbr": "BPJSJKK",
            "type": "Deduction",
            "statistical_component": 1,
            "description": "BPJS Jaminan Kecelakaan Kerja",
            "accounts": [{
                "company": "%",
                "default_account": "Beban BPJS JKK - %"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "BPJS JKM",
            "salary_component_abbr": "BPJSJKM",
            "type": "Deduction",
            "statistical_component": 1,
            "description": "BPJS Jaminan Kematian",
            "accounts": [{
                "company": "%",
                "default_account": "Beban BPJS JKM - %"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "BPJS Kesehatan Employer",
            "salary_component_abbr": "BPJSKESE",
            "type": "Deduction",
            "statistical_component": 1,
            "description": "BPJS Kesehatan - Kontribusi Perusahaan",
            "accounts": [{
                "company": "%",
                "default_account": "Beban BPJS Kesehatan - %"
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
            frappe.db.commit()

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
    
    company = frappe.defaults.get_defaults().company
    if not company:
        return
        
    for account in accounts:
        parent_account = frappe.db.get_value("Account", {
            "account_name": account["parent_account"],
            "company": company
        }, "name")
        
        if not parent_account:
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

def create_salary_structures():
    """Create required Salary Structures"""
    structures = [
        {
            "doctype": "Salary Structure",
            "name": "Struktur Gaji Tetap G1",
            "is_active": "Yes",
            "payroll_frequency": "Monthly",
            "payment_account": "Cash - %",
            "earnings": [
                {
                    "salary_component": "Gaji Pokok",
                    "amount_based_on_formula": 1,
                    "formula": "base",
                    "condition": ""
                },
                {
                    "salary_component": "Tunjangan Makan",
                    "amount": 500000,
                    "condition": ""
                },
                {
                    "salary_component": "Tunjangan Transport",
                    "amount": 300000,
                    "condition": ""
                }
            ],
            "deductions": [
                {
                    "salary_component": "BPJS JHT Employee",
                    "amount_based_on_formula": 1,
                    "formula": "base * 0.02",
                    "condition": "ikut_bpjs_ketenagakerjaan"
                },
                {
                    "salary_component": "BPJS JP Employee",
                    "amount_based_on_formula": 1,
                    "formula": "base * 0.01",
                    "condition": "ikut_bpjs_ketenagakerjaan"
                },
                {
                    "salary_component": "BPJS Kesehatan Employee",
                    "amount_based_on_formula": 1,
                    "formula": "base * 0.01",
                    "condition": "ikut_bpjs_kesehatan"
                },
                {
                    "salary_component": "PPh 21",
                    "amount_based_on_formula": 0,
                    "formula": "",
                    "condition": "not penghasilan_final"
                }
            ]
        }
    ]
    
    for structure in structures:
        if not frappe.db.exists("Salary Structure", structure["name"]):
            doc = frappe.new_doc("Salary Structure")
            
            for key, value in structure.items():
                if key not in ["earnings", "deductions"]:
                    doc.set(key, value)
            
            for earning in structure.get("earnings", []):
                doc.append("earnings", earning)
                
            for deduction in structure.get("deductions", []):
                doc.append("deductions", deduction)
                
            company = frappe.defaults.get_defaults().company
            if company:
                doc.company = company
                
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
