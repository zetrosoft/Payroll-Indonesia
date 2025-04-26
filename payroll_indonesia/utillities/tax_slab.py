# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate

def create_default_tax_slab():
    """Buat Income Tax Slab default untuk Indonesia"""
    
    # Cek apakah sudah ada tax slab untuk IDR
    if frappe.db.exists("Income Tax Slab", {"currency": "IDR", "is_default": 1}):
        print("Default Income Tax Slab untuk IDR sudah ada")
        return
    
    # Buat tax slab baru
    tax_slab = frappe.new_doc("Income Tax Slab")
    tax_slab.name = "Indonesia Tax Slab - IDR"
    tax_slab.effective_from = getdate("2023-01-01")  # Tanggal berlaku
    tax_slab.company = frappe.defaults.get_defaults().get("company")
    tax_slab.currency = "IDR"
    tax_slab.is_default = 1
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
    try:
        tax_slab.insert(ignore_permissions=True)
        frappe.db.commit()
        print(f"Berhasil membuat Income Tax Slab: {tax_slab.name}")
        return tax_slab.name
    except Exception as e:
        frappe.db.rollback()
        print(f"Error membuat Income Tax Slab: {str(e)}")
        return None

def update_salary_structures():
    """Update semua Salary Structure untuk bypass validasi Income Tax Slab"""
    
    # Ambil semua Salary Structure yang aktif
    structures = frappe.get_all("Salary Structure", filters={"is_active": "Yes"})
    
    # Dapatkan default Income Tax Slab
    default_tax_slab = frappe.get_all(
        "Income Tax Slab", 
        filters={"currency": "IDR", "is_default": 1},
        limit=1
    )
    
    if not default_tax_slab:
        print("Tidak ada Income Tax Slab default. Jalankan create_default_tax_slab() terlebih dahulu.")
        return
        
    default_tax_slab_name = default_tax_slab[0].name
    
    # Update setiap Salary Structure
    for structure in structures:
        doc = frappe.get_doc("Salary Structure", structure.name)
        
        # Set income_tax_slab field
        doc.income_tax_slab = default_tax_slab_name
        
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
    default_tax_slab = frappe.get_all(
        "Income Tax Slab", 
        filters={"currency": "IDR", "is_default": 1},
        limit=1
    )
    
    if not default_tax_slab:
        print("No default Income Tax Slab found")
        return
        
    default_tax_slab_name = default_tax_slab[0].name
    
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
                default_tax_slab_name
            )
            print(f"Updated Assignment: {assignment.name}")
        except Exception as e:
            print(f"Error updating {assignment.name}: {str(e)}")
    
    frappe.db.commit()
    print(f"Updated {len(assignments)} Salary Structure Assignments")