# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate

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
    count = 0
    for structure in structures:
        doc = frappe.get_doc("Salary Structure", structure.name)
        
        # Set income_tax_slab field
        doc.income_tax_slab = default_tax_slab_name
        
        # Set tax calculation method to manual untuk memastikan perhitungan PPh 21 tetap di modul kita
        doc.tax_calculation_method = "Manual"
        
        try:
            doc.save(ignore_permissions=True)
            count += 1
            print(f"Updated {count}/{len(structures)}: {doc.name}")
        except Exception as e:
            print(f"Error updating {doc.name}: {str(e)}")
            
    frappe.db.commit()
    print(f"Berhasil update {count} dari {len(structures)} Salary Structure")
    return count

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
    count = 0
    for assignment in assignments:
        try:
            frappe.db.set_value(
                "Salary Structure Assignment",
                assignment.name,
                "income_tax_slab",
                default_tax_slab_name
            )
            count += 1
            print(f"Updated {count}/{len(assignments)}: {assignment.name}")
        except Exception as e:
            print(f"Error updating {assignment.name}: {str(e)}")
    
    frappe.db.commit()
    print(f"Berhasil update {count} dari {len(assignments)} Salary Structure Assignment")
    return count

def check_salary_structure_tax_method():
    """Periksa metode perhitungan pajak di Salary Structure"""
    structures = frappe.get_all(
        "Salary Structure", 
        filters={"is_active": "Yes"},
        fields=["name", "tax_calculation_method", "income_tax_slab"]
    )
    
    print("Daftar Salary Structure aktif:")
    for idx, ss in enumerate(structures, 1):
        print(f"{idx}. {ss.name}")
        print(f"   - Tax Calculation Method: {ss.tax_calculation_method or 'None'}")
        print(f"   - Income Tax Slab: {ss.income_tax_slab or 'None'}")
        print()
        
    return structures

def check_salary_structure_assignments():
    """Periksa semua Salary Structure Assignment"""
    assignments = frappe.get_all(
        "Salary Structure Assignment",
        filters={"docstatus": 1},
        fields=["name", "employee", "employee_name", "salary_structure", "income_tax_slab"]
    )
    
    print("Daftar Salary Structure Assignment:")
    for idx, ssa in enumerate(assignments, 1):
        print(f"{idx}. {ssa.name}")
        print(f"   - Employee: {ssa.employee} ({ssa.employee_name})")
        print(f"   - Salary Structure: {ssa.salary_structure}")
        print(f"   - Income Tax Slab: {ssa.income_tax_slab or 'None'}")
        print()
        
    return assignments

def fix_all_salary_structures_and_assignments():
    """Perbaiki semua Salary Structure dan Assignment sekaligus"""
    from payroll_indonesia.utilities.tax_slab import create_default_tax_slab
    
    # Langkah 1: Pastikan ada Income Tax Slab default
    tax_slab_name = create_default_tax_slab()
    if not tax_slab_name:
        print("Gagal membuat Income Tax Slab default.")
        return False
    
    # Langkah 2: Update semua Salary Structure
    ss_count = update_salary_structures()
    
    # Langkah 3: Update semua Salary Structure Assignment
    ssa_count = update_existing_assignments()
    
    print(f"Proses perbaikan selesai:")
    print(f"- Income Tax Slab dibuat: {tax_slab_name}")
    print(f"- Salary Structure diupdate: {ss_count}")
    print(f"- Salary Structure Assignment diupdate: {ssa_count}")
    
    return True# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate

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
    count = 0
    for structure in structures:
        doc = frappe.get_doc("Salary Structure", structure.name)
        
        # Set income_tax_slab field
        doc.income_tax_slab = default_tax_slab_name
        
        # Set tax calculation method to manual untuk memastikan perhitungan PPh 21 tetap di modul kita
        doc.tax_calculation_method = "Manual"
        
        try:
            doc.save(ignore_permissions=True)
            count += 1
            print(f"Updated {count}/{len(structures)}: {doc.name}")
        except Exception as e:
            print(f"Error updating {doc.name}: {str(e)}")
            
    frappe.db.commit()
    print(f"Berhasil update {count} dari {len(structures)} Salary Structure")
    return count

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
    count = 0
    for assignment in assignments:
        try:
            frappe.db.set_value(
                "Salary Structure Assignment",
                assignment.name,
                "income_tax_slab",
                default_tax_slab_name
            )
            count += 1
            print(f"Updated {count}/{len(assignments)}: {assignment.name}")
        except Exception as e:
            print(f"Error updating {assignment.name}: {str(e)}")
    
    frappe.db.commit()
    print(f"Berhasil update {count} dari {len(assignments)} Salary Structure Assignment")
    return count

def check_salary_structure_tax_method():
    """Periksa metode perhitungan pajak di Salary Structure"""
    structures = frappe.get_all(
        "Salary Structure", 
        filters={"is_active": "Yes"},
        fields=["name", "tax_calculation_method", "income_tax_slab"]
    )
    
    print("Daftar Salary Structure aktif:")
    for idx, ss in enumerate(structures, 1):
        print(f"{idx}. {ss.name}")
        print(f"   - Tax Calculation Method: {ss.tax_calculation_method or 'None'}")
        print(f"   - Income Tax Slab: {ss.income_tax_slab or 'None'}")
        print()
        
    return structures

def check_salary_structure_assignments():
    """Periksa semua Salary Structure Assignment"""
    assignments = frappe.get_all(
        "Salary Structure Assignment",
        filters={"docstatus": 1},
        fields=["name", "employee", "employee_name", "salary_structure", "income_tax_slab"]
    )
    
    print("Daftar Salary Structure Assignment:")
    for idx, ssa in enumerate(assignments, 1):
        print(f"{idx}. {ssa.name}")
        print(f"   - Employee: {ssa.employee} ({ssa.employee_name})")
        print(f"   - Salary Structure: {ssa.salary_structure}")
        print(f"   - Income Tax Slab: {ssa.income_tax_slab or 'None'}")
        print()
        
    return assignments

def fix_all_salary_structures_and_assignments():
    """Perbaiki semua Salary Structure dan Assignment sekaligus"""
    from payroll_indonesia.utilities.tax_slab import create_default_tax_slab
    
    # Langkah 1: Pastikan ada Income Tax Slab default
    tax_slab_name = create_default_tax_slab()
    if not tax_slab_name:
        print("Gagal membuat Income Tax Slab default.")
        return False
    
    # Langkah 2: Update semua Salary Structure
    ss_count = update_salary_structures()
    
    # Langkah 3: Update semua Salary Structure Assignment
    ssa_count = update_existing_assignments()
    
    print(f"Proses perbaikan selesai:")
    print(f"- Income Tax Slab dibuat: {tax_slab_name}")
    print(f"- Salary Structure diupdate: {ss_count}")
    print(f"- Salary Structure Assignment diupdate: {ssa_count}")
    
    return True