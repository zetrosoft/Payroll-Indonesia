# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-28 02:25:00 by dannyaudian

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, flt, fmt_money, getdate, now_datetime

# Debug function for error tracking
def debug_log(message, module_name="PPh TER Table"):
    """Log debug message with timestamp and additional info"""
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    frappe.log_error(f"[{timestamp}] {message}", module_name)

def get_formatted_currency(value, company=None):
    """Format currency value based on company settings"""
    if company:
        currency = frappe.get_cached_value('Company', company, 'default_currency')
    else:
        currency = frappe.db.get_default("currency")
    return fmt_money(value, currency=currency)

class PPhTERTable(Document):
    def validate(self):
        self.validate_company()
        self.validate_details()
        self.calculate_total()
        self.validate_total()
        self.sync_month_period()
    
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
    
    def validate_details(self):
        """Validate PPh TER details"""
        if not self.details:
            frappe.throw(_("At least one employee record is required for PPh TER"))
            
        for d in self.details:
            if not d.amount or d.amount <= 0:
                frappe.throw(_("PPh amount must be greater than 0 for employee {0}").format(d.employee_name))
    
    def calculate_total(self):
        """Calculate total from details"""
        self.total = sum(flt(d.amount) for d in self.details)
    
    def validate_total(self):
        """Validate total amount is greater than 0"""
        if not self.total or self.total <= 0:
            frappe.throw(_("Total amount must be greater than 0"))
    
    def sync_month_period(self):
        """Sync month and period fields, update month_year_title"""
        period_to_month = {
            "January": 1, "February": 2, "March": 3, "April": 4,
            "May": 5, "June": 6, "July": 7, "August": 8,
            "September": 9, "October": 10, "November": 11, "December": 12
        }
        
        month_to_period = {v: k for k, v in period_to_month.items()}
        
        # Sync fields
        if self.period and (not self.month or self.month <= 0 or self.month > 12):
            self.month = period_to_month.get(self.period, 0)
        elif self.month and not self.period and 1 <= self.month <= 12:
            self.period = month_to_period.get(self.month, "")
        
        # Update title
        if self.period and self.year:
            self.month_year_title = f"{self.period} {self.year}"
    
    def on_submit(self):
        """Set status to Submitted"""
        self.status = "Submitted"
    
    def on_cancel(self):
        """Reset status to Draft"""
        if self.payment_entry:
            pe_status = frappe.db.get_value("Payment Entry", self.payment_entry, "docstatus")
            if pe_status and int(pe_status) == 1:
                frappe.throw(_("Cannot cancel document with submitted Payment Entry"))
        self.status = "Draft"
    
    @frappe.whitelist()
    def generate_payment_entry(self):
        """Generate Payment Entry for PPh TER payment to tax office"""
        if self.payment_entry:
            frappe.throw(_("Payment Entry already exists"))
            
        if self.docstatus != 1:
            frappe.throw(_("Document must be submitted first"))
            
        try:
            # Create payment entry
            pe = frappe.new_doc("Payment Entry")
            pe.payment_type = "Pay"
            pe.party_type = "Supplier"
            pe.party = "Kantor Pajak"  # Tax Office
            pe.posting_date = today()
            pe.paid_amount = self.total
            pe.received_amount = self.total
            
            # Set company and accounts
            pe.company = self.company
            pe.paid_from = frappe.get_cached_value('Company', self.company, 'default_bank_account')
            pe.paid_to = frappe.get_cached_value('Company', self.company, 'default_payable_account')
            
            # Set references
            pe.reference_doctype = self.doctype
            pe.reference_name = self.name
            
            # Add custom remarks with period
            period_text = f"{self.period} {self.year}"
            pe.remarks = (
                f"PPh 21 Payment for {period_text}\n"
                f"Total Amount: {get_formatted_currency(self.total, pe.company)}"
            )
            
            # Save and submit
            pe.insert()
            pe.submit()
            
            # Update this document
            self.db_set('payment_entry', pe.name)
            self.db_set('status', 'Paid')
            
            return pe.name
            
        except Exception as e:
            frappe.msgprint(_("Error creating Payment Entry"))
            frappe.throw(str(e))

# ----- Fungsi tambahan untuk integrasi dengan Salary Slip -----

@frappe.whitelist()
def create_from_salary_slip(salary_slip):
    """
    Create or update PPh TER Table from a Salary Slip
    Called asynchronously from the Salary Slip's on_submit method
    """
    debug_log(f"Starting create_from_salary_slip for {salary_slip}")
    
    try:
        # Get the salary slip document
        slip = frappe.get_doc("Salary Slip", salary_slip)
        if not slip or slip.docstatus != 1:
            debug_log(f"Salary slip {salary_slip} not found or not submitted")
            return None
            
        # Check if this slip is using TER
        is_using_ter = getattr(slip, 'is_using_ter', 0)
        if not is_using_ter:
            debug_log(f"Salary slip {salary_slip} is not using TER method, skipping")
            return None
            
        # Get TER rate
        ter_rate = getattr(slip, 'ter_rate', 0)
        if not ter_rate:
            debug_log(f"No TER rate found in salary slip {salary_slip}, skipping")
            return None
            
        # Get the period
        month = getdate(slip.end_date).month
        year = getdate(slip.end_date).year
        
        # Get PPh 21 amount from salary slip
        pph21_amount = 0
        for deduction in slip.deductions:
            if deduction.salary_component == "PPh 21":
                pph21_amount = flt(deduction.amount)
                break
        
        debug_log(f"Processing PPh TER for company={slip.company}, year={year}, month={month}, rate={ter_rate}")
        debug_log(f"PPh 21 amount: {pph21_amount}")
        
        # Check if a PPh TER Table already exists for this period
        ter_table_name = frappe.db.get_value(
            "PPh TER Table",
            {"company": slip.company, "year": year, "month": month, "docstatus": ["!=", 2]},
            "name"
        )
        
        if ter_table_name:
            debug_log(f"Found existing PPh TER Table: {ter_table_name}")
            ter_table = frappe.get_doc("PPh TER Table", ter_table_name)
            
            # Check if already submitted
            if ter_table.docstatus > 0:
                debug_log(f"PPh TER Table {ter_table_name} already submitted, creating a new one")
                ter_table = create_new_ter_table(slip, month, year, ter_rate)
            
        else:
            debug_log(f"Creating new PPh TER Table for {slip.company}, {year}, {month}")
            ter_table = create_new_ter_table(slip, month, year, ter_rate)
        
        # Check if employee is already in the table
        employee_exists = False
        for detail in ter_table.details:
            if detail.employee == slip.employee:
                debug_log(f"Employee {slip.employee} already exists in PPh TER Table {ter_table.name}, updating")
                update_employee_ter_details(detail, slip, pph21_amount)
                employee_exists = True
                break
        
        # If employee doesn't exist, add them
        if not employee_exists:
            debug_log(f"Adding employee {slip.employee} to PPh TER Table {ter_table.name}")
            add_employee_to_ter_table(ter_table, slip, pph21_amount)
        
        # Save the document
        ter_table.flags.ignore_permissions = True
        ter_table.calculate_total()
        ter_table.save()
        debug_log(f"Successfully saved PPh TER Table: {ter_table.name}")
        
        return ter_table.name
        
    except Exception as e:
        debug_log(f"Error in create_from_salary_slip: {str(e)}\nTraceback: {frappe.get_traceback()}")
        frappe.log_error(
            f"Error creating PPh TER Table from {salary_slip}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "PPh TER Table Error"
        )
        return None

def create_new_ter_table(slip, month, year, ter_rate):
    """Create a new PPh TER Table"""
    debug_log(f"Creating new PPh TER Table for {slip.company}, {month}/{year}")
    
    # Create the document
    ter_table = frappe.new_doc("PPh TER Table")
    ter_table.company = slip.company
    ter_table.month = month
    ter_table.year = year
    ter_table.ter_rate = ter_rate
    
    # Set period field if month is valid
    month_to_period = {
        1: "January", 2: "February", 3: "March", 4: "April",
        5: "May", 6: "June", 7: "July", 8: "August",
        9: "September", 10: "October", 11: "November", 12: "December"
    }
    
    if month in month_to_period:
        ter_table.period = month_to_period[month]
    
    # Set title
    if month in month_to_period:
        ter_table.month_year_title = f"{month_to_period[month]} {year}"
    else:
        ter_table.month_year_title = f"{month}-{year}"
    
    # Initialize fields
    ter_table.details = []
    ter_table.total = 0
    ter_table.status = "Draft"
    
    return ter_table

def add_employee_to_ter_table(ter_table, slip, pph21_amount):
    """Add an employee to PPh TER Table"""
    debug_log(f"Adding employee {slip.employee} to PPh TER Table {ter_table.name}")
    
    # Get values from salary slip
    biaya_jabatan = getattr(slip, 'biaya_jabatan', 0)
    netto = getattr(slip, 'netto', slip.gross_pay)
    
    # Create new detail
    detail = {
        "employee": slip.employee,
        "employee_name": slip.employee_name,
        "npwp": getattr(slip, 'npwp', ""),
        "ktp": getattr(slip, 'ktp', ""),
        "biaya_jabatan": biaya_jabatan,
        "penghasilan_bruto": slip.gross_pay,
        "penghasilan_netto": netto,
        "penghasilan_kena_pajak": netto,
        "amount": pph21_amount,
        "ter_rate": getattr(slip, 'ter_rate', 0)
    }
    
    # Add to the details child table
    ter_table.append("details", detail)
    
    debug_log(f"Successfully added employee {slip.employee} to PPh TER Table")

def update_employee_ter_details(detail, slip, pph21_amount):
    """Update an employee's TER details"""
    debug_log(f"Updating TER details for employee {slip.employee}")
    
    # Get values from salary slip
    biaya_jabatan = getattr(slip, 'biaya_jabatan', 0)
    netto = getattr(slip, 'netto', slip.gross_pay)
    
    # Update details
    detail.employee_name = slip.employee_name
    detail.npwp = getattr(slip, 'npwp', detail.npwp)
    detail.ktp = getattr(slip, 'ktp', detail.ktp)
    detail.biaya_jabatan = biaya_jabatan
    detail.penghasilan_bruto = slip.gross_pay
    detail.penghasilan_netto = netto
    detail.penghasilan_kena_pajak = netto
    detail.amount = pph21_amount
    detail.ter_rate = getattr(slip, 'ter_rate', detail.ter_rate)
    
    debug_log(f"Successfully updated TER details for employee {slip.employee}")

@frappe.whitelist()
def update_on_salary_slip_cancel(salary_slip, month, year):
    """
    Update PPh TER Table when a Salary Slip is cancelled
    Called asynchronously from the Salary Slip's on_cancel method
    """
    debug_log(f"Starting update_on_salary_slip_cancel for {salary_slip}, month={month}, year={year}")
    
    try:
        # Get the salary slip document
        slip = frappe.get_doc("Salary Slip", salary_slip)
        if not slip:
            debug_log(f"Salary slip {salary_slip} not found")
            return False
            
        # Only continue if using TER
        is_using_ter = getattr(slip, 'is_using_ter', 0)
        if not is_using_ter:
            debug_log(f"Salary slip {salary_slip} not using TER, skipping update_on_salary_slip_cancel")
            return False
            
        # Find the PPh TER Table
        ter_table_name = frappe.db.get_value(
            "PPh TER Table",
            {"company": slip.company, "year": year, "month": month, "docstatus": ["!=", 2]},
            "name"
        )
        
        if not ter_table_name:
            debug_log(f"No PPh TER Table found for company={slip.company}, month={month}, year={year}")
            return False
            
        # Get the document
        ter_doc = frappe.get_doc("PPh TER Table", ter_table_name)
        
        # Check if already submitted
        if ter_doc.docstatus > 0:
            debug_log(f"PPh TER Table {ter_table_name} already submitted, cannot update")
            frappe.msgprint(_("PPh TER Table {0} already submitted, cannot update.").format(ter_table_name))
            return False
            
        # Find and remove the employee entry
        to_remove = []
        for i, d in enumerate(ter_doc.details):
            if d.employee == slip.employee:
                debug_log(f"Found entry to remove: details[{i}] with employee={slip.employee}")
                to_remove.append(d)
                
        # If entries found, remove them and save
        if to_remove:
            debug_log(f"Found {len(to_remove)} entries to remove from PPh TER Table {ter_table_name}")
            
            for d in to_remove:
                ter_doc.details.remove(d)
                
            # Save the document
            ter_doc.flags.ignore_permissions = True
            ter_doc.calculate_total()
            ter_doc.save()
            debug_log(f"Successfully updated PPh TER Table: {ter_table_name}")
            
            return True
        else:
            debug_log(f"No entries found for employee={slip.employee} in PPh TER Table {ter_table_name}")
            return False
            
    except Exception as e:
        debug_log(f"Error in update_on_salary_slip_cancel: {str(e)}\nTraceback: {frappe.get_traceback()}")
        frappe.log_error(
            f"Error updating PPh TER Table on cancel for {salary_slip}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "PPh TER Table Cancel Error"
        )
        return False
