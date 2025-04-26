# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-26 05:19:23 by dannyaudian

import frappe
from frappe import _
from frappe.utils import getdate

def validate_payroll_entry(doc, method=None):
    """Validasi tambahan untuk Payroll Entry"""
    validate_payroll_dates(doc)
    validate_employee_list(doc)
    
def validate_payroll_dates(doc):
    """Validasi tanggal payroll untuk konteks Indonesia"""
    # Validasi bahwa tanggal berada dalam bulan yang sama
    start_month = getdate(doc.start_date).month
    end_month = getdate(doc.end_date).month
    
    if start_month != end_month:
        frappe.msgprint(
            _("Untuk perhitungan pajak Indonesia, periode payroll sebaiknya berada dalam bulan yang sama."),
            title=_("Peringatan"),
            indicator="orange"
        )
        
def validate_employee_list(doc):
    """Validasi daftar karyawan"""
    if hasattr(doc, 'employees') and doc.employees:
        # Periksa apakah ada employee yang tidak valid
        invalid_employees = [emp for emp in doc.employees if not emp.employee]
        
        if invalid_employees:
            frappe.msgprint(
                _("Ditemukan {0} data karyawan yang tidak valid. Data ini akan diabaikan saat pemrosesan.").format(len(invalid_employees)),
                title=_("Perhatian"),
                indicator="orange"
            )
            
            # Hapus employee yang tidak valid
            doc.employees = [emp for emp in doc.employees if emp.employee]
            
def on_submit(doc, method=None):
    """Fungsi untuk menangani proses saat Payroll Entry disubmit"""
    # Cek apakah periode adalah Desember (untuk koreksi tahunan)
    is_december = getdate(doc.end_date).month == 12
    
    if is_december:
        frappe.msgprint(
            _("Periode Desember terdeteksi. Sistem akan otomatis melakukan perhitungan koreksi pajak tahunan."),
            title=_("Koreksi Pajak Tahunan"),
            indicator="blue"
        )
        
    # Tambahkan log
    frappe.log_error(
        f"Payroll Entry {doc.name} for period {doc.start_date} to {doc.end_date} submitted by {frappe.session.user}",
        "Payroll Entry Submission"
    )

def before_validate(doc, method=None):
    """Fungsi yang dijalankan sebelum validasi"""
    # Debug untuk memeriksa filters yang digunakan
    if hasattr(doc, 'employees') and not doc.employees:
        frappe.msgprint(_("Tidak ada karyawan yang ditemukan. Memeriksa filter..."))
        
        # Cek karyawan aktif di perusahaan
        active_employees = frappe.db.sql("""
            SELECT name, employee_name
            FROM `tabEmployee`
            WHERE status = 'Active' AND company = %s
        """, (doc.company), as_dict=True)
        
        if not active_employees:
            frappe.msgprint(_("Tidak ada karyawan aktif di perusahaan {0}").format(doc.company))
        else:
            # Cek salary structure assignment
            employees_with_structure = []
            for emp in active_employees:
                has_structure = frappe.db.exists("Salary Structure Assignment", {
                    "employee": emp.name,
                    "docstatus": 1
                })
                
                if has_structure:
                    employees_with_structure.append(emp)
            
            if not employees_with_structure:
                frappe.msgprint(_("Karyawan aktif tidak memiliki Salary Structure Assignment"))
            else:
                # Cek karyawan dengan slip gaji yang sudah ada
                for emp in employees_with_structure:
                    existing_slip = frappe.db.exists("Salary Slip", {
                        "employee": emp.name,
                        "start_date": doc.start_date,
                        "end_date": doc.end_date,
                        "docstatus": ["!=", 2]  # Not cancelled
                    })
                    
                    if existing_slip:
                        frappe.msgprint(_(
                            "Karyawan {0} sudah memiliki slip gaji untuk periode ini: {1}"
                        ).format(emp.employee_name, existing_slip))