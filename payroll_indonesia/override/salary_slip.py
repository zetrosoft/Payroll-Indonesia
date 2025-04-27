# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 11:01:44 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate
from erpnext.payroll.doctype.salary_slip.salary_slip import SalarySlip
from erpnext.payroll.doctype.salary_slip.salary_slip import make_salary_slip_from_timesheet as original_make_slip

# Import fungsi dari file modul pendukung dengan penanganan error yang lebih baik
try:
    from payroll_indonesia.override.salary_slip.base import get_formatted_currency, get_component_amount, update_component_amount
    from payroll_indonesia.override.salary_slip.tax_calculator import calculate_tax_components
    from payroll_indonesia.override.salary_slip.bpjs_calculator import calculate_bpjs_components
    from payroll_indonesia.override.salary_slip.ter_calculator import calculate_monthly_pph_with_ter, should_use_ter_method, get_ter_rate
    from payroll_indonesia.override.salary_slip.tax_summary_creator import create_tax_summary
    from payroll_indonesia.override.salary_slip.bpjs_summary_creator import create_bpjs_payment_summary, create_bpjs_payment_component
    from payroll_indonesia.override.salary_slip.ter_table_creator import create_pph_ter_table
except ImportError:
    frappe.log_error("Error importing Payroll Indonesia modules", "Salary Slip Import Error")
    # Definisi placeholder untuk menghindari error saat module tidak ditemukan
    def get_component_amount(doc, name, type_):
        return 0
    def update_component_amount(doc, name, amount, type_):
        return False
    def calculate_tax_components(doc, employee):
        pass
    def calculate_bpjs_components(doc, employee, base):
        pass
    def create_tax_summary(doc):
        pass
    def create_bpjs_payment_summary(doc):
        return None
    def create_bpjs_payment_component(doc):
        return None
    def create_pph_ter_table(doc):
        return None


class IndonesiaPayrollSalarySlip(SalarySlip):
    """
    Enhanced Salary Slip for Indonesian Payroll
    Extends erpnext.payroll.doctype.salary_slip.salary_slip.SalarySlip
    
    Implementasi ini menambahkan fitur-fitur khusus untuk payroll Indonesia:
    - Perhitungan BPJS (Kesehatan, JHT, JP, JKK, JKM)
    - Perhitungan PPh 21 dengan metode gross atau gross-up
    - Dukungan untuk metode TER (Tax Equal Rate)
    - Integrasi dengan dokumen BPJS Payment Summary
    - Integrasi dengan dokumen Employee Tax Summary
    """
    def validate(self):
        """Validate salary slip dan hitung komponen Indonesia"""
        try:
            # Panggil validasi kelas induk terlebih dahulu
            super(IndonesiaPayrollSalarySlip, self).validate()
            
            # Inisialisasi field tambahan jika belum ada
            self.initialize_payroll_fields()
            
            # Dapatkan dokumen karyawan dengan validasi
            employee = self.get_employee_doc()
            
            # Hitung gaji pokok untuk perhitungan BPJS
            gaji_pokok = self.get_gaji_pokok()
            
            # Hitung komponen BPJS
            calculate_bpjs_components(self, employee, gaji_pokok)
            
            # Hitung komponen Pajak
            calculate_tax_components(self, employee)
            
            # Generate data NPWP dan KTP
            self.generate_tax_id_data(employee)

            # Tambahkan catatan ke payroll_note
            self.add_payroll_note("Validasi berhasil: Komponen BPJS dan Pajak dihitung.")
            
        except Exception as e:
            frappe.log_error(
                f"Error dalam validasi Salary Slip untuk {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Slip Validation Error"
            )
            frappe.throw(_("Error dalam validasi Salary Slip: {0}").format(str(e)))
    
    def on_submit(self):
        """Buat dokumen terkait saat submit"""
        try:
            # Panggil method on_submit dari kelas induk terlebih dahulu
            super(IndonesiaPayrollSalarySlip, self).on_submit()
            
            # Buat dokumen tax summary
            create_tax_summary(self)
            
            # Buat dokumen BPJS jika ada komponen BPJS
            bpjs_components = [
                self.get_component_amount("BPJS JHT Employee", "deductions"),
                self.get_component_amount("BPJS JP Employee", "deductions"),
                self.get_component_amount("BPJS Kesehatan Employee", "deductions")
            ]
            
            if any(component > 0 for component in bpjs_components):
                bpjs_summary = create_bpjs_payment_summary(self)
                # Buat BPJS Payment Component jika setting diaktifkan
                try:
                    bpjs_settings = frappe.get_single("BPJS Settings")
                    if hasattr(bpjs_settings, 'auto_create_component') and bpjs_settings.auto_create_component:
                        create_bpjs_payment_component(self)
                except Exception as e:
                    self.add_payroll_note(f"Warning: Gagal membuat BPJS Payment Component: {str(e)}")
                
            # Buat PPh TER Table jika menggunakan metode TER
            if getattr(self, 'is_using_ter', 0) == 1:
                create_pph_ter_table(self)
                
            self.add_payroll_note("Submit berhasil: Dokumen terkait telah dibuat.")
            
        except Exception as e:
            frappe.log_error(
                f"Error dalam on_submit Salary Slip untuk {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Slip Submit Error"
            )
            frappe.msgprint(_("Warning: Error saat membuat dokumen terkait: {0}").format(str(e)))
    
    def on_cancel(self):
        """Tangani pembatalan dokumen"""
        try:
            # Panggil method on_cancel dari kelas induk terlebih dahulu
            super(IndonesiaPayrollSalarySlip, self).on_cancel()
            
            # Update dokumen terkait
            self.update_related_documents_on_cancel()
            
        except Exception as e:
            frappe.log_error(
                f"Error dalam on_cancel Salary Slip untuk {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Slip Cancel Error"
            )
            frappe.msgprint(_("Warning: Error saat mengupdate dokumen terkait pada pembatalan: {0}").format(str(e)))
    
    def update_related_documents_on_cancel(self):
        """Update dokumen terkait saat membatalkan salary slip"""
        month = getdate(self.end_date).month
        year = getdate(self.end_date).year
        
        # Hapus dari BPJS Payment Summary
        self.update_bpjs_summary_on_cancel(month, year)
        
        # Hapus dari PPh TER Table
        self.update_ter_table_on_cancel(month, year)
        
        # Update Employee Tax Summary
        self.update_tax_summary_on_cancel(year)
        
        # Hapus BPJS Payment Components terkait dengan slip gaji ini
        self.delete_related_bpjs_components()
        
        self.add_payroll_note("Cancel berhasil: Dokumen terkait telah diperbarui.")
    
    def delete_related_bpjs_components(self):
        """Hapus BPJS Payment Components yang dibuat untuk slip gaji ini"""
        try:
            # Temukan BPJS Payment Components terkait
            components = frappe.get_all(
                "BPJS Payment Component",
                filters={"salary_slip": self.name, "docstatus": 0},  # Draft only
                pluck="name"
            )
            
            # Hapus setiap komponen
            for component in components:
                try:
                    frappe.delete_doc("BPJS Payment Component", component, force=False)
                    frappe.msgprint(_("Berhasil menghapus BPJS Payment Component {0}").format(component))
                except Exception as e:
                    frappe.log_error(
                        f"Error menghapus BPJS Payment Component {component}: {str(e)}",
                        "BPJS Component Delete Error"
                    )
                    frappe.msgprint(_(
                        "Tidak dapat menghapus BPJS Payment Component {0}: {1}"
                    ).format(component, str(e)))
        except Exception as e:
            frappe.log_error(
                f"Error mencari BPJS Payment Components untuk {self.name}: {str(e)}",
                "BPJS Component Query Error"
            )
            frappe.msgprint(_("Error mencari BPJS Payment Components terkait: {0}").format(str(e)))
    
    def update_bpjs_summary_on_cancel(self, month, year):
        """Update BPJS Payment Summary saat salary slip dibatalkan"""
        try:
            # Cari BPJS Payment Summary untuk periode ini
            bpjs_summary = frappe.db.get_value(
                "BPJS Payment Summary",
                {"company": self.company, "year": year, "month": month, "docstatus": ["!=", 2]},
                "name"
            )
            
            if not bpjs_summary:
                return
                
            # Dapatkan dokumen
            bpjs_doc = frappe.get_doc("BPJS Payment Summary", bpjs_summary)
            
            # Cek apakah masih bisa dimodifikasi
            if bpjs_doc.docstatus > 0:
                frappe.msgprint(_(
                    "BPJS Payment Summary {0} sudah disubmit dan tidak dapat diperbarui."
                ).format(bpjs_summary))
                return
                
            # Temukan dan hapus employee kita
            if hasattr(bpjs_doc, 'employee_details'):
                to_remove = []
                for i, d in enumerate(bpjs_doc.employee_details):
                    if hasattr(d, 'salary_slip') and d.salary_slip == self.name:
                        to_remove.append(d)
                        
                for d in to_remove:
                    bpjs_doc.employee_details.remove(d)
                    
                # Simpan jika ada entri yang dihapus
                if len(to_remove) > 0:
                    bpjs_doc.save()
                    frappe.msgprint(_("Berhasil menghapus data dari BPJS Payment Summary {0}").format(bpjs_summary))
                    
        except Exception as e:
            frappe.log_error(
                f"Error memperbarui BPJS Summary saat cancel: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Summary Cancel Error"
            )
            frappe.msgprint(_("Error memperbarui BPJS Payment Summary: {0}").format(str(e)))
    
    def update_ter_table_on_cancel(self, month, year):
        """Update PPh TER Table saat salary slip dibatalkan"""
        try:
            # Hanya lanjutkan jika menggunakan TER
            if not getattr(self, 'is_using_ter', 0):
                return
                
            # Cari TER Table untuk periode ini
            ter_table = frappe.db.get_value(
                "PPh TER Table",
                {"company": self.company, "year": year, "month": month, "docstatus": ["!=", 2]},
                "name"
            )
            
            if not ter_table:
                return
                
            # Dapatkan dokumen
            ter_doc = frappe.get_doc("PPh TER Table", ter_table)
            
            # Cek apakah masih bisa dimodifikasi
            if ter_doc.docstatus > 0:
                frappe.msgprint(_(
                    "PPh TER Table {0} sudah disubmit dan tidak dapat diperbarui."
                ).format(ter_table))
                return
                
            # Temukan dan hapus employee kita
            if hasattr(ter_doc, 'details'):
                to_remove = []
                for i, d in enumerate(ter_doc.details):
                    if d.employee == self.employee:
                        to_remove.append(d)
                        
                for d in to_remove:
                    ter_doc.details.remove(d)
                    
                # Simpan jika ada entri yang dihapus
                if len(to_remove) > 0:
                    ter_doc.save()
                    frappe.msgprint(_("Berhasil menghapus data dari PPh TER Table {0}").format(ter_table))
                    
        except Exception as e:
            frappe.log_error(
                f"Error memperbarui TER Table saat cancel: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "TER Table Cancel Error"
            )
            frappe.msgprint(_("Error memperbarui PPh TER Table: {0}").format(str(e)))
    
    def update_tax_summary_on_cancel(self, year):
        """Update Employee Tax Summary saat salary slip dibatalkan"""
        try:
            # Cari Tax Summary untuk karyawan dan tahun ini
            tax_summary = frappe.db.get_value(
                "Employee Tax Summary",
                {"employee": self.employee, "year": year},
                "name"
            )
            
            if not tax_summary:
                return
                
            # Dapatkan dokumen
            tax_doc = frappe.get_doc("Employee Tax Summary", tax_summary)
                
            # Temukan dan update bulan kita
            if hasattr(tax_doc, 'monthly_details'):
                month = getdate(self.end_date).month
                changed = False
                
                for d in tax_doc.monthly_details:
                    if hasattr(d, 'month') and d.month == month and hasattr(d, 'salary_slip') and d.salary_slip == self.name:
                        # Set nilai bulan ini menjadi 0
                        d.gross_pay = 0
                        d.bpjs_deductions = 0
                        d.tax_amount = 0
                        d.salary_slip = None
                        changed = True
                        
                # Hitung ulang YTD jika ada perubahan
                if changed:
                    # Hitung ulang YTD
                    total_tax = 0
                    if tax_doc.monthly_details:
                        for m in tax_doc.monthly_details:
                            if hasattr(m, 'tax_amount'):
                                total_tax += flt(m.tax_amount)
                                
                    tax_doc.ytd_tax = total_tax
                    tax_doc.save()
                    frappe.msgprint(_("Berhasil memperbarui Employee Tax Summary {0}").format(tax_summary))
                    
        except Exception as e:
            frappe.log_error(
                f"Error memperbarui Tax Summary saat cancel: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Tax Summary Cancel Error"
            )
            frappe.msgprint(_("Error memperbarui Employee Tax Summary: {0}").format(str(e)))
    
    # Helper methods
    def initialize_payroll_fields(self):
        """Inisialisasi field payroll tambahan"""
        if not hasattr(self, 'biaya_jabatan') or self.biaya_jabatan is None:
            self.biaya_jabatan = 0
            
        if not hasattr(self, 'netto') or self.netto is None:
            self.netto = 0
            
        if not hasattr(self, 'total_bpjs') or self.total_bpjs is None:
            self.total_bpjs = 0
            
        if not hasattr(self, 'is_using_ter') or self.is_using_ter is None:
            self.is_using_ter = 0
            
        if not hasattr(self, 'ter_rate') or self.ter_rate is None:
            self.ter_rate = 0
            
        if not hasattr(self, 'koreksi_pph21') or self.koreksi_pph21 is None:
            self.koreksi_pph21 = 0
            
        if not hasattr(self, 'payroll_note') or self.payroll_note is None:
            self.payroll_note = ""
            
        if not hasattr(self, 'npwp') or self.npwp is None:
            self.npwp = ""
            
        if not hasattr(self, 'ktp') or self.ktp is None:
            self.ktp = ""
    
    def get_employee_doc(self):
        """Dapatkan dokumen karyawan dengan validasi"""
        if not self.employee:
            frappe.throw(_("Employee harus diisi untuk salary slip"))
            
        try:
            employee_doc = frappe.get_doc("Employee", self.employee)
            return employee_doc
        except Exception as e:
            frappe.throw(_("Error saat mengambil data karyawan {0}: {1}").format(self.employee, str(e)))
    
    def get_gaji_pokok(self):
        """Dapatkan gaji pokok dari komponen earnings"""
        gaji_pokok = 0
        
        # Cari komponen Basic
        for earning in self.earnings:
            if earning.salary_component == "Basic":
                gaji_pokok = flt(earning.amount)
                break
                
        # Jika Basic tidak ditemukan, gunakan komponen pertama
        if gaji_pokok == 0 and len(self.earnings) > 0:
            gaji_pokok = flt(self.earnings[0].amount)
            
        return gaji_pokok
    
    def generate_tax_id_data(self, employee):
        """Generate informasi NPWP dan KTP dari data karyawan"""
        try:
            # Dapatkan NPWP dari karyawan
            if hasattr(employee, 'npwp'):
                self.npwp = employee.npwp
                
            # Dapatkan KTP dari karyawan
            if hasattr(employee, 'ktp'):
                self.ktp = employee.ktp
                
        except Exception as e:
            frappe.log_error(
                f"Error menghasilkan data tax ID untuk {self.name}: {str(e)}",
                "Tax ID Data Error"
            )
            frappe.msgprint(_("Error menghasilkan data tax ID: {0}").format(str(e)))
    
    def add_payroll_note(self, note):
        """Tambahkan catatan ke payroll_note"""
        if not hasattr(self, 'payroll_note'):
            self.payroll_note = ""
            
        # Tambahkan timestamp ke catatan
        from frappe.utils import now_datetime
        timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
        
        # Tambahkan catatan baru
        self.payroll_note += f"\n[{timestamp}] {note}"
    
    def get_component_amount(self, component_name, component_type):
        """Wrapper untuk fungsi get_component_amount"""
        return get_component_amount(self, component_name, component_type)
        
    def update_component_amount(self, component_name, amount, component_type):
        """Wrapper untuk fungsi update_component_amount"""
        return update_component_amount(self, component_name, amount, component_type)


# Override kelas SalarySlip standar dengan versi yang telah ditingkatkan
frappe.model.document.get_controller("Salary Slip")._controller = IndonesiaPayrollSalarySlip

@frappe.whitelist()
def make_salary_slip_from_timesheet(timesheet):
    """
    Override function untuk make_salary_slip_from_timesheet
    Memanggil versi asli tetapi dengan penyesuaian untuk Indonesia
    """
    try:
        # Dapatkan salary slip dari fungsi asli
        salary_slip = original_make_slip(timesheet)
        
        # Cek apakah perusahaan di Indonesia
        if not salary_slip:
            return None
            
        company = frappe.db.get_value("Timesheet", timesheet, "company")
        if not company:
            return salary_slip
            
        country = frappe.db.get_value("Company", company, "country")
        if country != "Indonesia":
            return salary_slip
        
        # Jika perusahaan di Indonesia, lakukan kustomisasi tambahan
        
        # Dapatkan karyawan
        employee = salary_slip.employee
        employee_doc = frappe.get_doc("Employee", employee)
        
        # Set field tambahan jika tersedia
        if hasattr(salary_slip, 'npwp') and hasattr(employee_doc, 'npwp'):
            salary_slip.npwp = employee_doc.npwp
            
        if hasattr(salary_slip, 'ktp') and hasattr(employee_doc, 'ktp'):
            salary_slip.ktp = employee_doc.ktp
        
        # Tambahkan catatan payroll
        if hasattr(salary_slip, 'payroll_note'):
            salary_slip.payroll_note = "Dibuat dari Timesheet: " + timesheet
        
        return salary_slip
    except Exception as e:
        frappe.log_error(
            f"Error dalam make_salary_slip_from_timesheet: {str(e)}\nTimesheet: {timesheet}",
            "Timesheet Override Error"
        )
        return original_make_slip(timesheet)