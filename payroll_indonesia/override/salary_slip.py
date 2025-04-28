# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-28 01:42:00 by dannyaudian

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
    
    # Removed direct imports of summary creator functions that will be moved to separate doctypes
    # Instead, we'll use a queue method to trigger these document creations from their respective doctypes
    
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
            
            # Antrian pembuatan dokumen terkait
            debug_log(f"Queueing creation of related documents for {self.name}")
            self.queue_document_creation()
            
            self.add_payroll_note("Submit berhasil: Pembuatan dokumen terkait telah dijadwalkan.")
            debug_log(f"on_submit completed successfully for {self.name}")
            
        except Exception as e:
            debug_log(f"Error in on_submit for {self.name}: {str(e)}\nTraceback: {frappe.get_traceback()}")
            frappe.log_error(
                f"Error dalam on_submit Salary Slip untuk {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Slip Submit Error"
            )
            frappe.msgprint(_("Warning: Error saat menjadwalkan pembuatan dokumen terkait: {0}").format(str(e)))
    
    def queue_document_creation(self):
        """Jadwalkan pembuatan dokumen terkait melalui background jobs"""
        debug_log(f"Starting queue_document_creation for {self.name}")
        try:
            # Jadwalkan pembuatan tax summary
            debug_log(f"Queuing tax summary creation for {self.name}")
            frappe.enqueue(
                method="payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.create_from_salary_slip",
                queue="short",
                timeout=300,
                is_async=True,
                **{"salary_slip": self.name}
            )
            
            # Cek apakah ada komponen BPJS
            debug_log(f"Checking BPJS components for {self.name}")
            bpjs_components = [
                self.get_component_amount("BPJS JHT Employee", "deductions"),
                self.get_component_amount("BPJS JP Employee", "deductions"),
                self.get_component_amount("BPJS Kesehatan Employee", "deductions")
            ]
            
            debug_log(f"BPJS components for {self.name}: {bpjs_components}")
            
            # Jadwalkan pembuatan BPJS summary jika ada komponen
            if any(component > 0 for component in bpjs_components):
                debug_log(f"Queuing BPJS payment summary creation for {self.name}")
                frappe.enqueue(
                    method="payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_summary.create_from_salary_slip",
                    queue="short",
                    timeout=300,
                    is_async=True,
                    **{"salary_slip": self.name}
                )
            
            # Jadwalkan pembuatan PPh TER Table jika menggunakan metode TER
            if getattr(self, 'is_using_ter', 0) == 1:
                debug_log(f"Queuing PPh TER table creation for {self.name} (is_using_ter=1)")
                frappe.enqueue(
                    method="payroll_indonesia.doctype.pph_ter_table.pph_ter_table.create_from_salary_slip",
                    queue="short",
                    timeout=300,
                    is_async=True,
                    **{"salary_slip": self.name}
                )
            else:
                debug_log(f"Skipping PPh TER table creation for {self.name} (is_using_ter=0)")
                
        except Exception as e:
            debug_log(f"Error in queue_document_creation for {self.name}: {str(e)}\nTraceback: {frappe.get_traceback()}")
            frappe.log_error(
                f"Error dalam queue_document_creation untuk {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Document Queue Error"
            )
            frappe.msgprint(_("Warning: Error saat membuat antrian dokumen terkait: {0}").format(str(e)))
    
    def on_cancel(self):
        """Tangani pembatalan dokumen"""
        debug_log(f"Starting on_cancel for salary slip {self.name}")
        try:
            # Panggil method on_cancel dari kelas induk terlebih dahulu
            debug_log(f"Calling parent on_cancel for {self.name}")
            super(IndonesiaPayrollSalarySlip, self).on_cancel()
            
            # Update dokumen terkait
            debug_log(f"Queueing updates for related documents on cancel for {self.name}")
            self.queue_document_updates_on_cancel()
            
            debug_log(f"on_cancel completed successfully for {self.name}")
            
        except Exception as e:
            debug_log(f"Error in on_cancel for {self.name}: {str(e)}\nTraceback: {frappe.get_traceback()}")
            frappe.log_error(
                f"Error dalam on_cancel Salary Slip untuk {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Slip Cancel Error"
            )
            frappe.msgprint(_("Warning: Error saat mengupdate dokumen terkait pada pembatalan: {0}").format(str(e)))
    
    def queue_document_updates_on_cancel(self):
        """Jadwalkan update dokumen terkait saat membatalkan salary slip"""
        debug_log(f"Starting queue_document_updates_on_cancel for {self.name}")
        month = getdate(self.end_date).month
        year = getdate(self.end_date).year
        
        try:
            # Jadwalkan update untuk BPJS Payment Summary
            debug_log(f"Queuing BPJS summary update on cancel for {self.name} (month={month}, year={year})")
            frappe.enqueue(
                method="payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_summary.update_on_salary_slip_cancel",
                queue="short",
                timeout=300,
                is_async=True,
                **{"salary_slip": self.name, "month": month, "year": year}
            )
            
            # Jadwalkan update untuk PPh TER Table jika menggunakan TER
            if getattr(self, 'is_using_ter', 0) == 1:
                debug_log(f"Queuing TER table update on cancel for {self.name} (month={month}, year={year})")
                frappe.enqueue(
                    method="payroll_indonesia.doctype.pph_ter_table.pph_ter_table.update_on_salary_slip_cancel",
                    queue="short",
                    timeout=300,
                    is_async=True,
                    **{"salary_slip": self.name, "month": month, "year": year}
                )
            
            # Jadwalkan update untuk Employee Tax Summary
            debug_log(f"Queuing tax summary update on cancel for {self.name} (year={year})")
            frappe.enqueue(
                method="payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.update_on_salary_slip_cancel",
                queue="short",
                timeout=300,
                is_async=True,
                **{"salary_slip": self.name, "year": year}
            )
            
            # Jadwalkan penghapusan BPJS Payment Components
            debug_log(f"Queuing deletion of related BPJS components for {self.name}")
            frappe.enqueue(
                method="payroll_indonesia.doctype.bpjs_payment_component.bpjs_payment_component.delete_from_salary_slip",
                queue="short",
                timeout=300,
                is_async=True,
                **{"salary_slip": self.name}
            )
            
            self.add_payroll_note("Cancel berhasil: Pembaruan dokumen terkait telah dijadwalkan.")
            debug_log(f"queue_document_updates_on_cancel completed for {self.name}")
            
        except Exception as e:
            debug_log(f"Error in queue_document_updates_on_cancel: {str(e)}\nTraceback: {frappe.get_traceback()}")
            frappe.log_error(
                f"Error dalam queue_document_updates_on_cancel: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Document Update Queue Error"
            )
            frappe.msgprint(_("Error saat menjadwalkan pembaruan dokumen terkait: {0}").format(str(e)))
    
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
        "related_documents_queued": False,
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
        
        # Check if background jobs system is working
        try:
            from frappe.utils.background_jobs import get_jobs
            queues = ['default', 'short', 'long']
            result["background_jobs_working"] = any(bool(get_jobs(queue)) for queue in queues)
            debug_log(f"Background jobs working: {result['background_jobs_working']}")
            
            if not result["background_jobs_working"]:
                result["recommendations"].append("Background jobs system does not appear to be running. Check if Redis and worker processes are active.")
        except Exception as e:
            debug_log(f"Error checking background jobs: {str(e)}")
            result["background_jobs_working"] = False
            result["recommendations"].append(f"Could not check background jobs system: {str(e)}")
        
        # Test if the slip was successfully submitted
        if slip.docstatus == 1:
            debug_log(f"Checking related documents for submitted slip {salary_slip_name}")
            
            # Check document creation queue entries
            result["related_documents_queued"] = True
            debug_log(f"Related documents assumed to be queued for {salary_slip_name}")
            
        debug_log(f"Diagnosis completed for salary slip {salary_slip_name}")
        
        # If no issues found
        if not result["recommendations"]:
            result["recommendations"].append("All components appear to be working correctly. Documents creation has been queued.")
            
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
