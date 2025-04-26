# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
import json

def process_fixtures():
    """Proses semua fixtures setelah migrate"""
    create_salary_structures()
    frappe.db.commit()
    
def create_salary_structures():
    """Buat atau update salary structure dari fixture"""
    # Define all salary structures here
    structures = [
        {
            "doctype": "Salary Structure",
            "name": "Struktur Gaji Tetap G1",
            "is_active": "Yes",
            "payroll_frequency": "Monthly",
            "company": "%",  # Wildcard untuk semua company
            "mode_of_payment": "Cash",
            "currency": "IDR",
            "tax_calculation_method": "Manual",
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
                },
                {
                    "salary_component": "Insentif",
                    "amount": 0,
                    "amount_based_on_formula": 0,
                    "condition": "",
                    "description": "Diisi manual sesuai kinerja karyawan"
                },
                {
                    "salary_component": "Bonus",
                    "amount": 0,
                    "amount_based_on_formula": 0,
                    "condition": "",
                    "description": "Diisi manual sesuai kebijakan perusahaan"
                }
            ],
            "deductions": [
                {
                    "salary_component": "BPJS JHT Employee",
                    "amount_based_on_formula": 0,
                    "amount": 0,
                    "condition": "ikut_bpjs_ketenagakerjaan",
                    "do_not_include_in_total": 0
                },
                {
                    "salary_component": "BPJS JP Employee",
                    "amount_based_on_formula": 0,
                    "amount": 0,
                    "condition": "ikut_bpjs_ketenagakerjaan",
                    "do_not_include_in_total": 0
                },
                {
                    "salary_component": "BPJS Kesehatan Employee",
                    "amount_based_on_formula": 0,
                    "amount": 0,
                    "condition": "ikut_bpjs_kesehatan",
                    "do_not_include_in_total": 0
                },
                {
                    "salary_component": "PPh 21",
                    "amount_based_on_formula": 0,
                    "amount": 0,
                    "condition": "not penghasilan_final",
                    "do_not_include_in_total": 0
                },
                {
                    "salary_component": "BPJS JHT Employer",
                    "amount_based_on_formula": 0,
                    "amount": 0,
                    "condition": "ikut_bpjs_ketenagakerjaan",
                    "statistical_component": 1,
                    "do_not_include_in_total": 1
                },
                {
                    "salary_component": "BPJS JP Employer",
                    "amount_based_on_formula": 0,
                    "amount": 0,
                    "condition": "ikut_bpjs_ketenagakerjaan",
                    "statistical_component": 1,
                    "do_not_include_in_total": 1
                },
                {
                    "salary_component": "BPJS JKK",
                    "amount_based_on_formula": 0,
                    "amount": 0,
                    "condition": "ikut_bpjs_ketenagakerjaan", 
                    "statistical_component": 1,
                    "do_not_include_in_total": 1
                },
                {
                    "salary_component": "BPJS JKM",
                    "amount_based_on_formula": 0,
                    "amount": 0,
                    "condition": "ikut_bpjs_ketenagakerjaan",
                    "statistical_component": 1,
                    "do_not_include_in_total": 1
                },
                {
                    "salary_component": "BPJS Kesehatan Employer",
                    "amount_based_on_formula": 0,
                    "amount": 0,
                    "condition": "ikut_bpjs_kesehatan",
                    "statistical_component": 1,
                    "do_not_include_in_total": 1
                }
            ],
            "note": "Nilai komponen BPJS dan PPh 21 dihitung otomatis berdasarkan pengaturan di BPJS Settings dan PPh 21 Settings."
        }
        # Tambahkan struktur gaji lainnya disini
    ]
    
    # Create or update salary structures
    for structure in structures:
        # Check if salary structure already exists
        if frappe.db.exists("Salary Structure", structure["name"]):
            # Update existing salary structure
            doc = frappe.get_doc("Salary Structure", structure["name"])
            
            # Update basic fields
            for key, value in structure.items():
                if key not in ["name", "doctype", "earnings", "deductions"]:
                    setattr(doc, key, value)
            
            # Clear existing earnings and deductions
            doc.earnings = []
            doc.deductions = []
            
            # Add new earnings
            for earning in structure.get("earnings", []):
                doc.append("earnings", earning)
                
            # Add new deductions
            for deduction in structure.get("deductions", []):
                doc.append("deductions", deduction)
            
            # Save the document
            doc.save()
            print(f"Updated Salary Structure: {structure['name']}")
        else:
            # Create new salary structure
            doc = frappe.get_doc(structure)
            doc.insert(ignore_permissions=True)
            print(f"Created Salary Structure: {structure['name']}")