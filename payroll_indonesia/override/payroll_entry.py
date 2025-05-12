# -*- coding: utf-8 -*-
# Copyright (c) 2023, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate
from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry


def safe_log_error(message, title=None, **kwargs):
    """
    Safely log an error with title truncated to max 140 characters

    Args:
        message (str): Error message
        title (str, optional): Error title (will be truncated to 140 chars)
        **kwargs: Additional arguments to pass to frappe.log_error
                  (valid: reference_doctype, reference_name, traceback)
    """
    if not title:
        title = "Payroll Error"

    # Truncate title to 140 characters if needed
    short_title = title[:137] + "..." if len(title) > 140 else title

    # Filter kwargs to only include valid parameters
    valid_kwargs = {}
    for key in ["reference_doctype", "reference_name", "traceback"]:
        if key in kwargs:
            valid_kwargs[key] = kwargs[key]

    try:
        # Call frappe.log_error with the truncated title and valid kwargs
        return frappe.log_error(message=message, title=short_title, **valid_kwargs)
    except Exception:
        # If we still get an error, try with minimal info
        try:
            return frappe.log_error(
                message="Error occurred (details too long)", title="Payroll Log Error"
            )
        except Exception:
            # If all else fails, silently fail
            pass


class CustomPayrollEntry(PayrollEntry):
    def validate(self):
        """Validasi untuk Payroll Entry dengan logika terpusat"""
        try:
            super().validate()
            self._validate_payroll_dates()
            self._validate_employee_list()

            # Logic moved from before_validate()
            if hasattr(self, "employees") and not self.employees:
                frappe.msgprint(
                    _("Tidak ada karyawan yang ditemukan. Memeriksa filter..."), indicator="blue"
                )

                try:
                    # Cek karyawan aktif di perusahaan
                    active_employees = frappe.db.sql(
                        """
                        SELECT name, employee_name
                        FROM `tabEmployee`
                        WHERE status = 'Active' AND company = %s
                    """,
                        (self.company),
                        as_dict=True,
                    )

                    if not active_employees:
                        frappe.msgprint(
                            _("Tidak ada karyawan aktif di perusahaan {0}").format(self.company),
                            indicator="orange",
                        )
                    else:
                        # Cek salary structure assignment
                        employees_with_structure = []
                        for emp in active_employees:
                            has_structure = frappe.db.exists(
                                "Salary Structure Assignment",
                                {"employee": emp.name, "docstatus": 1},
                            )

                            if has_structure:
                                employees_with_structure.append(emp)

                        if not employees_with_structure:
                            frappe.msgprint(
                                _("Karyawan aktif tidak memiliki Salary Structure Assignment"),
                                indicator="orange",
                            )
                        else:
                            # Cek karyawan dengan slip gaji yang sudah ada
                            for emp in employees_with_structure:
                                existing_slip = frappe.db.exists(
                                    "Salary Slip",
                                    {
                                        "employee": emp.name,
                                        "start_date": self.start_date,
                                        "end_date": self.end_date,
                                        "docstatus": ["!=", 2],  # Not cancelled
                                    },
                                )

                                if existing_slip:
                                    frappe.msgprint(
                                        _(
                                            "Karyawan {0} sudah memiliki slip gaji untuk periode ini: {1}"
                                        ).format(emp.employee_name, existing_slip),
                                        indicator="blue",
                                    )
                except Exception as e:
                    # Non-critical error during filter checking - log and continue
                    safe_log_error(
                        f"Error checking employee filters for {self.name}: {str(e)}",
                        "Payroll Entry Filter Check",
                    )
                    frappe.msgprint(
                        _("Error checking employee filters. See error log for details."),
                        indicator="orange",
                    )
        except Exception as e:
            # Handle ValidationError separately
            if isinstance(e, frappe.exceptions.ValidationError):
                raise

            # For other errors, log and re-raise as validation error
            safe_log_error(
                f"Error validating Payroll Entry {self.name}: {str(e)}", "Payroll Entry Validation"
            )
            frappe.throw(_("Error validating Payroll Entry: {0}").format(str(e)))

    def _validate_payroll_dates(self):
        """Validasi tanggal payroll untuk konteks Indonesia"""
        try:
            # Validasi bahwa tanggal berada dalam bulan yang sama
            start_month = getdate(self.start_date).month
            end_month = getdate(self.end_date).month

            if start_month != end_month:
                frappe.throw(
                    _(
                        "Untuk perhitungan pajak Indonesia, periode payroll harus berada dalam bulan yang sama"
                    ),
                    title=_("Invalid Payroll Period"),
                )
        except Exception as e:
            # Critical validation - re-raise as ValidationError
            if isinstance(e, frappe.exceptions.ValidationError):
                raise

            safe_log_error(
                f"Error validating payroll dates for {self.name}: {str(e)}",
                "Payroll Date Validation",
            )
            frappe.throw(_("Error validating payroll dates: {0}").format(str(e)))

    def _validate_employee_list(self):
        """Validasi daftar karyawan"""
        try:
            if hasattr(self, "employees") and self.employees:
                # Periksa apakah ada employee yang tidak valid
                invalid_employees = [emp for emp in self.employees if not emp.employee]

                if invalid_employees:
                    # This is a warning, not a validation failure - processing can continue
                    frappe.msgprint(
                        _(
                            "Ditemukan {0} data karyawan yang tidak valid. Data ini akan diabaikan saat pemrosesan."
                        ).format(len(invalid_employees)),
                        title=_("Perhatian"),
                        indicator="orange",
                    )

                    # Hapus employee yang tidak valid
                    self.employees = [emp for emp in self.employees if emp.employee]
        except Exception as e:
            # Non-critical error during employee validation - log and continue
            safe_log_error(
                f"Error validating employee list for {self.name}: {str(e)}",
                "Employee List Validation",
            )
            frappe.msgprint(
                _(
                    "Error validating employee list. Some employees may be skipped. See error log for details."
                ),
                indicator="orange",
            )

    def on_submit(self):
        """Handler untuk proses saat Payroll Entry disubmit"""
        try:
            super().on_submit()

            # Cek apakah periode adalah Desember (untuk koreksi tahunan)
            is_december = getdate(self.end_date).month == 12

            if is_december:
                frappe.msgprint(
                    _(
                        "Periode Desember terdeteksi. Sistem akan otomatis melakukan perhitungan koreksi pajak tahunan."
                    ),
                    title=_("Koreksi Pajak Tahunan"),
                    indicator="blue",
                )

            # Tambahkan log
            safe_log_error(
                f"Payroll Entry {self.name} for period {self.start_date} to {self.end_date} submitted by {frappe.session.user}",
                "Payroll Entry Submission",
            )
        except Exception as e:
            # Handle ValidationError separately
            if isinstance(e, frappe.exceptions.ValidationError):
                raise

            # Critical error during submission - must stop
            safe_log_error(
                f"Error submitting Payroll Entry {self.name}: {str(e)}",
                "Payroll Entry Submission Error",
            )
            frappe.throw(_("Error submitting Payroll Entry: {0}").format(str(e)))

    def get_emp_list(self):
        """Override untuk mendapatkan daftar karyawan yang valid"""
        try:
            # Coba ambil daftar karyawan dengan filter minimal
            minimal_emp_list = frappe.db.sql(
                """
                select
                    name as employee, employee_name, department, designation
                from
                    `tabEmployee`
                where
                    status = 'Active'
                    and company = %s
            """,
                (self.company),
                as_dict=True,
            )

            # Log jumlah karyawan bukan seluruh data untuk menghindari error truncated
            safe_log_error(f"Employee count: {len(minimal_emp_list)}", "Employee Query")

            # Filter karyawan yang memiliki salary structure assignment
            emp_list_with_structure = []
            for emp in minimal_emp_list:
                # Cek apakah karyawan memiliki salary structure assignment
                has_structure = frappe.db.exists(
                    "Salary Structure Assignment", {"employee": emp.employee, "docstatus": 1}
                )

                if has_structure:
                    emp_list_with_structure.append(emp)

            if not emp_list_with_structure:
                # This is a warning, not a validation failure - return empty list
                frappe.msgprint(
                    _("Tidak ada karyawan yang memiliki Salary Structure Assignment aktif."),
                    title=_("Salary Structure Missing"),
                    indicator="red",
                )

            # Filter: hilangkan employee yang None atau kosong
            filtered_emp_list = [emp for emp in emp_list_with_structure if emp.get("employee")]

            # Tampilkan daftar karyawan yang akan diproses (batasi jumlah nama yang ditampilkan)
            if filtered_emp_list:
                # Batasi jumlah karyawan yang ditampilkan untuk menghindari pesan terlalu panjang
                max_display = 5
                displayed_emps = filtered_emp_list[:max_display]

                employee_names = ", ".join(
                    [
                        "{0} ({1})".format(emp.get("employee_name"), emp.get("employee"))
                        for emp in displayed_emps
                    ]
                )

                # Tambahkan teks "+X lainnya" jika karyawan lebih dari max_display
                if len(filtered_emp_list) > max_display:
                    remaining = len(filtered_emp_list) - max_display
                    employee_names += _(" dan {0} karyawan lainnya").format(remaining)

                frappe.msgprint(
                    _("Karyawan yang akan diproses: {0}").format(employee_names), indicator="blue"
                )
            else:
                frappe.msgprint(
                    _("Tidak ada karyawan yang memenuhi kriteria untuk payroll ini"),
                    indicator="orange",
                )

            return filtered_emp_list

        except Exception as e:
            # This is a critical error - can't continue without employee list
            safe_log_error(
                f"Error retrieving employee list for {self.name}: {str(e)}", "Employee List Error"
            )
            frappe.throw(_("Error retrieving employee list: {0}").format(str(e)))

    def get_existing_salary_slips(self, employees):
        """
        Mendapatkan daftar salary slip yang sudah ada
        untuk karyawan dalam periode payroll yang sama
        """
        try:
            existing_slip_names = []
            existing_slips = []

            # Pastikan employees adalah list objek dengan key 'employee'
            employees_list = [
                emp if isinstance(emp, dict) else {"employee": emp} for emp in employees
            ]

            # Ambil list ID karyawan
            employee_list = [d.get("employee") for d in employees_list if d.get("employee")]

            if not employee_list:
                return existing_slip_names

            # Query untuk mendapatkan slip gaji yang sudah ada
            existing_slips = frappe.db.sql(
                """
                select distinct employee
                from `tabSalary Slip`
                where docstatus != 2
                and company = %s
                and start_date = %s
                and end_date = %s
                and employee in (%s)
            """
                % ("%s", "%s", "%s", ", ".join(["%s"] * len(employee_list))),
                tuple([self.company, self.start_date, self.end_date] + employee_list),
                as_dict=True,
            )

            existing_slip_names = [d.employee for d in existing_slips if d.employee]
            return existing_slip_names

        except Exception as e:
            # Non-critical error - log and return empty list
            safe_log_error(
                f"Error retrieving existing salary slips for {self.name}: {str(e)}",
                "Existing Slip Retrieval",
            )
            frappe.msgprint(
                _("Warning: Could not check for existing salary slips. Duplicates may be created."),
                indicator="orange",
            )
            return []

    def create_salary_slips(self):
        """Buat slip gaji untuk karyawan yang dipilih"""
        try:
            self.check_permission("write")

            # Dapatkan daftar karyawan yang valid
            employees = self.get_emp_list()
            if not employees:
                # Critical validation - must have employees to create slips
                frappe.throw(
                    _("Tidak ada karyawan yang valid untuk pembuatan slip gaji"),
                    title=_("No Valid Employees"),
                )

            # Log aktifitas
            frappe.msgprint(
                _("Membuat slip gaji untuk {0} karyawan").format(len(employees)), indicator="blue"
            )

            # Buat salary slips
            return self.create_salary_slips_for_employees(employees)

        except Exception as e:
            # Handle ValidationError separately
            if isinstance(e, frappe.exceptions.ValidationError):
                raise

            # Critical error - can't create salary slips
            safe_log_error(
                f"Error creating salary slips for {self.name}: {str(e)}",
                "Salary Slip Creation Error",
            )
            frappe.throw(_("Error creating salary slips: {0}").format(str(e)))

    def create_salary_slips_for_employees(self, employees, publish_progress=True):
        """
        Buat salary slips untuk karyawan yang dipilih
        dengan validasi tambahan untuk konteks Indonesia
        """
        try:
            # Filter untuk menghilangkan employee yang None atau kosong
            employees = [emp if isinstance(emp, dict) else {"employee": emp} for emp in employees]
            employees = [emp for emp in employees if emp and emp.get("employee")]

            if not employees:
                # Critical validation - must have employees after filtering
                frappe.throw(
                    _("Tidak ada karyawan valid yang dipilih untuk pembuatan slip gaji"),
                    title=_("No Valid Employees"),
                )

            # Lanjutkan dengan pemrosesan standar
            salary_slips_exist_for = self.get_existing_salary_slips(employees)
            count = 0
            error_count = 0

            for emp in employees:
                employee = emp.get("employee")

                if employee in salary_slips_exist_for:
                    continue

                # Pastikan employee ada dan valid
                if not employee or not frappe.db.exists("Employee", employee):
                    # Non-critical error - can skip this employee and continue
                    frappe.msgprint(
                        _("Employee {0} tidak valid, melewati pembuatan slip gaji").format(
                            employee or "None"
                        ),
                        indicator="orange",
                    )
                    continue

                # Buat salary slip
                args = self.get_salary_slip_args(employee)

                try:
                    salary_slip = frappe.get_doc(args)
                    salary_slip.insert()
                    count += 1

                    # Update progress if needed
                    if publish_progress:
                        # Fix bug with set() usage for list of dicts
                        unique_employees = {
                            e.get("employee") for e in employees if e.get("employee")
                        }
                        existing_slips_set = set(salary_slips_exist_for)
                        denominator = max(1, len(unique_employees - existing_slips_set))
                        frappe.publish_progress(
                            count * 100 / denominator, title=_("Creating Salary Slips...")
                        )

                except Exception as e:
                    # Non-critical error - can continue with other employees
                    error_count += 1
                    error_msg = f"Gagal membuat Salary Slip untuk {employee}: {str(e)}"

                    # Batasi panjang error message untuk log
                    if len(error_msg) > 900:  # Batas aman untuk field `message` pada Error Log
                        error_msg = error_msg[:900] + "... [truncated]"

                    frappe.msgprint(
                        _("Gagal membuat Salary Slip untuk {0}").format(employee),
                        title=_("Salary Slip Creation Failed"),
                        indicator="orange",
                    )
                    safe_log_error(error_msg, "Salary Slip Creation Error")

            # Log ringkasan hasil
            result_msg = f"Created {count} salary slips, {error_count} errors"
            safe_log_error(result_msg, "Salary Slip Creation Summary")

            # Show summary to user
            if error_count > 0:
                frappe.msgprint(
                    _(
                        "Created {0} salary slips with {1} errors. See error log for details."
                    ).format(count, error_count),
                    indicator="orange",
                )
            else:
                frappe.msgprint(
                    _("Successfully created {0} salary slips.").format(count), indicator="green"
                )

            return salary_slips_exist_for, count

        except Exception as e:
            # Handle ValidationError separately
            if isinstance(e, frappe.exceptions.ValidationError):
                raise

            # Critical error - can't create salary slips
            safe_log_error(
                f"Error creating salary slips for employees: {str(e)}", "Salary Slip Creation Error"
            )
            frappe.throw(_("Error creating salary slips: {0}").format(str(e)))

    def get_salary_slip_args(self, employee):
        """Generate args untuk salary slip dengan konteks Indonesia"""
        try:
            # Validasi employee
            if not employee:
                frappe.throw(_("Employee ID tidak boleh kosong"), title=_("Invalid Employee"))

            employee_doc = frappe.get_doc("Employee", employee)

            # Make sure date_of_joining exists
            if not employee_doc.date_of_joining:
                frappe.throw(
                    _("Please set the Date Of Joining for employee <strong>{0}</strong>").format(
                        employee
                    ),
                    title=_("Missing Date of Joining"),
                )

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
                "employee": employee,
            }

            # Add Indonesia specific fields
            if hasattr(self, "use_ter_method"):
                args["use_ter_method"] = self.use_ter_method

            # Add TER category and TER rate if they exist
            if hasattr(self, "ter_category"):
                args["ter_category"] = self.ter_category

            if hasattr(self, "ter_rate"):
                args["ter_rate"] = self.ter_rate

            return args

        except Exception as e:
            # Handle ValidationError separately
            if isinstance(e, frappe.exceptions.ValidationError):
                raise

            # Critical error - can't create salary slip args
            safe_log_error(
                f"Error getting salary slip args for employee {employee}: {str(e)}",
                "Salary Slip Args Error",
            )
            frappe.throw(
                _("Error generating salary slip data for {0}: {1}").format(employee, str(e))
            )
