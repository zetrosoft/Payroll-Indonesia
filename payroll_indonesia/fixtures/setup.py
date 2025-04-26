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
    
    # Setup Settings immediately (synchronously)
    setup_pph21_defaults()
    setup_pph21_ter()
    
    frappe.msgprint(_(
        "Payroll Indonesia berhasil diinstal. PPh 21 Settings telah dikonfigurasi dengan metode TER."
    ), indicator="green", title=_("Installation Complete"))

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
    """Setup default PPh 21 configuration with TER method as default

    Sets up the income tax settings with complete PTKP values and tax brackets
    according to Indonesian tax regulations (PMK terbaru)
    """
    try:
        # Check if PPh 21 Settings DocType exists
        if not frappe.db.exists("DocType", "PPh 21 Settings"):
            frappe.log_error("DocType 'PPh 21 Settings' tidak ditemukan. Pastikan DocType sudah diinstall dengan benar.")
            return
        
        # Check if settings already exist
        settings = None
        if frappe.db.exists("PPh 21 Settings", "PPh 21 Settings"):
            # Get existing settings
            settings = frappe.get_doc("PPh 21 Settings", "PPh 21 Settings")
            frappe.msgprint("PPh 21 Settings already exists, updating configuration...")
            
            # Clear existing PTKP and bracket tables to avoid duplicates
            settings.ptkp_table = []
            settings.bracket_table = []
        else:
            # Create new settings
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
            settings.append("bracket_table", bracket)
        
        # Save settings
        if settings.name == "PPh 21 Settings":
            settings.save(ignore_permissions=True)
        else:
            settings.insert(ignore_permissions=True)
            
        frappe.db.commit()
        frappe.msgprint("PPh 21 Settings configured successfully with TER method")
        
        return settings
    except Exception as e:
        frappe.log_error(f"Error in setup_pph21_defaults: {str(e)}")
        frappe.msgprint(f"Error setting up PPh 21: {str(e)}", indicator="red")

def setup_pph21_ter():
    """Setup default TER rates based on PMK-168/PMK.010/2023

    TER (Tarif Efektif Rata-rata) adalah metode perhitungan alternatif 
    untuk PPh 21 yang menggunakan tarif yang sudah ditetapkan berdasarkan 
    rentang penghasilan dan status PTKP
    """
    try:
        # Check if the doctype exists
        if not frappe.db.exists("DocType", "PPh 21 TER Table"):
            frappe.log_error("PPh 21 TER Table DocType not found. Skipping TER setup.")
            return
        
        # Clear existing TER rates to avoid duplicates
        frappe.db.sql("DELETE FROM `tabPPh 21 TER Table`")
        frappe.db.commit()
        
        # Create TER rates based on PMK-168/PMK.010/2023
        # Data sesuai dengan Lampiran PMK-168/PMK.010/2023
        
        # Daftar semua status pajak
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
        
        # Counter untuk jumlah record yang diinsert
        count = 0
        
        # Loop semua status pajak
        for status in status_list:
            if status in ter_rates:
                # Loop semua rate bracket untuk status pajak ini
                for rate_data in ter_rates[status]:
                    # Buat deskripsi yang informatif
                    description = f"{status} "
                    
                    if rate_data["income_to"] == 0:
                        description += f"di atas Rp{rate_data['income_from']:,.0f}"
                    elif rate_data["income_from"] == 0:
                        description += f"s.d Rp{rate_data['income_to']:,.0f}"
                    else:
                        description += f"Rp{rate_data['income_from']:,.0f} s.d Rp{rate_data['income_to']:,.0f}"
                    
                    # Buat record TER baru
                    doc = frappe.get_doc({
                        "doctype": "PPh 21 TER Table",
                        "status_pajak": status,
                        "income_from": rate_data["income_from"],
                        "income_to": rate_data["income_to"],
                        "rate": rate_data["rate"],
                        "description": description
                    })
                    doc.insert(ignore_permissions=True)
                    count += 1
        
        frappe.db.commit()
        frappe.msgprint(_(f"Berhasil membuat {count} rate TER untuk {len(status_list)} status pajak sesuai PMK-168/PMK.010/2023"))
            
    except Exception as e:
        frappe.log_error(f"Error setting up PPh 21 TER rates: {str(e)}")
        frappe.msgprint(f"Error saat mengatur rate TER: {str(e)}", indicator="red")
    try:
        # Check if the doctype exists
        if not frappe.db.exists("DocType", "PPh 21 TER Table"):
            frappe.log_error("PPh 21 TER Table DocType not found. Skipping TER setup.")
            return
        
        # Clear existing TER rates to avoid duplicates
        frappe.db.sql("DELETE FROM `tabPPh 21 TER Table`")
        frappe.db.commit()
        
        # Create TER rates based on PMK-168/PMK.010/2023
        # Data sesuai dengan PMK-168/PMK.010/2023
        default_rates = [
            # STATUS TK0 (Tidak Kawin 0 Tanggungan)
            {"status_pajak": "TK0", "income_from": 0, "income_to": 4500000, "rate": 0, "description": "TK0 sampai Rp4.500.000"},
            {"status_pajak": "TK0", "income_from": 4500000, "income_to": 5000000, "rate": 0.5, "description": "TK0 Rp4.500.000 s.d Rp5.000.000"},
            {"status_pajak": "TK0", "income_from": 5000000, "income_to": 6000000, "rate": 1.0, "description": "TK0 Rp5.000.000 s.d Rp6.000.000"},
            {"status_pajak": "TK0", "income_from": 6000000, "income_to": 7000000, "rate": 1.75, "description": "TK0 Rp6.000.000 s.d Rp7.000.000"},
            {"status_pajak": "TK0", "income_from": 7000000, "income_to": 8000000, "rate": 2.5, "description": "TK0 Rp7.000.000 s.d Rp8.000.000"},
            {"status_pajak": "TK0", "income_from": 8000000, "income_to": 9000000, "rate": 3.0, "description": "TK0 Rp8.000.000 s.d Rp9.000.000"},
            {"status_pajak": "TK0", "income_from": 9000000, "income_to": 10000000, "rate": 3.5, "description": "TK0 Rp9.000.000 s.d Rp10.000.000"},
            {"status_pajak": "TK0", "income_from": 10000000, "income_to": 15000000, "rate": 4.5, "description": "TK0 Rp10.000.000 s.d Rp15.000.000"},
            {"status_pajak": "TK0", "income_from": 15000000, "income_to": 20000000, "rate": 5.5, "description": "TK0 Rp15.000.000 s.d Rp20.000.000"},
            {"status_pajak": "TK0", "income_from": 20000000, "income_to": 500000000, "rate": 7.5, "description": "TK0 Rp20.000.000 s.d Rp500.000.000"},
            {"status_pajak": "TK0", "income_from": 500000000, "income_to": 0, "rate": 10.0, "description": "TK0 di atas Rp500.000.000"},
            
            # STATUS K0 (Kawin 0 Tanggungan)
            {"status_pajak": "K0", "income_from": 0, "income_to": 4875000, "rate": 0, "description": "K0 sampai Rp4.875.000"},
            {"status_pajak": "K0", "income_from": 4875000, "income_to": 5500000, "rate": 0.5, "description": "K0 Rp4.875.000 s.d Rp5.500.000"},
            {"status_pajak": "K0", "income_from": 5500000, "income_to": 6500000, "rate": 1.0, "description": "K0 Rp5.500.000 s.d Rp6.500.000"},
            {"status_pajak": "K0", "income_from": 6500000, "income_to": 7500000, "rate": 1.75, "description": "K0 Rp6.500.000 s.d Rp7.500.000"},
            {"status_pajak": "K0", "income_from": 7500000, "income_to": 8500000, "rate": 2.25, "description": "K0 Rp7.500.000 s.d Rp8.500.000"},
            {"status_pajak": "K0", "income_from": 8500000, "income_to": 9500000, "rate": 2.75, "description": "K0 Rp8.500.000 s.d Rp9.500.000"},
            {"status_pajak": "K0", "income_from": 9500000, "income_to": 11000000, "rate": 3.25, "description": "K0 Rp9.500.000 s.d Rp11.000.000"},
            {"status_pajak": "K0", "income_from": 11000000, "income_to": 15500000, "rate": 4.0, "description": "K0 Rp11.000.000 s.d Rp15.500.000"},
            {"status_pajak": "K0", "income_from": 15500000, "income_to": 21500000, "rate": 5.0, "description": "K0 Rp15.500.000 s.d Rp21.500.000"},
            {"status_pajak": "K0", "income_from": 21500000, "income_to": 500000000, "rate": 7.0, "description": "K0 Rp21.500.000 s.d Rp500.000.000"},
            {"status_pajak": "K0", "income_from": 500000000, "income_to": 0, "rate": 9.5, "description": "K0 di atas Rp500.000.000"},
            
            # STATUS K1 (Kawin 1 Tanggungan)
            {"status_pajak": "K1", "income_from": 0, "income_to": 5250000, "rate": 0, "description": "K1 sampai Rp5.250.000"},
            {"status_pajak": "K1", "income_from": 5250000, "income_to": 6000000, "rate": 0.5, "description": "K1 Rp5.250.000 s.d Rp6.000.000"},
            {"status_pajak": "K1", "income_from": 6000000, "income_to": 7000000, "rate": 1.0, "description": "K1 Rp6.000.000 s.d Rp7.000.000"},
            {"status_pajak": "K1", "income_from": 7000000, "income_to": 8000000, "rate": 1.5, "description": "K1 Rp7.000.000 s.d Rp8.000.000"},
            {"status_pajak": "K1", "income_from": 8000000, "income_to": 9000000, "rate": 2.0, "description": "K1 Rp8.000.000 s.d Rp9.000.000"},
            {"status_pajak": "K1", "income_from": 9000000, "income_to": 10000000, "rate": 2.5, "description": "K1 Rp9.000.000 s.d Rp10.000.000"},
            {"status_pajak": "K1", "income_from": 10000000, "income_to": 12000000, "rate": 3.0, "description": "K1 Rp10.000.000 s.d Rp12.000.000"},
            {"status_pajak": "K1", "income_from": 12000000, "income_to": 16000000, "rate": 3.75, "description": "K1 Rp12.000.000 s.d Rp16.000.000"},
            {"status_pajak": "K1", "income_from": 16000000, "income_to": 23000000, "rate": 4.75, "description": "K1 Rp16.000.000 s.d Rp23.000.000"},
            {"status_pajak": "K1", "income_from": 23000000, "income_to": 500000000, "rate": 6.75, "description": "K1 Rp23.000.000 s.d Rp500.000.000"},
            {"status_pajak": "K1", "income_from": 500000000, "income_to": 0, "rate": 9.25, "description": "K1 di atas Rp500.000.000"},
            
            # STATUS K2 (Kawin 2 Tanggungan)
            {"status_pajak": "K2", "income_from": 0, "income_to": 5625000, "rate": 0, "description": "K2 sampai Rp5.625.000"},
            {"status_pajak": "K2", "income_from": 5625000, "income_to": 6500000, "rate": 0.5, "description": "K2 Rp5.625.000 s.d Rp6.500.000"},
            {"status_pajak": "K2", "income_from": 6500000, "income_to": 7500000, "rate": 1.0, "description": "K2 Rp6.500.000 s.d Rp7.500.000"},
            {"status_pajak": "K2", "income_from": 7500000, "income_to": 8500000, "rate": 1.5, "description": "K2 Rp7.500.000 s.d Rp8.500.000"},
            {"status_pajak": "K2", "income_from": 8500000, "income_to": 9500000, "rate": 1.75, "description": "K2 Rp8.500.000 s.d Rp9.500.000"},
            {"status_pajak": "K2", "income_from": 9500000, "income_to": 10500000, "rate": 2.25, "description": "K2 Rp9.500.000 s.d Rp10.500.000"},
            {"status_pajak": "K2", "income_from": 10500000, "income_to": 13000000, "rate": 2.75, "description": "K2 Rp10.500.000 s.d Rp13.000.000"},
            {"status_pajak": "K2", "income_from": 13000000, "income_to": 16500000, "rate": 3.5, "description": "K2 Rp13.000.000 s.d Rp16.500.000"},
            {"status_pajak": "K2", "income_from": 16500000, "income_to": 24500000, "rate": 4.5, "description": "K2 Rp16.500.000 s.d Rp24.500.000"},
            {"status_pajak": "K2", "income_from": 24500000, "income_to": 500000000, "rate": 6.5, "description": "K2 Rp24.500.000 s.d Rp500.000.000"},
            {"status_pajak": "K2", "income_from": 500000000, "income_to": 0, "rate": 9.0, "description": "K2 di atas Rp500.000.000"},
            
            # STATUS K3 (Kawin 3 Tanggungan)
            {"status_pajak": "K3", "income_from": 0, "income_to": 6000000, "rate": 0, "description": "K3 sampai Rp6.000.000"},
            {"status_pajak": "K3", "income_from": 6000000, "income_to": 7000000, "rate": 0.5, "description": "K3 Rp6.000.000 s.d Rp7.000.000"},
            {"status_pajak": "K3", "income_from": 7000000, "income_to": 8000000, "rate": 1.0, "description": "K3 Rp7.000.000 s.d Rp8.000.000"},
            {"status_pajak": "K3", "income_from": 8000000, "income_to": 9000000, "rate": 1.25, "description": "K3 Rp8.000.000 s.d Rp9.000.000"},
            {"status_pajak": "K3", "income_from": 9000000, "income_to": 10000000, "rate": 1.75, "description": "K3 Rp9.000.000 s.d Rp10.000.000"},
            {"status_pajak": "K3", "income_from": 10000000, "income_to": 11000000, "rate": 2.0, "description": "K3 Rp10.000.000 s.d Rp11.000.000"},
            {"status_pajak": "K3", "income_from": 11000000, "income_to": 14000000, "rate": 2.5, "description": "K3 Rp11.000.000 s.d Rp14.000.000"},
            {"status_pajak": "K3", "income_from": 14000000, "income_to": 17000000, "rate": 3.25, "description": "K3 Rp14.000.000 s.d Rp17.000.000"},
            {"status_pajak": "K3", "income_from": 17000000, "income_to": 26000000, "rate": 4.25, "description": "K3 Rp17.000.000 s.d Rp26.000.000"},
            {"status_pajak": "K3", "income_from": 26000000, "income_to": 500000000, "rate": 6.25, "description": "K3 Rp26.000.000 s.d Rp500.000.000"},
            {"status_pajak": "K3", "income_from": 500000000, "income_to": 0, "rate": 8.75, "description": "K3 di atas Rp500.000.000"},
            
            # STATUS TK1 (Tidak Kawin 1 Tanggungan)
            {"status_pajak": "TK1", "income_from": 0, "income_to": 4875000, "rate": 0, "description": "TK1 sampai Rp4.875.000"},
            {"status_pajak": "TK1", "income_from": 4875000, "income_to": 5500000, "rate": 0.5, "description": "TK1 Rp4.875.000 s.d Rp5.500.000"},
            {"status_pajak": "TK1", "income_from": 5500000, "income_to": 6500000, "rate": 1.0, "description": "TK1 Rp5.500.000 s.d Rp6.500.000"},
            {"status_pajak": "TK1", "income_from": 6500000, "income_to": 7500000, "rate": 1.75, "description": "TK1 Rp6.500.000 s.d Rp7.500.000"},
            {"status_pajak": "TK1", "income_from": 7500000, "income_to": 8500000, "rate": 2.25, "description": "TK1 Rp7.500.000 s.d Rp8.500.000"},
            {"status_pajak": "TK1", "income_from": 8500000, "income_to": 9500000, "rate": 2.75, "description": "TK1 Rp8.500.000 s.d Rp9.500.000"},
            {"status_pajak": "TK1", "income_from": 9500000, "income_to": 11000000, "rate": 3.25, "description": "TK1 Rp9.500.000 s.d Rp11.000.000"},
            {"status_pajak": "TK1", "income_from": 11000000, "income_to": 15500000, "rate": 4.0, "description": "TK1 Rp11.000.000 s.d Rp15.500.000"},
            {"status_pajak": "TK1", "income_from": 15500000, "income_to": 21500000, "rate": 5.0, "description": "TK1 Rp15.500.000 s.d Rp21.500.000"},
            {"status_pajak": "TK1", "income_from": 21500000, "income_to": 500000000, "rate": 7.0, "description": "TK1 Rp21.500.000 s.d Rp500.000.000"},
            {"status_pajak": "TK1", "income_from": 500000000, "income_to": 0, "rate": 9.5, "description": "TK1 di atas Rp500.000.000"},
            
            # STATUS TK2 (Tidak Kawin 2 Tanggungan) - Tarif disamakan dengan K0 karena gabungan nilai PTKP sama
            {"status_pajak": "TK2", "income_from": 0, "income_to": 5250000, "rate": 0, "description": "TK2 sampai Rp5.250.000"},
            {"status_pajak": "TK2", "income_from": 5250000, "income_to": 6000000, "rate": 0.5, "description": "TK2 Rp5.250.000 s.d Rp6.000.000"},
            {"status_pajak": "TK2", "income_from": 6000000, "income_to": 7000000, "rate": 1.0, "description": "TK2 Rp6.000.000 s.d Rp7.000.000"},
            {"status_pajak": "TK2", "income_from": 7000000, "income_to": 8000000, "rate": 1.5, "description": "TK2 Rp7.000.000 s.d Rp8.000.000"},
            {"status_pajak": "TK2", "income_from": 8000000, "income_to": 9000000, "rate": 2.0, "description": "TK2 Rp8.000.000 s.d Rp9.000.000"},
            {"status_pajak": "TK2", "income_from": 9000000, "income_to": 10000000, "rate": 2.5, "description": "TK2 Rp9.000.000 s.d Rp10.000.000"},
            {"status_pajak": "TK2", "income_from": 10000000, "income_to": 12000000, "rate": 3.0, "description": "TK2 Rp10.000.000 s.d Rp12.000.000"},
            {"status_pajak": "TK2", "income_from": 12000000, "income_to": 16000000, "rate": 3.75, "description": "TK2 Rp12.000.000 s.d Rp16.000.000"},
            {"status_pajak": "TK2", "income_from": 16000000, "income_to": 23000000, "rate": 4.75, "description": "TK2 Rp16.000.000 s.d Rp23.000.000"},
            {"status_pajak": "TK2", "income_from": 23000000, "income_to": 500000000, "rate": 6.75, "description": "TK2 Rp23.000.000 s.d Rp500.000.000"},
            {"status_pajak": "TK2", "income_from": 500000000, "income_to": 0, "rate": 9.25, "description": "TK2 di atas Rp500.000.000"},
            
            # STATUS TK3 (Tidak Kawin 3 Tanggungan) - Tarif disamakan dengan K1 karena gabungan nilai PTKP sama
            {"status_pajak": "TK3", "income_from": 0, "income_to": 5625000, "rate": 0, "description": "TK3 sampai Rp5.625.000"},
            {"status_pajak": "TK3", "income_from": 5625000, "income_to": 6500000, "rate": 0.5, "description": "TK3 Rp5.625.000 s.d Rp6.500.000"},
            {"status_pajak": "TK3", "income_from": 6500000, "income_to": 7500000, "rate": 1.0, "description": "TK3 Rp6.500.000 s.d Rp7.500.000"},
            {"status_pajak": "TK3", "income_from": 7500000, "income_to": 8500000, "rate": 1.5, "description": "TK3 Rp7.500.000 s.d Rp8.500.000"},
            {"status_pajak": "TK3", "income_from": 8500000, "income_to": 9500000, "rate": 1.75, "description": "TK3 Rp8.500.000 s.d Rp9.500.000"},
            {"status_pajak": "TK3", "income_from": 9500000, "income_to": 10500000, "rate": 2.25, "description": "TK3 Rp9.500.000 s.d Rp10.500.000"},
            {"status_pajak": "TK3", "income_from": 10500000, "income_to": 13000000, "rate": 2.75, "description": "TK3 Rp10.500.000 s.d Rp13.000.000"},
            {"status_pajak": "TK3", "income_from": 13000000, "income_to": 16500000, "rate": 3.5, "description": "TK3 Rp13.000.000 s.d Rp16.500.000"},
            {"status_pajak": "TK3", "income_from": 16500000, "income_to": 24500000, "rate": 4.5, "description": "TK3 Rp16.500.000 s.d Rp24.500.000"},
            {"status_pajak": "TK3", "income_from": 24500000, "income_to": 500000000, "rate": 6.5, "description": "TK3 Rp24.500.000 s.d Rp500.000.000"},
            {"status_pajak": "TK3", "income_from": 500000000, "income_to": 0, "rate": 9.0, "description": "TK3 di atas Rp500.000.000"}
        ]
        
        # Create TER rate records
        for rate_data in default_rates:
            doc = frappe.get_doc({
                "doctype": "PPh 21 TER Table",
                "status_pajak": rate_data["status_pajak"],
                "income_from": rate_data["income_from"],
                "income_to": rate_data["income_to"],
                "rate": rate_data["rate"],
                "description": rate_data["description"]
            })
            doc.insert(ignore_permissions=True)
        
        frappe.db.commit()
        frappe.msgprint(_(f"Berhasil mengatur {len(default_rates)} rate TER sesuai PMK-168/PMK.010/2023"))
            
    except Exception as e:
        frappe.log_error(f"Error setting up PPh 21 TER rates: {str(e)}")
        frappe.msgprint(f"Error saat mengatur rate TER: {str(e)}", indicator="red")