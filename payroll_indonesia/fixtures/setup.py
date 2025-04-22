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
    
    # Setup additional requirements
    create_supplier_group()
    create_bpjs_supplier()

def create_salary_components():
    """Create required Salary Components"""
    # Get the default company
    company = frappe.defaults.get_defaults().get("company")
    if not company:
        frappe.log_error("No default company found. Skipping salary component creation.")
        return
    
    # Get company abbreviation for account naming
    company_abbr = frappe.db.get_value("Company", company, "abbr")
    if not company_abbr:
        frappe.log_error(f"Company abbreviation not found for {company}. Skipping salary component creation.")
        return
    
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
                "company": company,
                "default_account": f"Beban Gaji Pokok - {company_abbr}",
                "doctype": "Salary Component Account"
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
                "company": company,
                "default_account": f"Beban Tunjangan Makan - {company_abbr}",
                "doctype": "Salary Component Account"
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
                "company": company,
                "default_account": f"Beban Tunjangan Transport - {company_abbr}",
                "doctype": "Salary Component Account"
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
                "company": company,
                "default_account": f"Beban Insentif - {company_abbr}",
                "doctype": "Salary Component Account"
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
                "company": company,
                "default_account": f"Beban Bonus - {company_abbr}",
                "doctype": "Salary Component Account"
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
                "company": company,
                "default_account": f"Hutang PPh 21 - {company_abbr}",
                "doctype": "Salary Component Account"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "BPJS JHT Employee",
            "salary_component_abbr": "BPJSJHT",
            "type": "Deduction",
            "description": "BPJS Jaminan Hari Tua - Potongan Karyawan",
            "accounts": [{
                "company": company,
                "default_account": f"Hutang BPJS JHT - {company_abbr}",
                "doctype": "Salary Component Account"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "BPJS JP Employee",
            "salary_component_abbr": "BPJSJP",
            "type": "Deduction",
            "description": "BPJS Jaminan Pensiun - Potongan Karyawan",
            "accounts": [{
                "company": company,
                "default_account": f"Hutang BPJS JP - {company_abbr}",
                "doctype": "Salary Component Account"
            }]
        },
        {
            "doctype": "Salary Component",
            "salary_component": "BPJS Kesehatan Employee",
            "salary_component_abbr": "BPJSKES",
            "type": "Deduction",
            "description": "BPJS Kesehatan - Potongan Karyawan",
            "accounts": [{
                "company": company,
                "default_account": f"Hutang BPJS Kesehatan - {company_abbr}",
                "doctype": "Salary Component Account"
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
                "company": company,
                "default_account": f"Beban BPJS JHT - {company_abbr}",
                "doctype": "Salary Component Account"
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
                "company": company,
                "default_account": f"Beban BPJS JP - {company_abbr}",
                "doctype": "Salary Component Account"
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
                "company": company,
                "default_account": f"Beban BPJS JKK - {company_abbr}",
                "doctype": "Salary Component Account"
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
                "company": company,
                "default_account": f"Beban BPJS JKM - {company_abbr}",
                "doctype": "Salary Component Account"
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
                "company": company,
                "default_account": f"Beban BPJS Kesehatan - {company_abbr}",
                "doctype": "Salary Component Account"
            }]
        }
    ]
    
    for component in components:
        if not frappe.db.exists("Salary Component", component["salary_component"]):
            try:
                doc = frappe.new_doc("Salary Component")
                for key, value in component.items():
                    if key != "accounts":
                        doc.set(key, value)
                
                if "accounts" in component:
                    for account in component["accounts"]:
                        # Check if the account exists before adding
                        if frappe.db.exists("Account", account["default_account"]):
                            doc.append("accounts", account)
                        else:
                            frappe.log_error(f"Account {account['default_account']} not found for component {component['salary_component']}")
                
                doc.insert(ignore_permissions=True)
                frappe.db.commit()
            except Exception as e:
                frappe.log_error(f"Error creating salary component {component['salary_component']}: {str(e)}")

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

def create_salary_structures():
    """Create required Salary Structures"""
    # Get the default company
    company = frappe.defaults.get_defaults().get("company")
    if not company:
        frappe.log_error("No default company found. Skipping salary structure creation.")
        return
    
    # Get company abbreviation for account naming
    company_abbr = frappe.db.get_value("Company", company, "abbr")
    if not company_abbr:
        frappe.log_error(f"Company abbreviation not found for {company}. Skipping salary structure creation.")
        return
    
    # Find a valid payment account
    payment_account = None
    
    # Try to get default cash account
    try:
        payment_account = frappe.db.get_value("Account", 
            {"account_name": "Cash", "company": company, "is_group": 0}, "name")
    except:
        pass
        
    # If not found, try to get any bank account
    if not payment_account:
        try:
            payment_account = frappe.db.get_value("Account", 
                {"account_type": "Bank", "company": company, "is_group": 0}, "name")
        except:
            pass
    
    # If still not found, use a default format
    if not payment_account:
        payment_account = f"Cash - {company_abbr}"
    
    structures = [
        {
            "doctype": "Salary Structure",
            "name": "Struktur Gaji Tetap G1",
            "is_active": "Yes",
            "payroll_frequency": "Monthly",
            "payment_account": payment_account,
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
            try:
                doc = frappe.new_doc("Salary Structure")
                
                for key, value in structure.items():
                    if key not in ["earnings", "deductions"]:
                        doc.set(key, value)
                
                for earning in structure.get("earnings", []):
                    if frappe.db.exists("Salary Component", earning["salary_component"]):
                        doc.append("earnings", earning)
                    
                for deduction in structure.get("deductions", []):
                    if frappe.db.exists("Salary Component", deduction["salary_component"]):
                        doc.append("deductions", deduction)
                
                doc.company = company
                    
                doc.insert(ignore_permissions=True)
                frappe.db.commit()
            except Exception as e:
                frappe.log_error(f"Error creating salary structure {structure['name']}: {str(e)}")

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

def create_bpjs_supplier():
    """Create BPJS supplier if not exists"""
    if not frappe.db.exists("Supplier", "BPJS"):
        try:
            supplier = frappe.get_doc({
                "doctype": "Supplier",
                "supplier_name": "BPJS",
                "supplier_group": "Government",
                "supplier_type": "Government",
                "country": "Indonesia",
                "default_currency": "IDR",
                "default_price_list": "Standard Buying",
                "payment_terms": "",
                "is_internal_supplier": 0,
                "is_transporter": 0,
                "represents_company": None,
                "tax_category": "Government" if frappe.db.exists("Tax Category", "Government") else "",
                "tax_withholding_category": "",
                "docstatus": 1
            })
            supplier.insert()
            frappe.db.commit()
        except Exception as e:
            frappe.log_error(f"Failed to create BPJS supplier: {str(e)}")
