# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from hrms.payroll.doctype.salary_structure.salary_structure import SalaryStructure

class CustomSalaryStructure(SalaryStructure):
    def validate(self):
        """Override validasi Salary Structure untuk mengizinkan company='%'"""
        # Simpan nilai company original
        original_company = self.company
        
        # Jika company adalah wildcard '%', gunakan company default untuk validasi saja
        if self.company == "%":
            default_company = frappe.defaults.get_global_default("company")
            self.company = default_company
            
        # Jalankan validasi standard
        super().validate()
        
        # Kembalikan nilai company ke wildcard jika itu nilai aslinya
        if original_company == "%":
            self.company = original_company
    
    def on_update(self):
        """On update yang minimal tanpa mengakses field yang mungkin tidak ada"""
        try:
            super(CustomSalaryStructure, self).on_update()
        except:
            pass

# Fungsi untuk membuat/memperbarui Salary Structure default
def create_default_salary_structure():
    """Buat atau update Salary Structure secara programatis"""
    try:
        # Definisi struktur gaji default
        structure_name = "Struktur Gaji Tetap G1"
        
        # Dapatkan company default dari site
        default_company = frappe.defaults.get_global_default("company")
        company_value = default_company or "%"
        
        # Definisi komponen earnings
        earnings = [
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
        ]
        
        # Definisi komponen deductions
        deductions = [
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
        ]
        
        # Cek apakah struktur sudah ada
        if frappe.db.exists("Salary Structure", structure_name):
            # Update struktur yang sudah ada
            ss = frappe.get_doc("Salary Structure", structure_name)
            
            # Update field dasar
            ss.is_active = "Yes"
            ss.payroll_frequency = "Monthly"
            ss.company = company_value
            ss.currency = "IDR"
            
            # Hapus komponen lama
            ss.earnings = []
            ss.deductions = []
            
            # Tambahkan komponen baru
            for e in earnings:
                ss.append("earnings", e)
                
            for d in deductions:
                ss.append("deductions", d)
            
            # Note
            ss.note = "Nilai komponen BPJS dan PPh 21 dihitung otomatis berdasarkan pengaturan di BPJS Settings dan PPh 21 Settings."
            
            # Coba set tax calculation method jika field ada
            try:
                ss.tax_calculation_method = "Manual"
            except:
                pass
                
            # Save dengan ignore_permissions
            ss.flags.ignore_permissions = True
            ss.save()
            
            frappe.db.commit()
            print(f"Updated Salary Structure: {structure_name}")
            
        else:
            # Buat struktur baru
            ss_dict = {
                "doctype": "Salary Structure",
                "name": structure_name,
                "salary_structure_name": structure_name,
                "is_active": "Yes",
                "payroll_frequency": "Monthly",
                "company": company_value,
                "mode_of_payment": "Cash",
                "currency": "IDR",
                "earnings": earnings,
                "deductions": deductions,
                "note": "Nilai komponen BPJS dan PPh 21 dihitung otomatis berdasarkan pengaturan di BPJS Settings dan PPh 21 Settings."
            }
            
            # Buat dokumen baru
            ss = frappe.get_doc(ss_dict)
            
            # Coba set tax calculation method jika field ada
            try:
                ss.tax_calculation_method = "Manual"
            except:
                pass
                
            # Insert dengan ignore_permissions
            ss.insert(ignore_permissions=True)
            
            frappe.db.commit()
            print(f"Created Salary Structure: {structure_name}")
            
        return True
        
    except Exception as e:
        frappe.log_error(f"Error creating/updating Salary Structure: {str(e)}", "Salary Structure Setup")
        return False

# Fungsi untuk memastikan komponen salary tersedia
def create_salary_components():
    """Buat komponen gaji jika belum ada"""
    try:
        # Daftar komponen earnings
        earnings = [
            {"salary_component": "Gaji Pokok", "type": "Earning", "is_tax_applicable": 1},
            {"salary_component": "Tunjangan Makan", "type": "Earning", "is_tax_applicable": 1},
            {"salary_component": "Tunjangan Transport", "type": "Earning", "is_tax_applicable": 1},
            {"salary_component": "Insentif", "type": "Earning", "is_tax_applicable": 1},
            {"salary_component": "Bonus", "type": "Earning", "is_tax_applicable": 1}
        ]
        
        # Daftar komponen deductions
        deductions = [
            {"salary_component": "PPh 21", "type": "Deduction", "variable_based_on_taxable_salary": 1},
            {"salary_component": "BPJS JHT Employee", "type": "Deduction"},
            {"salary_component": "BPJS JP Employee", "type": "Deduction"},
            {"salary_component": "BPJS Kesehatan Employee", "type": "Deduction"},
            {"salary_component": "BPJS JHT Employer", "type": "Deduction", "statistical_component": 1, "do_not_include_in_total": 1},
            {"salary_component": "BPJS JP Employer", "type": "Deduction", "statistical_component": 1, "do_not_include_in_total": 1},
            {"salary_component": "BPJS JKK", "type": "Deduction", "statistical_component": 1, "do_not_include_in_total": 1},
            {"salary_component": "BPJS JKM", "type": "Deduction", "statistical_component": 1, "do_not_include_in_total": 1},
            {"salary_component": "BPJS Kesehatan Employer", "type": "Deduction", "statistical_component": 1, "do_not_include_in_total": 1}
        ]
        
        # Buat semua komponen
        for comp in earnings + deductions:
            name = comp["salary_component"]
            if not frappe.db.exists("Salary Component", name):
                doc = frappe.new_doc("Salary Component")
                doc.salary_component = name
                for key, value in comp.items():
                    if key != "salary_component":
                        doc.set(key, value)
                doc.insert(ignore_permissions=True)
                frappe.db.commit()
                print(f"Created Salary Component: {name}")
                
        return True
    except Exception as e:
        frappe.log_error(f"Error creating salary components: {str(e)}", "Setup")
        return False

# Fungsi untuk update salary structure secara terjadwal
def update_salary_structures():
    """Task terjadwal untuk memperbarui salary structure"""
    try:
        create_salary_components()
        create_default_salary_structure()
        return "Updated salary structures successfully"
    except Exception as e:
        frappe.log_error(f"Failed to update salary structures: {str(e)}", "Scheduled Task")
        return f"Error: {str(e)}"
            
    def on_update(self):
        """Pastikan income_tax_slab terisi jika ada component PPh 21"""
        super().on_update()
        
        # Cek apakah ada komponen PPh 21
        has_tax_component = False
        for d in self.deductions:
            if d.salary_component == "PPh 21":
                has_tax_component = True
                break
                
        # Periksa apakah field income_tax_slab ada dalam doctype
        field_exists = False
        try:
            # Cek apakah attribut ada atau bisa diakses dari db
            if hasattr(self, 'income_tax_slab'):
                field_exists = True
            else:
                # Coba ambil dari database
                tax_slab_value = frappe.db.get_value("Salary Structure", self.name, "income_tax_slab")
                if tax_slab_value is not None:
                    field_exists = True
        except Exception:
            field_exists = False
                
        # Jika ada komponen PPh 21 dan field income_tax_slab ada, tapi nilainya kosong
        if has_tax_component and field_exists:
            tax_slab_value = getattr(self, 'income_tax_slab', None) or frappe.db.get_value("Salary Structure", self.name, "income_tax_slab")
            
            if not tax_slab_value:
                # Cek apakah ada Income Tax Slab default
                tax_slab = frappe.db.get_value("Income Tax Slab", {"currency": self.currency, "is_default": 1}, "name")
                
                if tax_slab:
                    try:
                        # Update langsung ke DB untuk menghindari error
                        update_dict = {"tax_calculation_method": "Manual"}
                        
                        # Tambahkan income_tax_slab jika field ada di DocType
                        if field_exists:
                            update_dict["income_tax_slab"] = tax_slab
                            
                        frappe.db.set_value("Salary Structure", self.name, update_dict)
                        frappe.db.commit()
                    except Exception as e:
                        # Log error tapi jangan crash
                        frappe.log_error(f"Failed to update income_tax_slab: {str(e)}", "CustomSalaryStructure")