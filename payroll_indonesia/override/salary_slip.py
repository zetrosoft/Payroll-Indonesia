# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 11:01:44 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate, now_datetime
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
from hrms.payroll.doctype.salary_slip.salary_slip import make_salary_slip_from_timesheet as original_make_slip

# Debug function for error tracking
def debug_log(message, module_name="Salary Slip Debug"):
    """Log debug message with timestamp and additional info"""
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    frappe.log_error(f"[{timestamp}] {message}", module_name)

# Import fungsi dari file modul pendukung dengan penanganan error yang lebih baik
try:
    debug_log("Starting imports from payroll_indonesia modules")
    
    from payroll_indonesia.override.salary_slip.base import get_formatted_currency, get_component_amount, update_component_amount
    from payroll_indonesia.override.salary_slip.tax_calculator import calculate_tax_components
    from payroll_indonesia.override.salary_slip.bpjs_calculator import calculate_bpjs_components
    from payroll_indonesia.override.salary_slip.ter_calculator import calculate_monthly_pph_with_ter, should_use_ter_method, get_ter_rate
    from payroll_indonesia.override.salary_slip.tax_summary_creator import create_tax_summary
    from payroll_indonesia.override.salary_slip.bpjs_summary_creator import create_bpjs_payment_summary, create_bpjs_payment_component
    from payroll_indonesia.override.salary_slip.ter_table_creator import create_pph_ter_table
    
    debug_log("Successfully imported all payroll_indonesia modules")
except ImportError as e:
    debug_log(f"Error importing Payroll Indonesia modules: {str(e)}\nTraceback: {frappe.get_traceback()}", "Module Import Error")
    frappe.log_error("Error importing Payroll Indonesia modules", "Salary Slip Import Error")
    # Definisi placeholder untuk menghindari error saat module tidak ditemukan
    def get_component_amount(doc, name, type_):
        debug_log(f"Using placeholder get_component_amount for {name} in {type_}")
        return 0
    def update_component_amount(doc, name, amount, type_):
        debug_log(f"Using placeholder update_component_amount for {name}: {amount} in {type_}")
        return False
    def calculate_tax_components(doc, employee):
        debug_log(f"Using placeholder calculate_tax_components for employee {employee.name if hasattr(employee, 'name') else 'unknown'}")
        pass
    def calculate_bpjs_components(doc, employee, base):
        debug_log(f"Using placeholder calculate_bpjs_components: employee={employee.name if hasattr(employee, 'name') else 'unknown'}, base={base}")
        pass
    def create_tax_summary(doc):
        debug_log(f"Using placeholder create_tax_summary for {doc.name if hasattr(doc, 'name') else 'unknown doc'}")
        pass
    def create_bpjs_payment_summary(doc):
        debug_log(f"Using placeholder create_bpjs_payment_summary for {doc.name if hasattr(doc, 'name') else 'unknown doc'}")
        return None
    def create_bpjs_payment_component(doc):
        debug_log(f"Using placeholder create_bpjs_payment_component for {doc.name if hasattr(doc, 'name') else 'unknown doc'}")
        return None
    def create_pph_ter_table(doc):
        debug_log(f"Using placeholder create_pph_ter_table for {doc.name if hasattr(doc, 'name') else 'unknown doc'}")
        return None


class IndonesiaPayrollSalarySlip(SalarySlip):
    """
    Enhanced Salary Slip for Indonesian Payroll
    Extends hrms.payroll.doctype.salary_slip.salary_slip.SalarySlip
    
    Implementasi ini menambahkan fitur-fitur khusus untuk payroll Indonesia:
    - Perhitungan BPJS (Kesehatan, JHT, JP, JKK, JKM)
    - Perhitungan PPh 21 dengan metode gross atau gross-up
    - Dukungan untuk metode TER (Tax Equal Rate)
    - Integrasi dengan dokumen BPJS Payment Summary
    - Integrasi dengan dokumen Employee Tax Summary
    """
    def validate(self):
        """Validate salary slip dan hitung komponen Indonesia"""
        debug_log(f"Starting validate for salary slip {self.name}")
        try:
            # Panggil validasi kelas induk terlebih dahulu
            debug_log(f"Calling parent validate for {self.name}")
            super(IndonesiaPayrollSalarySlip, self).validate()
            
            # Inisialisasi field tambahan jika belum ada
            debug_log(f"Initializing payroll fields for {self.name}")
            self.initialize_payroll_fields()
            
            # Dapatkan dokumen karyawan dengan validasi
            debug_log(f"Getting employee doc for {self.employee}")
            employee = self.get_employee_doc()
            
            # Hitung gaji pokok untuk perhitungan BPJS
            debug_log(f"Calculating gaji pokok for {self.name}")
            gaji_pokok = self.get_gaji_pokok()
            debug_log(f"Gaji pokok for {self.name}: {gaji_pokok}")
            
            # Hitung komponen BPJS
            debug_log(f"Calculating BPJS components for {self.name}")
            calculate_bpjs_components(self, employee, gaji_pokok)
            
            # Hitung komponen Pajak
            debug_log(f"Calculating tax components for {self.name}")
            calculate_tax_components(self, employee)
            
            # Generate data NPWP dan KTP
            debug_log(f"Generating tax ID data for {self.name}")
            self.generate_tax_id_data(employee)

            # Tambahkan catatan ke payroll_note
            self.add_payroll_note("Validasi berhasil: Komponen BPJS dan Pajak dihitung.")
            debug_log(f"Validation completed successfully for {self.name}")
            
        except Exception as e:
            debug_log(f"Error in validate for {self.name}: {str(e)}\nTraceback: {frappe.get_traceback()}")
            frappe.log_error(
                f"Error dalam validasi Salary Slip untuk {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Slip Validation Error"
            )
            frappe.throw(_("Error dalam validasi Salary Slip: {0}").format(str(e)))
    
    def on_submit(self):
        """Buat dokumen terkait saat submit"""
        debug_log(f"Starting on_submit for salary slip {self.name}")
        try:
            # Panggil method on_submit dari kelas induk terlebih dahulu
            debug_log(f"Calling parent on_submit for {self.name}")
            super(IndonesiaPayrollSalarySlip, self).on_submit()
            
            # Buat dokumen tax summary
            debug_log(f"Creating tax summary for {self.name}")
            create_tax_summary(self)
            
            # Buat dokumen BPJS jika ada komponen BPJS
            debug_log(f"Checking BPJS components for {self.name}")
            bpjs_components = [
                self.get_component_amount("BPJS JHT Employee", "deductions"),
                self.get_component_amount("BPJS JP Employee", "deductions"),
                self.get_component_amount("BPJS Kesehatan Employee", "deductions")
            ]
            
            debug_log(f"BPJS components for {self.name}: {bpjs_components}")
            
            if any(component > 0 for component in bpjs_components):
                debug_log(f"Creating BPJS payment summary for {self.name}")
                bpjs_summary = create_bpjs_payment_summary(self)
                debug_log(f"BPJS payment summary created: {bpjs_summary}")
                
                # Buat BPJS Payment Component jika setting diaktifkan
                try:
                    debug_log(f"Checking BPJS settings for auto_create_component")
                    bpjs_settings = frappe.get_single("BPJS Settings")
                    if hasattr(bpjs_settings, 'auto_create_component') and bpjs_settings.auto_create_component:
                        debug_log(f"Creating BPJS payment component for {self.name}")
                        component = create_bpjs_payment_component(self)
                        debug_log(f"BPJS payment component created: {component}")
                except Exception as e:
                    debug_log(f"Error creating BPJS payment component: {str(e)}\nTraceback: {frappe.get_traceback()}")
                    self.add_payroll_note(f"Warning: Gagal membuat BPJS Payment Component: {str(e)}")
                
            # Buat PPh TER Table jika menggunakan metode TER
            if getattr(self, 'is_using_ter', 0) == 1:
                debug_log(f"Creating PPh TER table for {self.name} (is_using_ter=1)")
                ter_table = create_pph_ter_table(self)
                debug_log(f"PPh TER table created: {ter_table}")
            else:
                debug_log(f"Skipping PPh TER table creation for {self.name} (is_using_ter=0)")
                
            self.add_payroll_note("Submit berhasil: Dokumen terkait telah dibuat.")
            debug_log(f"on_submit completed successfully for {self.name}")
            
        except Exception as e:
            debug_log(f"Error in on_submit for {self.name}: {str(e)}\nTraceback: {frappe.get_traceback()}")
            frappe.log_error(
                f"Error dalam on_submit Salary Slip untuk {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Slip Submit Error"
            )
            frappe.msgprint(_("Warning: Error saat membuat dokumen terkait: {0}").format(str(e)))
    
    def on_cancel(self):
        """Tangani pembatalan dokumen"""
        debug_log(f"Starting on_cancel for salary slip {self.name}")
        try:
            # Panggil method on_cancel dari kelas induk terlebih dahulu
            debug_log(f"Calling parent on_cancel for {self.name}")
            super(IndonesiaPayrollSalarySlip, self).on_cancel()
            
            # Update dokumen terkait
            debug_log(f"Updating related documents on cancel for {self.name}")
            self.update_related_documents_on_cancel()
            
            debug_log(f"on_cancel completed successfully for {self.name}")
            
        except Exception as e:
            debug_log(f"Error in on_cancel for {self.name}: {str(e)}\nTraceback: {frappe.get_traceback()}")
            frappe.log_error(
                f"Error dalam on_cancel Salary Slip untuk {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Slip Cancel Error"
            )
            frappe.msgprint(_("Warning: Error saat mengupdate dokumen terkait pada pembatalan: {0}").format(str(e)))
    
    def update_related_documents_on_cancel(self):
        """Update dokumen terkait saat membatalkan salary slip"""
        debug_log(f"Starting update_related_documents_on_cancel for {self.name}")
        month = getdate(self.end_date).month
        year = getdate(self.end_date).year
        
        # Hapus dari BPJS Payment Summary
        debug_log(f"Updating BPJS summary on cancel for {self.name} (month={month}, year={year})")
        self.update_bpjs_summary_on_cancel(month, year)
        
        # Hapus dari PPh TER Table
        debug_log(f"Updating TER table on cancel for {self.name} (month={month}, year={year})")
        self.update_ter_table_on_cancel(month, year)
        
        # Update Employee Tax Summary
        debug_log(f"Updating tax summary on cancel for {self.name} (year={year})")
        self.update_tax_summary_on_cancel(year)
        
        # Hapus BPJS Payment Components terkait dengan slip gaji ini
        debug_log(f"Deleting related BPJS components for {self.name}")
        self.delete_related_bpjs_components()
        
        self.add_payroll_note("Cancel berhasil: Dokumen terkait telah diperbarui.")
        debug_log(f"update_related_documents_on_cancel completed for {self.name}")
    
    def delete_related_bpjs_components(self):
        """Hapus BPJS Payment Components yang dibuat untuk slip gaji ini"""
        debug_log(f"Starting delete_related_bpjs_components for {self.name}")
        try:
            # Temukan BPJS Payment Components terkait
            debug_log(f"Searching for BPJS Payment Components related to {self.name}")
            components = frappe.get_all(
                "BPJS Payment Component",
                filters={"salary_slip": self.name, "docstatus": 0},  # Draft only
                pluck="name"
            )
            
            debug_log(f"Found {len(components)} BPJS Payment Components for {self.name}: {components}")
            
            # Hapus setiap komponen
            for component in components:
                try:
                    debug_log(f"Deleting BPJS Payment Component {component}")
                    frappe.delete_doc("BPJS Payment Component", component, force=False)
                    frappe.msgprint(_("Berhasil menghapus BPJS Payment Component {0}").format(component))
                    debug_log(f"Successfully deleted BPJS Payment Component {component}")
                except Exception as e:
                    debug_log(f"Error deleting BPJS Payment Component {component}: {str(e)}\nTraceback: {frappe.get_traceback()}")
                    frappe.log_error(
                        f"Error menghapus BPJS Payment Component {component}: {str(e)}",
                        "BPJS Component Delete Error"
                    )
                    frappe.msgprint(_(
                        "Tidak dapat menghapus BPJS Payment Component {0}: {1}"
                    ).format(component, str(e)))
        except Exception as e:
            debug_log(f"Error searching for BPJS Payment Components: {str(e)}\nTraceback: {frappe.get_traceback()}")
            frappe.log_error(
                f"Error mencari BPJS Payment Components untuk {self.name}: {str(e)}",
                "BPJS Component Query Error"
            )
            frappe.msgprint(_("Error mencari BPJS Payment Components terkait: {0}").format(str(e)))
    
    def update_bpjs_summary_on_cancel(self, month, year):
        """Update BPJS Payment Summary saat salary slip dibatalkan"""
        debug_log(f"Starting update_bpjs_summary_on_cancel for {self.name} (month={month}, year={year})")
        try:
            # Cari BPJS Payment Summary untuk periode ini
            debug_log(f"Searching for BPJS Payment Summary for company={self.company}, month={month}, year={year}")
            bpjs_summary = frappe.db.get_value(
                "BPJS Payment Summary",
                {"company": self.company, "year": year, "month": month, "docstatus": ["!=", 2]},
                "name"
            )
            
            debug_log(f"BPJS Payment Summary found: {bpjs_summary}")
            
            if not bpjs_summary:
                debug_log(f"No BPJS Payment Summary found, skipping update")
                return
                
            # Dapatkan dokumen
            debug_log(f"Getting BPJS Payment Summary document {bpjs_summary}")
            bpjs_doc = frappe.get_doc("BPJS Payment Summary", bpjs_summary)
            
            # Cek apakah masih bisa dimodifikasi
            if bpjs_doc.docstatus > 0:
                debug_log(f"BPJS Payment Summary {bpjs_summary} already submitted, cannot update")
                frappe.msgprint(_(
                    "BPJS Payment Summary {0} sudah disubmit dan tidak dapat diperbarui."
                ).format(bpjs_summary))
                return
                
            # Temukan dan hapus employee kita
            if hasattr(bpjs_doc, 'employee_details'):
                debug_log(f"Checking employee_details in BPJS Payment Summary {bpjs_summary}")
                to_remove = []
                for i, d in enumerate(bpjs_doc.employee_details):
                    if hasattr(d, 'salary_slip') and d.salary_slip == self.name:
                        debug_log(f"Found entry to remove: employee_details[{i}] with salary_slip={self.name}")
                        to_remove.append(d)
                        
                debug_log(f"Found {len(to_remove)} entries to remove from BPJS Payment Summary {bpjs_summary}")
                
                for d in to_remove:
                    bpjs_doc.employee_details.remove(d)
                    
                # Simpan jika ada entri yang dihapus
                if len(to_remove) > 0:
                    debug_log(f"Saving BPJS Payment Summary {bpjs_summary} after removing entries")
                    bpjs_doc.save()
                    frappe.msgprint(_("Berhasil menghapus data dari BPJS Payment Summary {0}").format(bpjs_summary))
                    debug_log(f"Successfully updated BPJS Payment Summary {bpjs_summary}")
                else:
                    debug_log(f"No entries removed from BPJS Payment Summary {bpjs_summary}")
            else:
                debug_log(f"BPJS Payment Summary {bpjs_summary} does not have employee_details field")
                    
        except Exception as e:
            debug_log(f"Error updating BPJS Summary on cancel: {str(e)}\nTraceback: {frappe.get_traceback()}")
            frappe.log_error(
                f"Error memperbarui BPJS Summary saat cancel: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Summary Cancel Error"
            )
            frappe.msgprint(_("Error memperbarui BPJS Payment Summary: {0}").format(str(e)))
    
    def update_ter_table_on_cancel(self, month, year):
        """Update PPh TER Table saat salary slip dibatalkan"""
        debug_log(f"Starting update_ter_table_on_cancel for {self.name} (month={month}, year={year})")
        try:
            # Hanya lanjutkan jika menggunakan TER
            is_using_ter = getattr(self, 'is_using_ter', 0)
            debug_log(f"Checking if using TER: is_using_ter={is_using_ter}")
            
            if not is_using_ter:
                debug_log(f"Not using TER, skipping update_ter_table_on_cancel")
                return
                
            # Cari TER Table untuk periode ini
            debug_log(f"Searching for PPh TER Table for company={self.company}, month={month}, year={year}")
            ter_table = frappe.db.get_value(
                "PPh TER Table",
                {"company": self.company, "year": year, "month": month, "docstatus": ["!=", 2]},
                "name"
            )
            
            debug_log(f"PPh TER Table found: {ter_table}")
            
            if not ter_table:
                debug_log(f"No PPh TER Table found, skipping update")
                return
                
            # Dapatkan dokumen
            debug_log(f"Getting PPh TER Table document {ter_table}")
            ter_doc = frappe.get_doc("PPh TER Table", ter_table)
            
            # Cek apakah masih bisa dimodifikasi
            if ter_doc.docstatus > 0:
                debug_log(f"PPh TER Table {ter_table} already submitted, cannot update")
                frappe.msgprint(_(
                    "PPh TER Table {0} sudah disubmit dan tidak dapat diperbarui."
                ).format(ter_table))
                return
                
            # Temukan dan hapus employee kita
            if hasattr(ter_doc, 'details'):
                debug_log(f"Checking details in PPh TER Table {ter_table}")
                to_remove = []
                for i, d in enumerate(ter_doc.details):
                    if d.employee == self.employee:
                        debug_log(f"Found entry to remove: details[{i}] with employee={self.employee}")
                        to_remove.append(d)
                        
                debug_log(f"Found {len(to_remove)} entries to remove from PPh TER Table {ter_table}")
                
                for d in to_remove:
                    ter_doc.details.remove(d)
                    
                # Simpan jika ada entri yang dihapus
                if len(to_remove) > 0:
                    debug_log(f"Saving PPh TER Table {ter_table} after removing entries")
                    ter_doc.save()
                    frappe.msgprint(_("Berhasil menghapus data dari PPh TER Table {0}").format(ter_table))
                    debug_log(f"Successfully updated PPh TER Table {ter_table}")
                else:
                    debug_log(f"No entries removed from PPh TER Table {ter_table}")
            else:
                debug_log(f"PPh TER Table {ter_table} does not have details field")
                    
        except Exception as e:
            debug_log(f"Error updating TER Table on cancel: {str(e)}\nTraceback: {frappe.get_traceback()}")
            frappe.log_error(
                f"Error memperbarui TER Table saat cancel: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "TER Table Cancel Error"
            )
            frappe.msgprint(_("Error memperbarui PPh TER Table: {0}").format(str(e)))
    
    def update_tax_summary_on_cancel(self, year):
        """Update Employee Tax Summary saat salary slip dibatalkan"""
        debug_log(f"Starting update_tax_summary_on_cancel for {self.name} (year={year})")
        try:
            # Cari Tax Summary untuk karyawan dan tahun ini
            debug_log(f"Searching for Employee Tax Summary for employee={self.employee}, year={year}")
            tax_summary = frappe.db.get_value(
                "Employee Tax Summary",
                {"employee": self.employee, "year": year},
                "name"
            )
            
            debug_log(f"Employee Tax Summary found: {tax_summary}")
            
            if not tax_summary:
                debug_log(f"No Employee Tax Summary found, skipping update")
                return
                
            # Dapatkan dokumen
            debug_log(f"Getting Employee Tax Summary document {tax_summary}")
            tax_doc = frappe.get_doc("Employee Tax Summary", tax_summary)
                
            # Temukan dan update bulan kita
            if hasattr(tax_doc, 'monthly_details'):
                debug_log(f"Checking monthly_details in Employee Tax Summary {tax_summary}")
                month = getdate(self.end_date).month
                changed = False
                
                for i, d in enumerate(tax_doc.monthly_details):
                    if hasattr(d, 'month') and d.month == month and hasattr(d, 'salary_slip') and d.salary_slip == self.name:
                        debug_log(f"Found entry to update: monthly_details[{i}] with month={month}, salary_slip={self.name}")
                        # Set nilai bulan ini menjadi 0
                        d.gross_pay = 0
                        d.bpjs_deductions = 0
                        d.tax_amount = 0
                        d.salary_slip = None
                        changed = True
                        
                debug_log(f"Changed entries in Employee Tax Summary: {changed}")
                
                # Hitung ulang YTD jika ada perubahan
                if changed:
                    debug_log(f"Recalculating YTD tax for Employee Tax Summary {tax_summary}")
                    # Hitung ulang YTD
                    total_tax = 0
                    if tax_doc.monthly_details:
                        for m in tax_doc.monthly_details:
                            if hasattr(m, 'tax_amount'):
                                total_tax += flt(m.tax_amount)
                                
                    tax_doc.ytd_tax = total_tax
                    
                    debug_log(f"Saving Employee Tax Summary {tax_summary} with new YTD tax: {total_tax}")
                    tax_doc.save()
                    frappe.msgprint(_("Berhasil memperbarui Employee Tax Summary {0}").format(tax_summary))
                    debug_log(f"Successfully updated Employee Tax Summary {tax_summary}")
                else:
                    debug_log(f"No entries updated in Employee Tax Summary {tax_summary}")
            else:
                debug_log(f"Employee Tax Summary {tax_summary} does not have monthly_details field")
                    
        except Exception as e:
            debug_log(f"Error updating Tax Summary on cancel: {str(e)}\nTraceback: {frappe.get_traceback()}")
            frappe.log_error(
                f"Error memperbarui Tax Summary saat cancel: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Tax Summary Cancel Error"
            )
            frappe.msgprint(_("Error memperbarui Employee Tax Summary: {0}").format(str(e)))
    
    # Helper methods
    def initialize_payroll_fields(self):
        """Inisialisasi field payroll tambahan"""
        debug_log(f"Initializing payroll fields for {self.name}")
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
            
        debug_log(f"Payroll fields initialized for {self.name}")
    
    def get_employee_doc(self):
        """Dapatkan dokumen karyawan dengan validasi"""
        debug_log(f"Getting employee document for {self.employee}")
        if not self.employee:
            debug_log("Employee not specified for salary slip")
            frappe.throw(_("Employee harus diisi untuk salary slip"))
            
        try:
            debug_log(f"Retrieving employee document for {self.employee}")
            employee_doc = frappe.get_doc("Employee", self.employee)
            debug_log(f"Successfully retrieved employee document for {self.employee}")
            return employee_doc
        except Exception as e:
            debug_log(f"Error retrieving employee document for {self.employee}: {str(e)}\nTraceback: {frappe.get_traceback()}")
            frappe.throw(_("Error saat mengambil data karyawan {0}: {1}").format(self.employee, str(e)))
    
    def get_gaji_pokok(self):
        """Dapatkan gaji pokok dari komponen earnings"""
        debug_log(f"Getting gaji pokok for {self.name}")
        gaji_pokok = 0
        
        # Cari komponen Basic
        debug_log("Searching for Basic component")
        for earning in self.earnings:
            if earning.salary_component == "Basic":
                gaji_pokok = flt(earning.amount)
                debug_log(f"Found Basic component: {gaji_pokok}")
                break
                
        # Jika Basic tidak ditemukan, gunakan komponen pertama
        if gaji_pokok == 0 and len(self.earnings) > 0:
            gaji_pokok = flt(self.earnings[0].amount)
            debug_log(f"Basic not found, using first component: {gaji_pokok}")
            
        debug_log(f"Final gaji pokok for {self.name}: {gaji_pokok}")
        return gaji_pokok
    
    def generate_tax_id_data(self, employee):
        """Generate informasi NPWP dan KTP dari data karyawan"""
        debug_log(f"Generating tax ID data for {self.name}")
        try:
            # Dapatkan NPWP dari karyawan
            if hasattr(employee, 'npwp'):
                debug_log(f"Setting NPWP to {employee.npwp}")
                self.npwp = employee.npwp
                
            # Dapatkan KTP dari karyawan
            if hasattr(employee, 'ktp'):
                debug_log(f"Setting KTP to {employee.ktp}")
                self.ktp = employee.ktp
                
            debug_log(f"Tax ID data generated for {self.name}")
            
        except Exception as e:
            debug_log(f"Error generating tax ID data for {self.name}: {str(e)}\nTraceback: {frappe.get_traceback()}")
            frappe.log_error(
                f"Error menghasilkan data tax ID untuk {self.name}: {str(e)}",
                "Tax ID Data Error"
            )
            frappe.msgprint(_("Error menghasilkan data tax ID: {0}").format(str(e)))
    
    def add_payroll_note(self, note):
        """Tambahkan catatan ke payroll_note"""
        debug_log(f"Adding payroll note to {self.name}: {note}")
        if not hasattr(self, 'payroll_note'):
            self.payroll_note = ""
            
        # Tambahkan timestamp ke catatan
        timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
        
        # Tambahkan catatan baru
        self.payroll_note += f"\n[{timestamp}] {note}"
        debug_log(f"Payroll note added to {self.name}")
    
    def get_component_amount(self, component_name, component_type):
        """Wrapper untuk fungsi get_component_amount"""
        debug_log(f"Getting component amount for {component_name} in {component_type}")
        amount = get_component_amount(self, component_name, component_type)
        debug_log(f"Component {component_name} amount: {amount}")
        return amount
        
    def update_component_amount(self, component_name, amount, component_type):
        """Wrapper untuk fungsi update_component_amount"""
        debug_log(f"Updating component {component_name} to {amount} in {component_type}")
        result = update_component_amount(self, component_name, amount, component_type)
        debug_log(f"Component {component_name} update result: {result}")
        return result


# Override kelas SalarySlip standar dengan versi yang telah ditingkatkan
try:
    debug_log("Attempting to override SalarySlip controller")
    frappe.model.document.get_controller("Salary Slip")._controller = IndonesiaPayrollSalarySlip
    debug_log("Successfully overrode SalarySlip controller")
except Exception as e:
    debug_log(f"Error overriding SalarySlip controller: {str(e)}\nTraceback: {frappe.get_traceback()}")
    frappe.log_error(
        f"Error overriding SalarySlip controller: {str(e)}\n\n"
        f"Traceback: {frappe.get_traceback()}",
        "Controller Override Error"
    )

@frappe.whitelist()
def make_salary_slip_from_timesheet(timesheet):
    """
    Override function untuk make_salary_slip_from_timesheet
    Memanggil versi asli tetapi dengan penyesuaian untuk Indonesia
    """
    debug_log(f"Starting make_salary_slip_from_timesheet for timesheet {timesheet}")
    try:
        # Dapatkan salary slip dari fungsi asli
        debug_log(f"Calling original make_salary_slip_from_timesheet for {timesheet}")
        salary_slip = original_make_slip(timesheet)
        
        # Cek apakah perusahaan di Indonesia
        if not salary_slip:
            debug_log(f"No salary slip created from timesheet {timesheet}")
            return None
            
        debug_log(f"Getting company for timesheet {timesheet}")
        company = frappe.db.get_value("Timesheet", timesheet, "company")
        if not company:
            debug_log(f"No company found for timesheet {timesheet}, returning original salary slip")
            return salary_slip
            
        debug_log(f"Getting country for company {company}")
        country = frappe.db.get_value("Company", company, "country")
        debug_log(f"Company {company} country: {country}")
        
        if country != "Indonesia":
            debug_log(f"Company {company} is not in Indonesia, returning original salary slip")
            return salary_slip
        
        # Jika perusahaan di Indonesia, lakukan kustomisasi tambahan
        debug_log(f"Customizing salary slip for Indonesian company")
        
        # Dapatkan karyawan
        employee = salary_slip.employee
        debug_log(f"Getting employee document for {employee}")
        employee_doc = frappe.get_doc("Employee", employee)
        
        # Set field tambahan jika tersedia
        if hasattr(salary_slip, 'npwp') and hasattr(employee_doc, 'npwp'):
            debug_log(f"Setting NPWP: {employee_doc.npwp}")
            salary_slip.npwp = employee_doc.npwp
            
        if hasattr(salary_slip, 'ktp') and hasattr(employee_doc, 'ktp'):
            debug_log(f"Setting KTP: {employee_doc.ktp}")
            salary_slip.ktp = employee_doc.ktp
        
        # Tambahkan catatan payroll
        if hasattr(salary_slip, 'payroll_note'):
            debug_log(f"Setting payroll note for timesheet {timesheet}")
            salary_slip.payroll_note = "Dibuat dari Timesheet: " + timesheet
        
        debug_log(f"Customization completed for salary slip from timesheet {timesheet}")
        return salary_slip
    except Exception as e:
        debug_log(f"Error in make_salary_slip_from_timesheet: {str(e)}\nTraceback: {frappe.get_traceback()}")
        frappe.log_error(
            f"Error dalam make_salary_slip_from_timesheet: {str(e)}\nTimesheet: {timesheet}",
            "Timesheet Override Error"
        )
        # Fallback to original implementation
        debug_log(f"Falling back to original implementation for timesheet {timesheet}")
        return original_make_slip(timesheet)

# Add diagnostic tools for troubleshooting
@frappe.whitelist()
def diagnose_salary_slip_submission(salary_slip_name):
    """
    Diagnostic function to check if all components for salary slip submission are working properly
    """
    debug_log(f"Starting diagnosis for salary slip {salary_slip_name}")
    result = {
        "salary_slip_exists": False,
        "class_override_working": False,
        "custom_fields_exist": {},
        "dependent_doctypes_exist": {},
        "module_imports_working": {},
        "recommendations": []
    }
    
    try:
        # Check if salary slip exists
        if not frappe.db.exists("Salary Slip", salary_slip_name):
            debug_log(f"Salary slip {salary_slip_name} does not exist")
            result["recommendations"].append(f"Salary slip {salary_slip_name} not found. Please provide a valid salary slip name.")
            return result
            
        result["salary_slip_exists"] = True
        debug_log(f"Salary slip {salary_slip_name} exists")
        
        # Get the salary slip
        slip = frappe.get_doc("Salary Slip", salary_slip_name)
        
        # Check if class override is working
        result["class_override_working"] = isinstance(slip, IndonesiaPayrollSalarySlip)
        debug_log(f"Class override working: {result['class_override_working']}")
        
        if not result["class_override_working"]:
            result["recommendations"].append("SalarySlip class override is not working. Check hooks.py for correct override_doctype_class configuration.")
        
        # Check custom fields
        custom_fields = ["biaya_jabatan", "netto", "total_bpjs", "is_using_ter", "ter_rate", "koreksi_pph21", "payroll_note", "npwp", "ktp"]
        for field in custom_fields:
            result["custom_fields_exist"][field] = hasattr(slip, field)
            debug_log(f"Custom field {field} exists: {result['custom_fields_exist'][field]}")
            
            if not result["custom_fields_exist"][field]:
                result["recommendations"].append(f"Custom field '{field}' is missing. Create this field in Salary Slip doctype.")
        
        # Check dependent doctypes
        dependent_doctypes = ["Employee Tax Summary", "BPJS Payment Summary", "PPh TER Table", "BPJS Settings", "PPh 21 Settings"]
        for dt in dependent_doctypes:
            result["dependent_doctypes_exist"][dt] = frappe.db.exists("DocType", dt)
            debug_log(f"Dependent doctype {dt} exists: {result['dependent_doctypes_exist'][dt]}")
            
            if not result["dependent_doctypes_exist"][dt]:
                result["recommendations"].append(f"Dependent DocType '{dt}' is missing. Ensure it's properly installed.")
        
        # Check module imports
        module_funcs = {
            "calculate_tax_components": calculate_tax_components,
            "calculate_bpjs_components": calculate_bpjs_components,
            "create_tax_summary": create_tax_summary,
            "create_bpjs_payment_summary": create_bpjs_payment_summary,
            "create_pph_ter_table": create_pph_ter_table
        }
        
        for func_name, func in module_funcs.items():
            try:
                # Check if it's a placeholder function by checking source code
                import inspect
                source = inspect.getsource(func)
                result["module_imports_working"][func_name] = "debug_log" not in source
                debug_log(f"Module import for {func_name} working: {result['module_imports_working'][func_name]}")
                
                if not result["module_imports_working"][func_name]:
                    result["recommendations"].append(f"Function '{func_name}' is using placeholder implementation. Check if module files exist and imports are working.")
            except Exception as e:
                result["module_imports_working"][func_name] = False
                debug_log(f"Error checking module import for {func_name}: {str(e)}")
                result["recommendations"].append(f"Error checking function '{func_name}': {str(e)}")
        
        # Test document creation functions if slip is submitted
        if slip.docstatus == 1:
            debug_log(f"Checking related documents for submitted slip {salary_slip_name}")
            
            # Check if tax summary exists
            tax_summary = frappe.db.exists(
                "Employee Tax Summary",
                {"employee": slip.employee, "year": getdate(slip.end_date).year}
            )
            result["tax_summary_exists"] = bool(tax_summary)
            debug_log(f"Tax summary exists: {result['tax_summary_exists']}")
            
            if not result["tax_summary_exists"]:
                result["recommendations"].append("Employee Tax Summary not created for this salary slip. Try running create_tax_summary(slip) manually.")
            
            # Check if BPJS Payment Summary exists
            month = getdate(slip.end_date).month
            year = getdate(slip.end_date).year
            bpjs_summary = frappe.db.exists(
                "BPJS Payment Summary",
                {"company": slip.company, "year": year, "month": month}
            )
            result["bpjs_summary_exists"] = bool(bpjs_summary)
            debug_log(f"BPJS Payment Summary exists: {result['bpjs_summary_exists']}")
            
            if not result["bpjs_summary_exists"]:
                result["recommendations"].append("BPJS Payment Summary not created for this salary slip. Try running create_bpjs_payment_summary(slip) manually.")
            
            # Check if TER Table exists (if using TER)
            if getattr(slip, 'is_using_ter', 0):
                ter_table = frappe.db.exists(
                    "PPh TER Table",
                    {"company": slip.company, "year": year, "month": month}
                )
                result["ter_table_exists"] = bool(ter_table)
                debug_log(f"PPh TER Table exists: {result['ter_table_exists']}")
                
                if not result["ter_table_exists"]:
                    result["recommendations"].append("PPh TER Table not created for this salary slip. Try running create_pph_ter_table(slip) manually.")
        
        debug_log(f"Diagnosis completed for salary slip {salary_slip_name}")
        
        # If no issues found
        if not result["recommendations"]:
            result["recommendations"].append("All components appear to be working correctly. If issues persist, check server logs for detailed errors.")
            
        return result
    except Exception as e:
        debug_log(f"Error in diagnose_salary_slip_submission: {str(e)}\nTraceback: {frappe.get_traceback()}")
        frappe.log_error(
            f"Error in diagnose_salary_slip_submission: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Diagnostic Error"
        )
        result["recommendations"].append(f"Error during diagnosis: {str(e)}")
        return result

@frappe.whitelist()
def manually_create_related_documents(salary_slip_name):
    """
    Manually create all related documents for a salary slip
    """
    debug_log(f"Starting manual creation of related documents for {salary_slip_name}")
    result = {
        "tax_summary": None,
        "bpjs_summary": None,
        "ter_table": None,
        "errors": []
    }
    
    try:
        # Check if salary slip exists
        if not frappe.db.exists("Salary Slip", salary_slip_name):
            debug_log(f"Salary slip {salary_slip_name} does not exist")
            result["errors"].append(f"Salary slip {salary_slip_name} not found")
            return result
            
        # Get the salary slip
        slip = frappe.get_doc("Salary Slip", salary_slip_name)
        
        # Try creating Tax Summary
        try:
            debug_log(f"Manually creating tax summary for {salary_slip_name}")
            create_tax_summary(slip)
            # Check if it was created
            tax_summary = frappe.db.exists(
                "Employee Tax Summary",
                {"employee": slip.employee, "year": getdate(slip.end_date).year}
            )
            result["tax_summary"] = tax_summary
            debug_log(f"Tax summary created: {tax_summary}")
        except Exception as e:
            debug_log(f"Error creating tax summary: {str(e)}\nTraceback: {frappe.get_traceback()}")
            result["errors"].append(f"Error creating tax summary: {str(e)}")
        
        # Try creating BPJS Payment Summary
        try:
            debug_log(f"Manually creating BPJS payment summary for {salary_slip_name}")
            bpjs_summary = create_bpjs_payment_summary(slip)
            result["bpjs_summary"] = bpjs_summary
            debug_log(f"BPJS payment summary created: {bpjs_summary}")
        except Exception as e:
            debug_log(f"Error creating BPJS payment summary: {str(e)}\nTraceback: {frappe.get_traceback()}")
            result["errors"].append(f"Error creating BPJS payment summary: {str(e)}")
        
        # Try creating PPh TER Table if using TER
        if getattr(slip, 'is_using_ter', 0):
            try:
                debug_log(f"Manually creating PPh TER table for {salary_slip_name}")
                ter_table = create_pph_ter_table(slip)
                result["ter_table"] = ter_table
                debug_log(f"PPh TER table created: {ter_table}")
            except Exception as e:
                debug_log(f"Error creating PPh TER table: {str(e)}\nTraceback: {frappe.get_traceback()}")
                result["errors"].append(f"Error creating PPh TER table: {str(e)}")
        
        debug_log(f"Manual creation of related documents completed for {salary_slip_name}")
        return result
    except Exception as e:
        debug_log(f"Error in manually_create_related_documents: {str(e)}\nTraceback: {frappe.get_traceback()}")
        frappe.log_error(
            f"Error in manually_create_related_documents: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Manual Creation Error"
        )
        result["errors"].append(f"Unexpected error: {str(e)}")
        return result        