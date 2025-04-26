# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, cstr

def create_default_tax_slab():
    """
    Function for compatibility - calls create_income_tax_slab()
    """
    return create_income_tax_slab()

def create_income_tax_slab():
    """Buat Income Tax Slab untuk Indonesia"""
    
    # Cek apakah kolom is_default ada
    has_is_default = check_column_exists("Income Tax Slab", "is_default")
    
    # Cek apakah sudah ada tax slab untuk IDR
    existing_slabs = frappe.get_all("Income Tax Slab", filters={"currency": "IDR"})
    if existing_slabs:
        print(f"Income Tax Slab untuk IDR sudah ada: {existing_slabs[0].name}")
        return existing_slabs[0].name
    
    try:
        # Buat tax slab baru
        tax_slab = frappe.new_doc("Income Tax Slab")
        tax_slab.title = "Indonesia Tax Slab"
        tax_slab.effective_from = getdate("2023-01-01")
        tax_slab.company = frappe.defaults.get_defaults().get("company")
        tax_slab.currency = "IDR"
        
        # Set is_default jika field tersebut ada
        if has_is_default:
            tax_slab.is_default = 1
        
        if hasattr(tax_slab, "disabled"):
            tax_slab.disabled = 0
        
        # Tambahkan slabs (sesuaikan dengan tarif pajak Indonesia)
        tax_slab.slabs = []
        tax_slab.append("slabs", {
            "from_amount": 0,
            "to_amount": 60000000,
            "percent_deduction": 5,
            "condition": ""
        })
        tax_slab.append("slabs", {
            "from_amount": 60000000,
            "to_amount": 250000000,
            "percent_deduction": 15,
            "condition": ""
        })
        tax_slab.append("slabs", {
            "from_amount": 250000000,
            "to_amount": 500000000,
            "percent_deduction": 25,
            "condition": ""
        })
        tax_slab.append("slabs", {
            "from_amount": 500000000,
            "to_amount": 5000000000,
            "percent_deduction": 30,
            "condition": ""
        })
        tax_slab.append("slabs", {
            "from_amount": 5000000000,
            "to_amount": 0,  # 0 berarti unlimited
            "percent_deduction": 35,
            "condition": ""
        })
        
        # Simpan tax slab
        tax_slab.insert(ignore_permissions=True)
        frappe.db.commit()
        actual_name = tax_slab.name
        print(f"Berhasil membuat Income Tax Slab: {actual_name}")
        return actual_name
        
    except Exception as e:
        frappe.db.rollback()
        print(f"Error membuat Income Tax Slab: {cstr(e)}")
        frappe.log_error(f"Error membuat Income Tax Slab: {cstr(e)}", "Tax Slab Error")
        return None

def get_default_tax_slab():
    """Mendapatkan nama Income Tax Slab default"""
    try:
        # Cek apakah kolom is_default ada
        has_is_default = check_column_exists("Income Tax Slab", "is_default")
        
        if has_is_default:
            # Cari Income Tax Slab default
            default_slab = frappe.db.get_value("Income Tax Slab", 
                                            {"currency": "IDR", "is_default": 1}, 
                                            "name")
            if default_slab:
                return default_slab
        
        # Jika tidak ada atau kolom is_default tidak ada, ambil Tax Slab IDR pertama
        tax_slabs = frappe.get_all("Income Tax Slab", 
                                    filters={"currency": "IDR"}, 
                                    fields=["name"])
        if tax_slabs:
            return tax_slabs[0].name
            
        # Jika belum ada, buat baru
        return create_income_tax_slab()
        
    except Exception as e:
        frappe.log_error(f"Error getting default tax slab: {cstr(e)}", "Tax Slab Error")
        return None

def check_column_exists(doctype, column):
    """Check if column exists in DocType"""
    try:
        frappe.db.sql(f"SELECT `{column}` FROM `tab{doctype}` LIMIT 1")
        return True
    except Exception:
        return False

def update_salary_structures():
    """Update semua Salary Structure untuk bypass validasi Income Tax Slab"""
    
    # Ambil semua Salary Structure yang aktif
    structures = frappe.get_all("Salary Structure", filters={"is_active": "Yes"})
    
    # Dapatkan default Income Tax Slab
    default_tax_slab = get_default_tax_slab()
    
    if not default_tax_slab:
        print("Gagal mendapatkan/membuat Income Tax Slab default.")
        return
    
    # Update setiap Salary Structure
    for structure in structures:
        doc = frappe.get_doc("Salary Structure", structure.name)
        
        # Set income_tax_slab field
        doc.income_tax_slab = default_tax_slab
        
        # Set tax calculation method to manual untuk memastikan perhitungan PPh 21 tetap di modul kita
        doc.tax_calculation_method = "Manual"
        
        try:
            doc.save()
            print(f"Updated Salary Structure: {doc.name}")
        except Exception as e:
            print(f"Error updating {doc.name}: {str(e)}")
            
    frappe.db.commit()
    print("Semua Salary Structure telah diupdate")

def update_existing_assignments():
    """Update existing Salary Structure Assignments with default Income Tax Slab"""
    
    # Get default Income Tax Slab
    default_tax_slab = get_default_tax_slab()
    
    if not default_tax_slab:
        print("Gagal mendapatkan/membuat Income Tax Slab default.")
        return
        
    # Get all existing assignments without income tax slab
    assignments = frappe.get_all(
        "Salary Structure Assignment",
        filters={"income_tax_slab": ["is", "not set"]},
        fields=["name"]
    )
    
    # Update each assignment
    for assignment in assignments:
        try:
            frappe.db.set_value(
                "Salary Structure Assignment",
                assignment.name,
                "income_tax_slab",
                default_tax_slab
            )
            print(f"Updated Assignment: {assignment.name}")
        except Exception as e:
            print(f"Error updating {assignment.name}: {str(e)}")
    
    frappe.db.commit()
    print(f"Updated {len(assignments)} Salary Structure Assignments")