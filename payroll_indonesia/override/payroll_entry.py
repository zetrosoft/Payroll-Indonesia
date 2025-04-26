# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-26 08:40:12 by dannyaudian

import frappe
from frappe import _
from frappe.utils import getdate
from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry

class CustomPayrollEntry(PayrollEntry):
    def validate(self):
        """Validasi tambahan untuk Payroll Entry"""
        super().validate()
        self.validate_payroll_dates()
        
    def validate_payroll_dates(self):
        """Validasi tanggal payroll untuk konteks Indonesia"""
        # Validasi bahwa tanggal berada dalam bulan yang sama
        start_month = getdate(self.start_date).month
        end_month = getdate(self.end_date).month
        
        if start_month != end_month:
            frappe.throw(_("Untuk perhitungan pajak Indonesia, periode payroll harus berada dalam bulan yang sama"))
    
    def get_emp_list(self):
        """Override untuk mendapatkan daftar karyawan yang valid"""
        # Coba ambil daftar karyawan dengan filter minimal
        minimal_emp_list = frappe.db.sql("""
            select
                name as employee, employee_name, department, designation
            from
                `tabEmployee`
            where
                status = 'Active'
                and company = %s
        """, (self.company), as_dict=True)
        
        frappe.log_error(f"Minimal employee list: {minimal_emp_list}", "Employee Query")
        
        # Filter karyawan yang memiliki salary structure assignment
        emp_list_with_structure = []
        for emp in minimal_emp_list:
            # Cek apakah karyawan memiliki salary structure assignment
            has_structure = frappe.db.exists("Salary Structure Assignment", {
                "employee": emp.employee,
                "docstatus": 1
            })
            
            if has_structure:
                emp_list_with_structure.append(emp)
        
        if not emp_list_with_structure:
            frappe.msgprint(_("Tidak ada karyawan yang memiliki Salary Structure Assignment aktif."), 
                           title=_("Salary Structure Missing"), indicator="red")
        
        # Filter: hilangkan employee yang None atau kosong
        filtered_emp_list = [emp for emp in emp_list_with_structure if emp.get('employee')]
        
        # Tampilkan daftar karyawan yang akan diproses
        if filtered_emp_list:
            employee_names = ", ".join([f"{emp.get('employee_name')} ({emp.get('employee')})" for emp in filtered_emp_list])
            frappe.msgprint(_(f"Karyawan yang akan diproses: {employee_names}"))
        else:
            frappe.msgprint(_("Tidak ada karyawan yang memenuhi kriteria untuk payroll ini"))
        
        return filtered_emp_list
        
    def create_salary_slips(self):
        """Buat slip gaji untuk karyawan yang dipilih"""
        self.check_permission("write")
        
        # Dapatkan daftar karyawan yang valid
        employees = self.get_emp_list()
        if not employees:
            frappe.throw(_("Tidak ada karyawan yang valid untuk pembuatan slip gaji"))
            
        # Log aktifitas
        frappe.msgprint(_("Membuat slip gaji untuk {0} karyawan").format(len(employees)))
            
        # Buat salary slips
        return self.create_salary_slips_for_employees(employees)
        
    def create_salary_slips_for_employees(self, employees, publish_progress=True):
        """
        Buat salary slips untuk karyawan yang dipilih
        dengan validasi tambahan untuk konteks Indonesia
        """
        # Filter untuk menghilangkan employee yang None atau kosong
        employees = [emp if isinstance(emp, dict) else {"employee": emp} for emp in employees]
        employees = [emp for emp in employees if emp and emp.get('employee')]
        
        if not employees:
            frappe.throw(_("Tidak ada karyawan valid yang dipilih untuk pembuatan slip gaji"))
            
        # Lanjutkan dengan pemrosesan standar
        salary_slips_exist_for = self.get_existing_salary_slips(employees)
        count = 0
        
        for emp in employees:
            employee = emp.get('employee')
            
            if employee in salary_slips_exist_for:
                continue
                
            # Pastikan employee ada dan valid
            if not employee or not frappe.db.exists("Employee", employee):
                frappe.msgprint(_("Employee {0} tidak valid, melewati pembuatan slip gaji").format(employee or "None"))
                continue
                
            # Buat salary slip
            args = self.get_salary_slip_args(employee)
            
            try:
                salary_slip = frappe.get_doc(args)
                salary_slip.insert()
                count += 1
                
                # Update progress if needed
                if publish_progress:
                    frappe.publish_progress(
                        count * 100 / len(set(employees) - set(salary_slips_exist_for)),
                        title=_("Creating Salary Slips...")
                    )
                    
            except Exception as e:
                frappe.msgprint(
                    _("Gagal membuat Salary Slip untuk {0}: {1}").format(employee, str(e)),
                    title=_("Salary Slip Creation Failed")
                )
                frappe.log_error(
                    f"Payroll Entry - Gagal membuat Salary Slip untuk employee {employee}: {str(e)}"
                )
        
        return salary_slips_exist_for, count
    
    def get_salary_slip_args(self, employee):
        """Generate args untuk salary slip dengan konteks Indonesia"""
        
        # Validasi employee
        if not employee:
            frappe.throw(_("Employee ID tidak boleh kosong"))
            
        employee_doc = frappe.get_doc("Employee", employee)
        
        # Make sure date_of_joining exists
        if not employee_doc.date_of_joining:
            frappe.throw(_("Please set the Date Of Joining for employee <strong>{0}</strong>").format(employee))
        
        # Standard args
        args = {
            "salary_slip_based_on_timesheet": self.salary_slip_based_on_timesheet,
            "payroll_frequency": self.payroll_frequency,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "company": self.company,
            "posting_date": self.posting_date,
            "deduct_tax_for_unclaimed_employee_benefits": self.deduct_tax_for_unclaimed_employee_benefits,
            "deduct_tax_for_unsubmitted_tax_exemption_proof": self.deduct_tax_for_unsubmitted_tax_exemption_proof,
            "payroll_entry": self.name,
            "exchange_rate": self.exchange_rate,
            "currency": self.currency,
            "doctype": "Salary Slip",
            "employee": employee
        }
        
        # Add Indonesia specific fields
        if hasattr(self, "use_ter_method"):
            args["use_ter_method"] = self.use_ter_method
            
        return args