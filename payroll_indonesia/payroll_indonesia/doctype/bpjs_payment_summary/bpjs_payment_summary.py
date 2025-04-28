# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-28 02:15:00 by dannyaudian

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, flt, fmt_money, getdate, now_datetime

# Debug function for error tracking
def debug_log(message, module_name="BPJS Payment Summary"):
    """Log debug message with timestamp and additional info"""
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    frappe.log_error(f"[{timestamp}] {message}", module_name)

# Define custom formatter to replace missing get_formatted_currency
def get_formatted_currency(value, company=None):
    """Format currency value based on company settings"""
    if company:
        currency = frappe.get_cached_value('Company', company, 'default_currency')
    else:
        currency = frappe.db.get_default("currency")
    return fmt_money(value, currency=currency)

class BPJSPaymentSummary(Document):
    def validate(self):
        self.validate_company()
        self.validate_month_year()
        self.validate_components()
        self.calculate_total()
        self.validate_total()
        self.validate_supplier()
        self.set_account_details()
    
    def validate_company(self):
        """Validate company and its default accounts"""
        if not self.company:
            frappe.throw(_("Company is mandatory"))
            
        # Check default accounts
        company_doc = frappe.get_doc("Company", self.company)
        if not company_doc.default_bank_account:
            frappe.throw(_("Default Bank Account not set for Company {0}").format(self.company))
        if not company_doc.default_payable_account:
            frappe.throw(_("Default Payable Account not set for Company {0}").format(self.company))
    
    def validate_month_year(self):
        """Ensure month and year are valid"""
        if not self.month or not self.year:
            frappe.throw(_("Both Month and Year are mandatory"))
        if self.month < 1 or self.month > 12:
            frappe.throw(_("Month must be between 1 and 12"))
        if self.year < 2000:
            frappe.throw(_("Year must be greater than or equal to 2000"))
    
    def validate_components(self):
        """Validate BPJS components"""
        if not self.komponen:
            frappe.throw(_("At least one BPJS component is required"))
            
        for d in self.komponen:
            if not d.amount or d.amount <= 0:
                frappe.throw(_("Amount must be greater than 0 for component {0}").format(d.idx))
    
    def calculate_total(self):
        """Calculate total from components"""
        self.total = sum(flt(d.amount) for d in self.komponen)
    
    def validate_total(self):
        """Validate total amount is greater than 0"""
        if not self.total or self.total <= 0:
            frappe.throw(_("Total amount must be greater than 0"))
    
    def validate_supplier(self):
        """Validate BPJS supplier exists"""
        if not frappe.db.exists("Supplier", "BPJS"):
            from .bpjs_payment_validation import create_bpjs_supplier
            create_bpjs_supplier()
            
    def set_account_details(self):
        """Set account details dari BPJS Settings dan Account Mapping"""
        if self.docstatus == 1:
            frappe.throw(_("Cannot modify account details after submission"))
            
        # Hapus account_details yang sudah ada
        self.account_details = []
        
        try:
            # Cari BPJS Account Mapping khusus untuk perusahaan
            account_mapping = frappe.get_all(
                "BPJS Account Mapping",
                filters={"company": self.company},
                limit=1
            )
            
            if account_mapping:
                # Gunakan mapping perusahaan spesifik
                mapping_doc = frappe.get_doc("BPJS Account Mapping", account_mapping[0].name)
                
                # Hitung total untuk setiap jenis BPJS dari employee_details
                bpjs_totals = {
                    "Kesehatan": 0,
                    "JHT": 0,
                    "JP": 0,
                    "JKK": 0,
                    "JKM": 0
                }
                
                # Hitung total dari employee_details jika ada
                if hasattr(self, 'employee_details') and self.employee_details:
                    for emp in self.employee_details:
                        bpjs_totals["Kesehatan"] += flt(emp.kesehatan_employee) + flt(emp.kesehatan_employer)
                        bpjs_totals["JHT"] += flt(emp.jht_employee) + flt(emp.jht_employer)
                        bpjs_totals["JP"] += flt(emp.jp_employee) + flt(emp.jp_employer)
                        bpjs_totals["JKK"] += flt(emp.jkk)
                        bpjs_totals["JKM"] += flt(emp.jkm)
                else:
                    # Jika tidak ada employee_details, gunakan data dari komponen
                    component_type_map = {
                        "BPJS Kesehatan": "Kesehatan",
                        "BPJS JHT": "JHT",
                        "BPJS JP": "JP",
                        "BPJS JKK": "JKK",
                        "BPJS JKM": "JKM"
                    }
                    
                    for comp in self.komponen:
                        bpjs_type = component_type_map.get(comp.component)
                        if bpjs_type:
                            bpjs_totals[bpjs_type] += flt(comp.amount)
                
                # Mapping field nama dengan properti account dan tipe BPJS
                account_fields = [
                    {"field": "kesehatan_account", "type": "Kesehatan"},
                    {"field": "jht_account", "type": "JHT"},
                    {"field": "jp_account", "type": "JP"},
                    {"field": "jkk_account", "type": "JKK"},
                    {"field": "jkm_account", "type": "JKM"}
                ]
                
                # Tambahkan account details berdasarkan mapping
                for field_info in account_fields:
                    field = field_info["field"]
                    bpjs_type = field_info["type"]
                    
                    # Ambil akun dari mapping
                    account = getattr(mapping_doc, field, None)
                    amount = bpjs_totals[bpjs_type]
                    
                    if account and amount > 0:
                        # Format penamaan referensi sesuai standar
                        month_names = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 
                                      'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']
                        month_name = month_names[self.month - 1] if self.month >= 1 and self.month <= 12 else str(self.month)
                        
                        self.append("account_details", {
                            "account_type": bpjs_type,
                            "account": account,
                            "amount": amount,
                            "reference_number": f"BPJS-{bpjs_type}-{self.month}-{self.year}",
                            "description": f"BPJS {bpjs_type} {month_name} {self.year}"
                        })
                
                # Validasi total account_details sesuai dengan total dokumen
                account_total = sum(flt(acc.amount) for acc in self.account_details)
                if abs(account_total - self.total) > 0.1:  # Toleransi 0.1 untuk pembulatan
                    frappe.msgprint(
                        _("Warning: Total from account details ({0}) doesn't match document total ({1})").format(
                            account_total, self.total
                        ),
                        indicator='orange'
                    )
                    
            else:
                # Jika tidak ada mapping khusus perusahaan, gunakan BPJS Settings global
                bpjs_settings = frappe.get_single("BPJS Settings")
                
                # Mapping komponen dengan tipe dan field GL account di settings
                component_mapping = {
                    "BPJS Kesehatan": {"type": "Kesehatan", "account_field": "kesehatan_account"},
                    "BPJS JHT": {"type": "JHT", "account_field": "jht_account"},
                    "BPJS JP": {"type": "JP", "account_field": "jp_account"},
                    "BPJS JKK": {"type": "JKK", "account_field": "jkk_account"},
                    "BPJS JKM": {"type": "JKM", "account_field": "jkm_account"}
                }
                
                # Loop komponen BPJS dan tambahkan account details
                for comp in self.komponen:
                    if comp.component in component_mapping:
                        mapping = component_mapping[comp.component]
                        account_type = mapping["type"]
                        account_field = mapping["account_field"]
                        
                        # Skip jika tidak ada GL account yang sesuai di BPJS Settings
                        if not hasattr(bpjs_settings, account_field) or not getattr(bpjs_settings, account_field):
                            frappe.msgprint(
                                _("No account defined for {0} in BPJS Settings").format(account_type),
                                indicator='orange'
                            )
                            continue
                            
                        # Format penamaan referensi sesuai standar
                        month_names = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 
                                      'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']
                        month_name = month_names[self.month - 1] if self.month >= 1 and self.month <= 12 else str(self.month)
                        
                        # Tambahkan ke account_details table
                        self.append("account_details", {
                            "account_type": account_type,
                            "account": getattr(bpjs_settings, account_field),
                            "amount": comp.amount,
                            "reference_number": f"BPJS-{account_type}-{self.month}-{self.year}",
                            "description": f"BPJS {account_type} {month_name} {self.year}"
                        })
        
        except Exception as e:
            frappe.log_error(
                f"Error setting account details for BPJS Payment Summary {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Account Details Error"
            )
            frappe.msgprint(
                _("Error setting account details: {0}").format(str(e)),
                indicator='red'
            )
    
    def on_submit(self):
        """Set status to Submitted and create journal entry"""
        self.status = "Submitted"
        self.create_journal_entry()
    
    def on_cancel(self):
        """Reset status to Draft"""
        if self.payment_entry:
            pe_status = frappe.db.get_value("Payment Entry", self.payment_entry, "docstatus")
            if pe_status and int(pe_status) == 1:
                frappe.throw(_("Cannot cancel document with submitted Payment Entry"))
        
        if self.journal_entry:
            je_status = frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus")
            if je_status and int(je_status) == 1:
                frappe.throw(_("Cannot cancel document with submitted Journal Entry. Cancel the Journal Entry first."))
                
        self.status = "Draft"
    
    def create_journal_entry(self):
        """Create Journal Entry for BPJS Payment Summary on submission"""
        try:
            # Validate account details exist
            if not self.account_details or len(self.account_details) == 0:
                frappe.msgprint(_("No account details found. Journal Entry not created."))
                return
            
            # Get BPJS settings
            bpjs_settings = frappe.get_single("BPJS Settings")
            
            # Get default accounts
            company_default_accounts = frappe.get_cached_value('Company', self.company, 
                ['default_expense_account', 'default_payable_account', 'cost_center'], as_dict=1)
            
            # Create Journal Entry
            je = frappe.new_doc("Journal Entry")
            je.voucher_type = "Journal Entry"
            je.company = self.company
            je.posting_date = self.posting_date
            
            # Format month name for description
            month_names = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 
                          'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']
            month_name = month_names[self.month - 1] if self.month >= 1 and self.month <= 12 else str(self.month)
            
            je.user_remark = f"BPJS Contributions for {month_name} {self.year}"
            
            # Calculate totals from employee_details
            employee_total = 0
            employer_total = 0
            
            if hasattr(self, 'employee_details') and self.employee_details:
                for d in self.employee_details:
                    # Sum up employee contributions
                    employee_total += (
                        flt(d.kesehatan_employee) + 
                        flt(d.jht_employee) + 
                        flt(d.jp_employee)
                    )
                    
                    # Sum up employer contributions
                    employer_total += (
                        flt(d.kesehatan_employer) + 
                        flt(d.jht_employer) + 
                        flt(d.jp_employer) +
                        flt(d.jkk) + 
                        flt(d.jkm)
                    )
            
            # Add expense entries (debit)
            # First for employee contributions - expense to Salary Payable
            if employee_total > 0:
                je.append("accounts", {
                    "account": company_default_accounts.default_payable_account,
                    "debit_in_account_currency": employee_total,
                    "reference_type": "BPJS Payment Summary",
                    "reference_name": self.name,
                    "cost_center": company_default_accounts.cost_center
                })
                
            # For employer contributions - expense to BPJS Expense account
            expense_account = bpjs_settings.expense_account if hasattr(bpjs_settings, 'expense_account') and bpjs_settings.expense_account else company_default_accounts.default_expense_account
            
            if employer_total > 0:
                je.append("accounts", {
                    "account": expense_account,
                    "debit_in_account_currency": employer_total,
                    "reference_type": "BPJS Payment Summary",
                    "reference_name": self.name,
                    "cost_center": company_default_accounts.cost_center
                })
                
            # Add liability entries (credit)
            for acc in self.account_details:
                je.append("accounts", {
                    "account": acc.account,
                    "credit_in_account_currency": acc.amount,
                    "reference_type": "BPJS Payment Summary",
                    "reference_name": self.name,
                    "cost_center": company_default_accounts.cost_center
                })
                
            # Save and submit journal entry
            je.insert()
            je.submit()
            
            # Update reference in BPJS Payment Summary
            self.db_set('journal_entry', je.name)
            
            frappe.msgprint(_("Journal Entry {0} created successfully").format(je.name))
            
        except Exception as e:
            frappe.log_error(
                f"Error creating Journal Entry for BPJS Payment Summary {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Journal Entry Error"
            )
            frappe.msgprint(_("Error creating Journal Entry: {0}").format(str(e)))
    
    @frappe.whitelist()
    def generate_payment_entry(self):
        """Generate Payment Entry for BPJS payment"""
        if self.payment_entry:
            frappe.throw(_("Payment Entry already exists"))
            
        if self.docstatus != 1:
            frappe.throw(_("Document must be submitted first"))
        
        # Validasi account details
        if not self.account_details or len(self.account_details) == 0:
            frappe.throw(_("No account details found. Please set account details first."))
        
        try:
            # Get BPJS supplier
            if not frappe.db.exists("Supplier", "BPJS"):
                frappe.throw(_("BPJS supplier not found"))
            
            # Create payment entry
            pe = frappe.new_doc("Payment Entry")
            pe.payment_type = "Pay"
            pe.party_type = "Supplier"
            pe.party = "BPJS"
            pe.posting_date = today()
            pe.paid_amount = self.total
            pe.received_amount = self.total
            
            # Set company and accounts
            pe.company = self.company
            pe.paid_from = frappe.get_cached_value('Company', self.company, 'default_bank_account')
            
            # Use the primary account from account_details
            primary_account = self.account_details[0].account
            pe.paid_to = primary_account
            
            # Add references to BPJS Payment Summary
            pe.append("references", {
                "reference_doctype": self.doctype,
                "reference_name": self.name,
                "allocated_amount": self.total
            })
            
            # Add deductions for different BPJS components (except the primary component)
            for acc in self.account_details[1:]:  # Skip the first one as it's the main account
                pe.append("deductions", {
                    "account": acc.account,
                    "amount": acc.amount,
                    "description": acc.description or f"BPJS {acc.account_type} Payment"
                })
            
            # Format for custom reference number
            month_names = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 
                          'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']
            month_name = month_names[self.month - 1] if self.month >= 1 and self.month <= 12 else str(self.month)
            
            # Set reference details
            pe.reference_no = f"BPJS-{self.month}-{self.year}"
            pe.reference_date = today()
            
            # Add custom remarks with components
            components_text = "\n".join([
                f"- {d.component}: {get_formatted_currency(d.amount, pe.company)}"
                for d in self.komponen
            ])
            pe.remarks = (
                f"BPJS Payment for {self.name}\n"
                f"Periode: {month_name} {self.year}\n"
                f"Components:\n{components_text}"
            )
            
            # Save but don't submit - let user review and submit manually
            pe.insert()
            
            # Update this document with payment reference
            self.db_set('payment_entry', pe.name)
            
            frappe.msgprint(
                _("Payment Entry {0} created successfully. Please review and submit it.").format(pe.name),
                indicator='green'
            )
            
            return pe.name
            
        except Exception as e:
            frappe.log_error(
                f"Error creating Payment Entry for BPJS Payment Summary {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Payment Entry Error"
            )
            frappe.msgprint(_("Error creating Payment Entry"))
            frappe.throw(str(e))

# ----- Fungsi tambahan untuk integrasi dengan Salary Slip -----

@frappe.whitelist()
def create_from_salary_slip(salary_slip):
    """
    Create or update BPJS Payment Summary from a Salary Slip
    Called asynchronously from the Salary Slip's on_submit method
    """
    debug_log(f"Starting create_from_salary_slip for {salary_slip}")
    
    try:
        # Get the salary slip document
        slip = frappe.get_doc("Salary Slip", salary_slip)
        if not slip or slip.docstatus != 1:
            debug_log(f"Salary slip {salary_slip} not found or not submitted")
            return None
            
        # Check if there are any BPJS components
        bpjs_components = {
            "employee": {},
            "employer": {}
        }
        
        # Ambil data langsung dari salary slip tanpa menghitung ulang
        for deduction in slip.deductions:
            # Employee contributions
            if deduction.salary_component == "BPJS JHT Employee":
                bpjs_components["employee"]["jht"] = flt(deduction.amount)
            elif deduction.salary_component == "BPJS JP Employee":
                bpjs_components["employee"]["jp"] = flt(deduction.amount)
            elif deduction.salary_component == "BPJS Kesehatan Employee":
                bpjs_components["employee"]["kesehatan"] = flt(deduction.amount)
        
        # Check employer contributions in earnings (often added as non-taxable benefits)
        for earning in slip.earnings:
            # Employer contributions
            if earning.salary_component == "BPJS JHT Employer":
                bpjs_components["employer"]["jht"] = flt(earning.amount)
            elif earning.salary_component == "BPJS JP Employer":
                bpjs_components["employer"]["jp"] = flt(earning.amount)
            elif earning.salary_component == "BPJS Kesehatan Employer":
                bpjs_components["employer"]["kesehatan"] = flt(earning.amount)
            elif earning.salary_component == "BPJS JKK":
                bpjs_components["employer"]["jkk"] = flt(earning.amount)
            elif earning.salary_component == "BPJS JKM":
                bpjs_components["employer"]["jkm"] = flt(earning.amount)
        
        # If no BPJS components found, no need to continue
        if not any(bpjs_components["employee"].values()) and not any(bpjs_components["employer"].values()):
            debug_log(f"No BPJS components found in salary slip {salary_slip}")
            return None
        
        # Get the period
        month = getdate(slip.end_date).month
        year = getdate(slip.end_date).year
        
        debug_log(f"Processing BPJS for company={slip.company}, year={year}, month={month}")
        
        # Check if a BPJS Payment Summary already exists for this period
        bpjs_summary_name = frappe.db.get_value(
            "BPJS Payment Summary",
            {"company": slip.company, "year": year, "month": month, "docstatus": ["!=", 2]},
            "name"
        )
        
        if bpjs_summary_name:
            debug_log(f"Found existing BPJS Payment Summary: {bpjs_summary_name}")
            bpjs_summary = frappe.get_doc("BPJS Payment Summary", bpjs_summary_name)
            
            # Check if already submitted
            if bpjs_summary.docstatus > 0:
                debug_log(f"BPJS Payment Summary {bpjs_summary_name} already submitted, creating a new one")
                bpjs_summary = create_new_bpjs_summary(slip, month, year)
            
        else:
            debug_log(f"Creating new BPJS Payment Summary for {slip.company}, {year}, {month}")
            bpjs_summary = create_new_bpjs_summary(slip, month, year)
        
        # Check if employee is already in the summary
        employee_exists = False
        for employee_detail in bpjs_summary.employee_details:
            if employee_detail.employee == slip.employee and employee_detail.salary_slip == salary_slip:
                debug_log(f"Employee {slip.employee} already exists in BPJS Payment Summary {bpjs_summary.name}, updating")
                update_employee_bpjs_details(employee_detail, slip, bpjs_components)
                employee_exists = True
                break
        
        # If employee doesn't exist, add them
        if not employee_exists:
            debug_log(f"Adding employee {slip.employee} to BPJS Payment Summary {bpjs_summary.name}")
            add_employee_to_bpjs_summary(bpjs_summary, slip, bpjs_components)
        
        # Calculate totals
        recalculate_bpjs_totals(bpjs_summary)
        
        # Save the document
        bpjs_summary.flags.ignore_permissions = True
        bpjs_summary.save()
        debug_log(f"Successfully saved BPJS Payment Summary: {bpjs_summary.name}")
        
        # Create BPJS Payment Component if setting is enabled
        try:
            bpjs_settings = frappe.get_single("BPJS Settings")
            if hasattr(bpjs_settings, 'auto_create_component') and bpjs_settings.auto_create_component:
                debug_log(f"Auto-creating BPJS payment component for {salary_slip}")
                frappe.enqueue(
                    method="payroll_indonesia.doctype.bpjs_payment_component.bpjs_payment_component.create_from_salary_slip",
                    queue="short",
                    timeout=300,
                    is_async=True,
                    **{"salary_slip": salary_slip, "bpjs_summary": bpjs_summary.name}
                )
        except Exception as e:
            debug_log(f"Error checking BPJS settings: {str(e)}")
        
        return bpjs_summary.name
        
    except Exception as e:
        debug_log(f"Error in create_from_salary_slip: {str(e)}\nTraceback: {frappe.get_traceback()}")
        frappe.log_error(
            f"Error creating BPJS Payment Summary from {salary_slip}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Payment Summary Error"
        )
        return None

def create_new_bpjs_summary(slip, month, year):
    """Create a new BPJS Payment Summary"""
    debug_log(f"Creating new BPJS Payment Summary for {slip.company}, {month}/{year}")
    
    bpjs_summary = frappe.new_doc("BPJS Payment Summary")
    bpjs_summary.company = slip.company
    bpjs_summary.month = month
    bpjs_summary.year = year
    bpjs_summary.posting_date = today()
    
    # Get company details
    company_doc = frappe.get_doc("Company", slip.company)
    if company_doc:
        # Set company details like BPJS registration numbers if available
        for field in ['bpjs_company_registration', 'npwp', 'bpjs_branch_office']:
            if hasattr(company_doc, field):
                setattr(bpjs_summary, field, getattr(company_doc, field))
    
    # Initialize employee details and totals
    bpjs_summary.employee_details = []
    bpjs_summary.komponen = []
    
    return bpjs_summary

def add_employee_to_bpjs_summary(bpjs_summary, slip, bpjs_components):
    """Add an employee to BPJS Payment Summary"""
    debug_log(f"Adding employee {slip.employee} to BPJS Payment Summary {bpjs_summary.name}")
    
    employee = frappe.get_doc("Employee", slip.employee)
    
    # Create new employee detail
    employee_detail = {
        "employee": slip.employee,
        "employee_name": slip.employee_name,
        "salary_slip": slip.name,
        "department": getattr(employee, "department", ""),
        "designation": getattr(employee, "designation", ""),
        "bpjs_number": getattr(employee, "bpjs_number", ""),
        "nik": getattr(employee, "ktp", ""),
        "jht_employee": bpjs_components["employee"].get("jht", 0),
        "jp_employee": bpjs_components["employee"].get("jp", 0),
        "kesehatan_employee": bpjs_components["employee"].get("kesehatan", 0),
        "jht_employer": bpjs_components["employer"].get("jht", 0),
        "jp_employer": bpjs_components["employer"].get("jp", 0),
        "jkk": bpjs_components["employer"].get("jkk", 0),
        "jkm": bpjs_components["employer"].get("jkm", 0),
        "kesehatan_employer": bpjs_components["employer"].get("kesehatan", 0)
    }
    
    # Add to the employee_details child table
    bpjs_summary.append("employee_details", employee_detail)
    
    debug_log(f"Successfully added employee {slip.employee} to BPJS Payment Summary")

def update_employee_bpjs_details(employee_detail, slip, bpjs_components):
    """Update an employee's BPJS details"""
    debug_log(f"Updating BPJS details for employee {slip.employee}")
    
    # Update employee information
    employee_detail.employee_name = slip.employee_name
    employee_detail.salary_slip = slip.name
    
    # Update component amounts
    employee_detail.jht_employee = bpjs_components["employee"].get("jht", 0)
    employee_detail.jp_employee = bpjs_components["employee"].get("jp", 0)
    employee_detail.kesehatan_employee = bpjs_components["employee"].get("kesehatan", 0)
    employee_detail.jht_employer = bpjs_components["employer"].get("jht", 0)
    employee_detail.jp_employer = bpjs_components["employer"].get("jp", 0)
    employee_detail.jkk = bpjs_components["employer"].get("jkk", 0)
    employee_detail.jkm = bpjs_components["employer"].get("jkm", 0)
    employee_detail.kesehatan_employer = bpjs_components["employer"].get("kesehatan", 0)
    
    debug_log(f"Successfully updated BPJS details for employee {slip.employee}")

def recalculate_bpjs_totals(bpjs_summary):
    """Recalculate BPJS Payment Summary totals"""
    debug_log(f"Recalculating totals for BPJS Payment Summary {bpjs_summary.name}")
    
    # Calculate totals
    jht_total = 0
    jp_total = 0
    kesehatan_total = 0
    jkk_total = 0
    jkm_total = 0
    
    for emp in bpjs_summary.employee_details:
        jht_total += flt(emp.jht_employee) + flt(emp.jht_employer)
        jp_total += flt(emp.jp_employee) + flt(emp.jp_employer)
        kesehatan_total += flt(emp.kesehatan_employee) + flt(emp.kesehatan_employer)
        jkk_total += flt(emp.jkk)
        jkm_total += flt(emp.jkm)
    
    # Clear existing components
    bpjs_summary.komponen = []
    
    # Add components
    if jht_total > 0:
        bpjs_summary.append("komponen", {
            "component": "BPJS JHT",
            "description": "JHT Contribution (Employee + Employer)",
            "amount": jht_total
        })
    
    if jp_total > 0:
        bpjs_summary.append("komponen", {
            "component": "BPJS JP",
            "description": "JP Contribution (Employee + Employer)",
            "amount": jp_total
        })
    
    if kesehatan_total > 0:
        bpjs_summary.append("komponen", {
            "component": "BPJS Kesehatan",
            "description": "Kesehatan Contribution (Employee + Employer)",
            "amount": kesehatan_total
        })
    
    if jkk_total > 0:
        bpjs_summary.append("komponen", {
            "component": "BPJS JKK",
            "description": "JKK Contribution (Employer)",
            "amount": jkk_total
        })
    
    if jkm_total > 0:
        bpjs_summary.append("komponen", {
            "component": "BPJS JKM",
            "description": "JKM Contribution (Employer)",
            "amount": jkm_total
        })
    
    # Calculate grand total
    bpjs_summary.total = jht_total + jp_total + kesehatan_total + jkk_total + jkm_total
    
    debug_log(f"Successfully recalculated totals for BPJS Payment Summary {bpjs_summary.name}")

@frappe.whitelist()
def update_on_salary_slip_cancel(salary_slip, month, year):
    """
    Update BPJS Payment Summary when a Salary Slip is cancelled
    Called asynchronously from the Salary Slip's on_cancel method
    """
    debug_log(f"Starting update_on_salary_slip_cancel for {salary_slip}, month={month}, year={year}")
    
    try:
        # Get the salary slip document
        slip = frappe.get_doc("Salary Slip", salary_slip)
        if not slip:
            debug_log(f"Salary slip {salary_slip} not found")
            return False
            
        # Find the BPJS Payment Summary
        bpjs_summary_name = frappe.db.get_value(
            "BPJS Payment Summary",
            {"company": slip.company, "year": year, "month": month, "docstatus": ["!=", 2]},
            "name"
        )
        
        if not bpjs_summary_name:
            debug_log(f"No BPJS Payment Summary found for company={slip.company}, month={month}, year={year}")
            return False
            
        # Get the document
        bpjs_doc = frappe.get_doc("BPJS Payment Summary", bpjs_summary_name)
        
        # Check if already submitted
        if bpjs_doc.docstatus > 0:
            debug_log(f"BPJS Payment Summary {bpjs_summary_name} already submitted, cannot update")
            frappe.msgprint(_("BPJS Payment Summary {0} sudah disubmit dan tidak dapat diperbarui.").format(bpjs_summary_name))
            return False
            
        # Find and remove the employee entry
        to_remove = []
        for i, d in enumerate(bpjs_doc.employee_details):
            if getattr(d, "salary_slip") == salary_slip:
                debug_log(f"Found entry to remove: employee_details[{i}] with salary_slip={salary_slip}")
                to_remove.append(d)
                
        # If entries found, remove them and save
        if to_remove:
            debug_log(f"Found {len(to_remove)} entries to remove from BPJS Payment Summary {bpjs_summary_name}")
            
            for d in to_remove:
                bpjs_doc.employee_details.remove(d)
                
            # Recalculate totals
            recalculate_bpjs_totals(bpjs_doc)
            
            # Save the document
            bpjs_doc.flags.ignore_permissions = True
            bpjs_doc.save()
            debug_log(f"Successfully updated BPJS Payment Summary: {bpjs_summary_name}")
            
            return True
        else:
            debug_log(f"No entries found for salary_slip={salary_slip} in BPJS Payment Summary {bpjs_summary_name}")
            return False
            
    except Exception as e:
        debug_log(f"Error in update_on_salary_slip_cancel: {str(e)}\nTraceback: {frappe.get_traceback()}")
        frappe.log_error(
            f"Error updating BPJS Payment Summary on cancel for {salary_slip}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Payment Summary Cancel Error"
        )
        return False
