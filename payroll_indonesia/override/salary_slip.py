# -*- coding: utf-8 -*-
# Copyright (c) 2025, Danny Audian and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, money_in_words, cint
from erpnext.payroll.doctype.salary_slip.salary_slip import SalarySlip

class CustomSalarySlip(SalarySlip):
    def validate(self):
        super().validate()
        self.validate_required_components()
    
    def validate_required_components(self):
        """Validate existence of required salary components"""
        required_components = [
            "Gaji Pokok",
            "BPJS JHT Employee",
            "BPJS JP Employee", 
            "BPJS Kesehatan Employee",
            "PPh 21"
        ]
        
        for component in required_components:
            if not frappe.db.exists("Salary Component", component):
                frappe.throw(_("Required salary component {0} not found").format(component))
    
    def calculate_component_amounts(self):
        """Calculate salary components with Indonesian payroll rules"""
        # Call standard ERPNext calculation first
        super().calculate_component_amounts()
        
        try:
            # Additional Indonesian calculations
            self.calculate_indonesia_payroll()
            
        except Exception as e:
            frappe.log_error(
                "Salary Slip Calculation Error",
                f"Employee: {self.employee}\nError: {str(e)}"
            )
            frappe.throw(_("Error in salary calculation: {0}").format(str(e)))
    
    def calculate_indonesia_payroll(self):
        """Handle Indonesian specific payroll calculations"""
        # Get basic salary (Gaji Pokok)
        gaji_pokok = 0
        for earning in self.earnings:
            if earning.salary_component == "Gaji Pokok":
                gaji_pokok = earning.amount
                break
        
        if not gaji_pokok:
            frappe.msgprint(_("Warning: No Gaji Pokok found"))
            return
        
        # Get employee details
        employee = frappe.get_doc("Employee", self.employee)
        
        # Calculate BPJS components
        self.calculate_bpjs_components(employee, gaji_pokok)
        
        # Calculate tax components
        self.calculate_tax_components(employee)
        
        # Update totals
        self.update_totals()
    
    def calculate_bpjs_components(self, employee, gaji_pokok):
        """Calculate and update BPJS components"""
        from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import hitung_bpjs
        
        bpjs_result = hitung_bpjs(employee, gaji_pokok)
        
        # Update BPJS components
        self.update_deduction("BPJS JHT Employee", bpjs_result.get("jht_employee", 0))
        self.update_deduction("BPJS JP Employee", bpjs_result.get("jp_employee", 0))
        self.update_deduction("BPJS Kesehatan Employee", bpjs_result.get("kesehatan_employee", 0))
        
        # Store total BPJS for tax calculation
        self.total_bpjs = sum([
            bpjs_result.get("jht_employee", 0),
            bpjs_result.get("jp_employee", 0),
            bpjs_result.get("kesehatan_employee", 0)
        ])
    
    def calculate_tax_components(self, employee):
        """Calculate tax related components"""
        # Skip tax calculation for married women using husband's NPWP
        if employee.gender == "Female" and cint(employee.get("npwp_gabung_suami")):
            self.flags.is_tax_final = True
            return
        
        # Calculate Biaya Jabatan (5% of gross, max 500k)
        self.biaya_jabatan = min(self.gross_pay * 0.05, 500000)
        
        # Calculate netto income
        self.netto = self.gross_pay - self.biaya_jabatan - self.total_bpjs
        
        # Calculate PPh 21
        if self.is_december():
            self.calculate_december_pph(employee)
        else:
            self.calculate_monthly_pph(employee)
    
    def calculate_monthly_pph(self, employee):
        """Calculate PPh 21 using TER method for regular months"""
        # Get TER rate from PPh TER Table
        ter_rate = frappe.get_value(
            "PPh TER Table",
            {
                "status_pajak": employee.status_pajak,
                "from_amount": ["<=", self.netto],
                "to_amount": [">", self.netto]
            },
            "ter_rate"
        )
        
        if not ter_rate:
            frappe.throw(_("TER rate not found for status {0} and amount {1}")
                        .format(employee.status_pajak, self.netto))
        
        pph21 = self.netto * (ter_rate / 100)
        self.update_deduction("PPh 21", pph21)
    
    def calculate_december_pph(self, employee):
        """Calculate year-end tax correction for December"""
        year = getdate(self.end_date).year
        
        # Get year-to-date totals (Jan-Nov)
        ytd = self.get_ytd_totals(year)
        
        # Add current month
        annual_gross = ytd.gross + self.gross_pay
        annual_bpjs = ytd.bpjs + self.total_bpjs
        annual_biaya_jabatan = min(annual_gross * 0.05, 500000)
        
        # Calculate annual netto
        annual_netto = annual_gross - annual_bpjs - annual_biaya_jabatan
        
        # Get PTKP value
        from payroll_indonesia.payroll_indonesia.utils import get_ptkp_value
        ptkp = get_ptkp_value(employee.status_pajak)
        
        # Calculate PKP
        pkp = max(annual_netto - ptkp, 0)
        
        # Calculate annual PPh using progressive rates
        tax_brackets = [
            (0, 50_000_000, 0.05),
            (50_000_000, 250_000_000, 0.15),
            (250_000_000, 500_000_000, 0.25),
            (500_000_000, float('inf'), 0.35)
        ]
        
        annual_pph = 0
        remaining_pkp = pkp
        
        for lower, upper, rate in tax_brackets:
            if remaining_pkp <= 0:
                break
            
            taxable = min(remaining_pkp, upper - lower)
            annual_pph += taxable * rate
            remaining_pkp -= taxable
        
        # Calculate correction
        correction = annual_pph - ytd.pph21
        
        # Update December PPh 21
        self.update_deduction(
            "PPh 21",
            correction,
            f"Koreksi Desember: PPh {annual_pph:,.0f} - Dibayar {ytd.pph21:,.0f}"
        )
    
    def get_ytd_totals(self, year):
        """Get year-to-date totals for tax calculation"""
        ytd = frappe.db.sql("""
            SELECT 
                SUM(gross_pay) as gross,
                SUM(total_bpjs) as bpjs,
                SUM(
                    CASE 
                        WHEN salary_component = 'PPh 21'
                        THEN amount 
                        ELSE 0 
                    END
                ) as pph21
            FROM `tabSalary Slip` ss
            LEFT JOIN `tabSalary Detail` sd ON sd.parent = ss.name
            WHERE ss.employee = %s
            AND ss.docstatus = 1
            AND YEAR(ss.start_date) = %s
            AND ss.start_date < %s
        """, (self.employee, year, self.start_date), as_dict=1)[0]
        
        return frappe._dict({
            "gross": flt(ytd.gross),
            "bpjs": flt(ytd.bpjs),
            "pph21": flt(ytd.pph21)
        })
    
    def update_deduction(self, component_name, amount, description=None):
        """Update or add deduction component"""
        for d in self.deductions:
            if d.salary_component == component_name:
                d.amount = flt(amount)
                if description:
                    d.additional_salary = description
                return
        
        # Component doesn't exist, create new
        component = frappe.get_doc("Salary Component", component_name)
        self.append("deductions", {
            "salary_component": component_name,
            "amount": flt(amount),
            "default_amount": flt(amount),
            "additional_salary": description,
            "is_tax_applicable": component.is_tax_applicable,
            "is_flexible_benefit": component.is_flexible_benefit,
            "exempted_from_income_tax": component.is_tax_exempted
        })
    
    def update_totals(self):
        """Update total fields"""
        self.total_deduction = sum(flt(d.amount) for d in self.deductions)
        self.net_pay = self.gross_pay - self.total_deduction
        self.rounded_total = round(self.net_pay)
        
        company_currency = frappe.get_cached_value('Company', self.company, 'default_currency')
        self.total_in_words = money_in_words(self.rounded_total, company_currency)
    
    def is_december(self):
        """Check if salary slip is for December"""
        return getdate(self.end_date).month == 12

    def validate(self):
    super().validate()
    self.validate_required_components()
    
    # Initialize custom fields
    self.is_final_gabung_suami = 0
    self.koreksi_pph21 = 0
    self.payroll_note = ""

def calculate_tax_components(self, employee):
    """Calculate tax related components"""
    # Handle NPWP Gabung Suami case
    if employee.gender == "Female" and cint(employee.get("npwp_gabung_suami")):
        self.is_final_gabung_suami = 1
        self.payroll_note = "Penghasilan istri digabung dengan NPWP suami"
        return
    
    # Calculate Biaya Jabatan (5% of gross, max 500k)
    self.biaya_jabatan = min(self.gross_pay * 0.05, 500000)
    
    # Calculate netto income
    self.netto = self.gross_pay - self.biaya_jabatan - self.total_bpjs
    
    # Set basic payroll note
    self.set_basic_payroll_note(employee)
    
    # Calculate PPh 21
    if self.is_december():
        self.calculate_december_pph(employee)
    else:
        self.calculate_monthly_pph(employee)

def set_basic_payroll_note(self, employee):
    """Set basic payroll note with component details"""
    note_parts = [
        f"Status Pajak: {employee.status_pajak}",
        f"Penghasilan Bruto: Rp {self.gross_pay:,.0f}",
        f"Biaya Jabatan: Rp {self.biaya_jabatan:,.0f}",
        f"BPJS (JHT+JP+Kesehatan): Rp {self.total_bpjs:,.0f}",
        f"Penghasilan Neto: Rp {self.netto:,.0f}"
    ]
    
    self.payroll_note = "\n".join(note_parts)

def calculate_december_pph(self, employee):
    """Calculate year-end tax correction for December"""
    year = getdate(self.end_date).year
    
    # Get year-to-date totals (Jan-Nov)
    ytd = self.get_ytd_totals(year)
    
    # Calculate annual totals
    annual_gross = ytd.gross + self.gross_pay
    annual_bpjs = ytd.bpjs + self.total_bpjs
    annual_biaya_jabatan = min(annual_gross * 0.05, 500000)
    annual_netto = annual_gross - annual_bpjs - annual_biaya_jabatan
    
    # Get PTKP value
    from payroll_indonesia.payroll_indonesia.utils import get_ptkp_value
    ptkp = get_ptkp_value(employee.status_pajak)
    pkp = max(annual_netto - ptkp, 0)
    
    # Calculate annual PPh
    tax_brackets = [
        (0, 50_000_000, 0.05),
        (50_000_000, 250_000_000, 0.15),
        (250_000_000, 500_000_000, 0.25),
        (500_000_000, float('inf'), 0.35)
    ]
    
    annual_pph = 0
    tax_details = []
    remaining_pkp = pkp
    
    for lower, upper, rate in tax_brackets:
        if remaining_pkp <= 0:
            break
            
        taxable = min(remaining_pkp, upper - lower)
        tax = taxable * rate
        annual_pph += tax
        
        if tax > 0:
            tax_details.append(
                f"- Lapisan {rate*100:.0f}%: "
                f"Rp {taxable:,.0f} × {rate*100:.0f}% = Rp {tax:,.0f}"
            )
        
        remaining_pkp -= taxable
    
    # Calculate correction
    correction = annual_pph - ytd.pph21
    self.koreksi_pph21 = correction
    
    # Update December PPh 21
    self.update_deduction(
        "PPh 21",
        correction,
        f"Koreksi PPh 21 Desember {year}"
    )
    
    # Set detailed December note
    note_parts = [
        "=== Perhitungan PPh 21 Tahunan ===",
        f"Penghasilan Bruto Setahun: Rp {annual_gross:,.0f}",
        f"Biaya Jabatan: Rp {annual_biaya_jabatan:,.0f}",
        f"Total BPJS: Rp {annual_bpjs:,.0f}",
        f"Penghasilan Neto: Rp {annual_netto:,.0f}",
        f"PTKP ({employee.status_pajak}): Rp {ptkp:,.0f}",
        f"PKP: Rp {pkp:,.0f}",
        "",
        "Perhitungan Per Lapisan Pajak:",
        *tax_details,
        "",
        f"Total PPh 21 Setahun: Rp {annual_pph:,.0f}",
        f"PPh 21 Sudah Dibayar: Rp {ytd.pph21:,.0f}",
        f"Koreksi Desember: Rp {correction:,.0f}",
        f"({'Kurang Bayar' if correction > 0 else 'Lebih Bayar'})"
    ]
    
    self.payroll_note = "\n".join(note_parts)
