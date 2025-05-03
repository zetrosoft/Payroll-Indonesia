# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate

def create_account(company, account_name, account_type, parent):
    """Create GL Account if not exists - Module level function"""
    abbr = frappe.get_cached_value('Company',  company,  'abbr')
    account_name = f"{account_name} - {abbr}"
    
    if not frappe.db.exists("Account", account_name):
        doc = frappe.get_doc({
            "doctype": "Account",
            "account_name": account_name.replace(f" - {abbr}", ""),
            "company": company,
            "parent_account": parent,
            "account_type": account_type,
            "account_currency": frappe.get_cached_value('Company', company, 'default_currency'),
            "is_group": 0
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        frappe.msgprint(f"Created account: {account_name}")
    
    return account_name

def create_parent_account(company):
    """Create or get parent account for BPJS accounts - Module level function"""
    parent_account = "Duties and Taxes - " + frappe.get_cached_value('Company',  company,  'abbr')
    parent_name = "BPJS Payable - " + frappe.get_cached_value('Company',  company,  'abbr')
    
    if not frappe.db.exists("Account", parent_name):
        frappe.get_doc({
            "doctype": "Account",
            "account_name": "BPJS Payable",
            "parent_account": parent_account,
            "company": company,
            "account_type": "Payable",
            "account_currency": frappe.get_cached_value('Company', company, 'default_currency'),
            "is_group": 1
        }).insert(ignore_permissions=True)
    
    return parent_name

class BPJSSettings(Document):
    def validate(self):
        """Validate BPJS settings"""
        self.validate_percentages()
        self.validate_max_salary()
        self.setup_accounts()
    
    def validate_percentages(self):
        """Validate BPJS percentage ranges"""
        validations = [
            ("kesehatan_employee_percent", 0, 5, "Persentase BPJS Kesehatan karyawan harus antara 0 dan 5%"),
            ("kesehatan_employer_percent", 0, 10, "Persentase BPJS Kesehatan perusahaan harus antara 0 dan 10%"),
            ("jht_employee_percent", 0, 5, "Persentase JHT karyawan harus antara 0 dan 5%"),
            ("jht_employer_percent", 0, 10, "Persentase JHT perusahaan harus antara 0 dan 10%"),
            ("jp_employee_percent", 0, 5, "Persentase JP karyawan harus antara 0 dan 5%"),
            ("jp_employer_percent", 0, 5, "Persentase JP perusahaan harus antara 0 dan 5%"),
            ("jkk_percent", 0, 5, "Persentase JKK harus antara 0 dan 5%"),
            ("jkm_percent", 0, 5, "Persentase JKM harus antara 0 dan 5%")
        ]
        
        for field, min_val, max_val, message in validations:
            value = flt(self.get(field))
            if value < min_val or value > max_val:
                frappe.throw(message)
    
    def validate_max_salary(self):
        """Validate maximum salary thresholds"""
        if flt(self.kesehatan_max_salary) <= 0:
            frappe.throw("Batas maksimal gaji BPJS Kesehatan harus lebih dari 0")
            
        if flt(self.jp_max_salary) <= 0:
            frappe.throw("Batas maksimal gaji JP harus lebih dari 0")
    
    def setup_accounts(self):
        """Setup GL accounts for BPJS components for all companies"""
        # Jika company tidak disebutkan secara eksplisit, ambil default company
        default_company = frappe.defaults.get_defaults().get("company")
        if not default_company:
            companies = frappe.get_all("Company", pluck="name")
            if not companies:
                frappe.throw("No company found. Please create a company before setting up BPJS accounts.")
        else:
            companies = [default_company]
    
        # Loop semua company dan buat account
        for company in companies:
            try:
                # Parent account where BPJS accounts will be created
                parent_name = create_parent_account(company)
            
                # Define BPJS accounts to be created
                bpjs_accounts = {
                    "kesehatan_account": {
                        "account_name": "BPJS Kesehatan Payable",
                        "account_type": "Payable",
                        "field": "kesehatan_account"
                    },
                    "jht_account": {
                        "account_name": "BPJS JHT Payable",
                        "account_type": "Payable",
                        "field": "jht_account"
                    },
                    "jp_account": {
                        "account_name": "BPJS JP Payable",
                        "account_type": "Payable",
                        "field": "jp_account"
                    },
                    "jkk_account": {
                        "account_name": "BPJS JKK Payable",
                        "account_type": "Payable",
                        "field": "jkk_account"
                    },
                    "jkm_account": {
                        "account_name": "BPJS JKM Payable",
                        "account_type": "Payable",
                        "field": "jkm_account"
                    }
                }
            
                # Create accounts and update settings
                for key, account_info in bpjs_accounts.items():
                    account = self.get(account_info["field"])
                    if not account:
                        account = create_account(
                            company=company,
                            account_name=account_info["account_name"],
                            account_type=account_info["account_type"],
                            parent=parent_name
                        )
                        self.set(account_info["field"], account)
            
                # Trigger mapping creation
                from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import create_default_mapping
                create_default_mapping(company)
            
            except Exception as e:
                frappe.log_error(f"Error setting up BPJS accounts for company {company}: {str(e)}", "BPJS Setup Error")
                continue
    
    def on_update(self):
        """Update related documents when settings change"""
        # Update salary structure assignments if needed
        self.update_salary_structures()
    
        # Pastikan semua company memiliki BPJS mapping
        self.ensure_bpjs_mapping_for_all_companies()

    def update_salary_structures(self):
        """Update BPJS components in active salary structures"""
        try:
            # Mencari salary structure aktif
            salary_structures = frappe.get_all(
                "Salary Structure",
                filters={"docstatus": 1, "is_active": "Yes"},
                pluck="name"
            )
            
            if not salary_structures:
                return  # Tidak ada salary structure yang perlu diupdate
                
            # Log untuk debug
            frappe.logger().info(f"Updating {len(salary_structures)} active salary structures with BPJS settings")
            
            # Ambil daftar BPJS components yang perlu diupdate
            bpjs_components = {
                "BPJS Kesehatan Employee": self.kesehatan_employee_percent,
                "BPJS Kesehatan Employer": self.kesehatan_employer_percent,
                "BPJS JHT Employee": self.jht_employee_percent,
                "BPJS JHT Employer": self.jht_employer_percent,
                "BPJS JP Employee": self.jp_employee_percent,
                "BPJS JP Employer": self.jp_employer_percent,
                "BPJS JKK": self.jkk_percent,
                "BPJS JKM": self.jkm_percent
            }
            
            # Update setiap salary structure
            updated_count = 0
            for ss_name in salary_structures:
                try:
                    ss = frappe.get_doc("Salary Structure", ss_name)
                    
                    # Flag untuk mengecek apakah ada perubahan
                    changes_made = False
                    
                    # Update setiap component
                    for component_name, percent in bpjs_components.items():
                        # Cari component di earnings atau deductions
                        found = False
                        for detail in ss.earnings:
                            if detail.salary_component == component_name:
                                found = True
                                if detail.amount_based_on_formula and detail.formula:
                                    # Jangan update jika menggunakan formula kustom
                                    continue
                                
                                # Update rate jika perlu
                                detail.amount = percent
                                changes_made = True
                                break
                                
                        if not found:
                            for detail in ss.deductions:
                                if detail.salary_component == component_name:
                                    found = True
                                    if detail.amount_based_on_formula and detail.formula:
                                        # Jangan update jika menggunakan formula kustom
                                        continue
                                    
                                    # Update rate jika perlu
                                    detail.amount = percent
                                    changes_made = True
                                    break
                    
                    # Simpan jika ada perubahan
                    if changes_made:
                        ss.flags.ignore_validate = True
                        ss.flags.ignore_mandatory = True
                        ss.save(ignore_permissions=True)
                        updated_count += 1
                        
                except Exception as e:
                    frappe.log_error(f"Error updating salary structure {ss_name}: {str(e)}", "BPJS Update Error")
                    continue
            
            if updated_count > 0:
                frappe.logger().info(f"Updated {updated_count} salary structures with new BPJS rates")
                
        except Exception as e:
            frappe.log_error(f"Error in update_salary_structures: {str(e)}", "BPJS Settings Update Error")

    def ensure_bpjs_mapping_for_all_companies(self):
        """Ensure all companies have BPJS mapping"""
        try:
            companies = frappe.get_all("Company", pluck="name")
        
            for company in companies:
                # Cek apakah mapping sudah ada
                mapping_exists = frappe.db.exists("BPJS Account Mapping", {"company": company})
            
                if not mapping_exists:
                    # Import di sini untuk menghindari circular import
                    from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import create_default_mapping
                
                    mapping_name = create_default_mapping(company)
                    if mapping_name:
                        frappe.logger().info(f"Created BPJS Account Mapping for {company} during BPJS Settings update")
                    else:
                        frappe.logger().warning(f"Failed to create BPJS Account Mapping for {company} during BPJS Settings update")
    
        except Exception as e:
            frappe.log_error(f"Error ensuring BPJS mapping for all companies: {str(e)}", "BPJS Settings Update Error")