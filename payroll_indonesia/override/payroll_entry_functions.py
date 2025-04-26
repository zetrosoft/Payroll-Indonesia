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