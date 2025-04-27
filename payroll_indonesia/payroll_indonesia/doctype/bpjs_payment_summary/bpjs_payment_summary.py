# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 10:32:35 by dannyaudian

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, flt, fmt_money, getdate

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

    @frappe.whitelist()
    def populate_employee_details(self):
        """Populate employee details with active employees who have BPJS participation"""
        if self.docstatus == 1:
            frappe.throw(_("Cannot modify employee details after submission"))
        
        # Clear existing employee details
        self.employee_details = []
    
        # Get BPJS Settings
        bpjs_settings = frappe.get_single("BPJS Settings")
    
        # Get active employees
        employees = frappe.get_all(
            "Employee",
            filters={
                "status": "Active", 
                "company": self.company
         },
            fields=["name", "employee_name"]
        )
    
        # Get the payroll period for the selected month and year
        first_day = f"{self.year}-{self.month:02d}-01"
        if self.month == 12:
            last_day = f"{self.year + 1}-01-01"
        else:
            last_day = f"{self.year}-{self.month + 1:02d}-01"
    
        last_day = frappe.utils.add_days(last_day, -1)
    
        employee_count = 0
    
        for emp in employees:
            # Get latest salary structure assignment
            salary_structure_assignment = frappe.db.get_value(
                "Salary Structure Assignment",
                {
                    "employee": emp.name,
                    "docstatus": 1,
                    "from_date": ["<=", last_day]
                },
                ["name", "salary_structure", "base"],
                order_by="from_date desc"
            )
        
            if not salary_structure_assignment:
                continue
            
            # Check if employee is registered for BPJS
            is_bpjs_participant = frappe.db.get_value(
                "Employee", emp.name, "bpjs_participant"
            ) if frappe.db.has_column("Employee", "bpjs_participant") else 1
        
            if not is_bpjs_participant:
                continue
            
            # Get base salary
            base_salary = salary_structure_assignment[2] if salary_structure_assignment[2] else 0
        
            if base_salary <= 0:
                continue
            
            # Calculate BPJS contributions
            # JHT (2% employee, 3.7% employer)
            jht_employee = base_salary * (bpjs_settings.jht_employee_percent / 100)
            jht_employer = base_salary * (bpjs_settings.jht_employer_percent / 100)
        
            # JP (1% employee, 2% employer) with salary cap
            jp_base = min(base_salary, bpjs_settings.jp_max_salary)
            jp_employee = jp_base * (bpjs_settings.jp_employee_percent / 100)
            jp_employer = jp_base * (bpjs_settings.jp_employer_percent / 100)
        
            # Kesehatan (1% employee, 4% employer) with salary cap
            kesehatan_base = min(base_salary, bpjs_settings.kesehatan_max_salary)
            kesehatan_employee = kesehatan_base * (bpjs_settings.kesehatan_employee_percent / 100)
            kesehatan_employer = kesehatan_base * (bpjs_settings.kesehatan_employer_percent / 100)
        
            # JKK (0.24% - 1.74% of base salary)
            jkk = base_salary * (bpjs_settings.jkk_percent / 100)
        
            # JKM (0.3% of base salary)
            jkm = base_salary * (bpjs_settings.jkm_percent / 100)
        
            # Add employee to details
            self.append("employee_details", {
                "employee": emp.name,
                "employee_name": emp.employee_name,
                "jht_employee": jht_employee,
                "jp_employee": jp_employee,
                "kesehatan_employee": kesehatan_employee,
                "jht_employer": jht_employer,
                "jp_employer": jp_employer,
                "kesehatan_employer": kesehatan_employer,
                "jkk": jkk,
                "jkm": jkm
            })
        
            employee_count += 1
    
        if employee_count == 0:
            frappe.msgprint(_("No eligible employees found with BPJS participation."))
        else:
            # Update components based on employee details
            self.update_components_from_employee_details()
            frappe.msgprint(_("Added {0} employees to BPJS Payment Summary.").format(employee_count))

    def update_components_from_employee_details(self):
        """Update component table based on employee details"""
        if not self.employee_details:
            return
        
        # Calculate totals
        jht_total = 0
        jp_total = 0
        kesehatan_total = 0
        jkk_total = 0
        jkm_total = 0
    
        for emp in self.employee_details:
            jht_total += flt(emp.jht_employee) + flt(emp.jht_employer)
            jp_total += flt(emp.jp_employee) + flt(emp.jp_employer)
            kesehatan_total += flt(emp.kesehatan_employee) + flt(emp.kesehatan_employer)
            jkk_total += flt(emp.jkk)
            jkm_total += flt(emp.jkm)
    
        # Clear existing components
        self.komponen = []
    
        # Add JHT component
        if jht_total > 0:
            self.append("komponen", {
                "component": "BPJS JHT",
                "description": "JHT Contribution (Employee + Employer)",
                "amount": jht_total
            })
    
        # Add JP component
        if jp_total > 0:
            self.append("komponen", {
                "component": "BPJS JP",
                "description": "JP Contribution (Employee + Employer)",
                "amount": jp_total
            })
    
        # Add Kesehatan component
        if kesehatan_total > 0:
            self.append("komponen", {
                "component": "BPJS Kesehatan",
                "description": "Kesehatan Contribution (Employee + Employer)",
                "amount": kesehatan_total
            })
    
        # Add JKK component
        if jkk_total > 0:
            self.append("komponen", {
                "component": "BPJS JKK",
                "description": "JKK Contribution (Employer)",
                "amount": jkk_total
            })
    
        # Add JKM component
        if jkm_total > 0:
            self.append("komponen", {
                "component": "BPJS JKM",
                "description": "JKM Contribution (Employer)",
                "amount": jkm_total
            })