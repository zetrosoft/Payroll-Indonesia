# -*- coding: utf-8 -*-
# Copyright (c) 2025, Danny Audian and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, money_in_words, cint
from erpnext.payroll.doctype.salary_slip.salary_slip import SalarySlip

class CustomSalarySlip(SalarySlip):
    def validate(self):
        """Validate salary slip data"""
        super().validate()
        self.validate_required_components()
        self.initialize_custom_fields()
        
    def initialize_custom_fields(self):
        """Initialize custom fields with default values"""
        self.is_final_gabung_suami = 0
        self.koreksi_pph21 = 0
        self.payroll_note = ""
        self.biaya_jabatan = 0
        self.netto = 0
        self.total_bpjs = 0
    
    def validate_required_components(self):
        """Validate existence of required salary components"""
        required_components = {
            "earnings": ["Gaji Pokok"],
            "deductions": [
                "BPJS JHT Employee",
                "BPJS JP Employee", 
                "BPJS Kesehatan Employee",
                "PPh 21"
            ]
        }
        
        missing = []
        for component_type, components in required_components.items():
            for component in components:
                if not frappe.db.exists("Salary Component", component):
                    missing.append(component)
        
        if missing:
            frappe.throw(_(
                "Required salary components not found: {0}"
            ).format(", ".join(missing)))
    
    def calculate_component_amounts(self):
        """Calculate salary components with Indonesian payroll rules"""
        try:
            # Call standard ERPNext calculation first
            super().calculate_component_amounts()
            
            # Get basic salary (Gaji Pokok)
            gaji_pokok = self.get_component_amount("Gaji Pokok", "earnings")
            if not gaji_pokok:
                frappe.msgprint(_("Warning: 'Gaji Pokok' amount is zero"))
                return
            
            # Get employee details
            employee = frappe.get_doc("Employee", self.employee)
            
            # Calculate BPJS components
            self.calculate_bpjs_components(employee, gaji_pokok)
            
            # Calculate tax components
            self.calculate_tax_components(employee)
            
            # Update totals
            self.update_all_totals()
            
        except Exception as e:
            frappe.log_error(
                "Salary Slip Calculation Error",
                f"Employee: {self.employee}\nError: {str(e)}"
            )
            frappe.throw(_(
                "Error calculating salary components: {0}"
            ).format(str(e)))
    
    def calculate_bpjs_components(self, employee, gaji_pokok):
        """Calculate and update BPJS components"""
        from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import hitung_bpjs
        
        if not employee.ikut_bpjs_ketenagakerjaan and not employee.ikut_bpjs_kesehatan:
            return
        
        try:
            bpjs_result = hitung_bpjs(employee, gaji_pokok)
            
            # Update BPJS components
            if employee.ikut_bpjs_ketenagakerjaan:
                self.update_deduction(
                    "BPJS JHT Employee", 
                    bpjs_result.get("jht_employee", 0)
                )
                self.update_deduction(
                    "BPJS JP Employee",
                    bpjs_result.get("jp_employee", 0)
                )
            
            if employee.ikut_bpjs_kesehatan:
                self.update_deduction(
                    "BPJS Kesehatan Employee",
                    bpjs_result.get("kesehatan_employee", 0)
                )
            
            # Store total BPJS for tax calculation
            self.total_bpjs = sum([
                bpjs_result.get("jht_employee", 0),
                bpjs_result.get("jp_employee", 0),
                bpjs_result.get("kesehatan_employee", 0)
            ])
            
        except Exception as e:
            frappe.log_error(
                "BPJS Calculation Error",
                f"Employee: {employee.name}\nError: {str(e)}"
            )
            raise
    
    def calculate_tax_components(self, employee):
        """Calculate tax related components"""
        try:
            # Handle NPWP Gabung Suami case
            if employee.gender == "Female" and cint(employee.get("npwp_gabung_suami")):
                self.is_final_gabung_suami = 1
                self.payroll_note = "Pajak final digabung dengan NPWP suami"
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
                
        except Exception as e:
            frappe.log_error(
                "Tax Calculation Error",
                f"Employee: {employee.name}\nError: {str(e)}"
            )
            raise
    
    def calculate_monthly_pph(self, employee):
        """Calculate PPh 21 using TER method for regular months"""
        # Get TER rate from PPh TER Table
        ter = frappe.get_all(
            "PPh TER Table",
            filters={
                "status_pajak": employee.status_pajak,
                "from_amount": ["<=", self.netto],
                "to_amount": [">", self.netto]
            },
            fields=["ter_rate"],
            order_by="from_amount desc",
            limit=1
        )
        
        if not ter:
            frappe.throw(_(
                "TER rate not found for status {0} and amount {1}"
            ).format(employee.status_pajak, self.netto))
        
        pph21 = self.netto * (ter[0].ter_rate / 100)
        self.update_deduction("PPh 21", pph21)
        
        # Update note with TER rate info
        self.payroll_note += f"\nTarif PPh 21 (TER): {ter[0].ter_rate}%"
    
    def calculate_december_pph(self, employee):
        """Calculate year-end tax correction for December"""
        year = getdate(self.end_date).year
        
        # Get year-to-date totals
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
        annual_pph, tax_details = self.calculate_progressive_tax(pkp)
        
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
        self.set_december_note(
            annual_gross=annual_gross,
            annual_biaya_jabatan=annual_biaya_jabatan,
            annual_bpjs=annual_bpjs,
            annual_netto=annual_netto,
            ptkp=ptkp,
            pkp=pkp,
            tax_details=tax_details,
            annual_pph=annual_pph,
            ytd_pph=ytd.pph21,
            correction=correction
        )
    
    def calculate_progressive_tax(self, pkp):
        """Calculate tax using progressive rates"""
        tax_brackets = [
            (0, 50_000_000, 0.05),
            (50_000_000, 250_000_000, 0.15),
            (250_000_000, 500_000_000, 0.25),
            (500_000_000, float('inf'), 0.35)
        ]
        
        total_tax = 0
        tax_details = []
        remaining_pkp = pkp
        
        for lower, upper, rate in tax_brackets:
            if remaining_pkp <= 0:
                break
                
            taxable = min(remaining_pkp, upper - lower)
            tax = taxable * rate
            total_tax += tax
            
            if tax > 0:
                tax_details.append({
                    'rate': rate * 100,
                    'taxable': taxable,
                    'tax': tax
                })
            
            remaining_pkp -= taxable
        
        return total_tax, tax_details
    
    def set_basic_payroll_note(self, employee):
        """Set basic payroll note with component details"""
        self.payroll_note = "\n".join([
            f"Status Pajak: {employee.status_pajak}",
            f"Penghasilan Bruto: Rp {self.gross_pay:,.0f}",
            f"Biaya Jabatan: Rp {self.biaya_jabatan:,.0f}",
            f"BPJS (JHT+JP+Kesehatan): Rp {self.total_bpjs:,.0f}",
            f"Penghasilan Neto: Rp {self.netto:,.0f}"
        ])
    
    def set_december_note(self, **kwargs):
        """Set detailed December correction note"""
        self.payroll_note = "\n".join([
            "=== Perhitungan PPh 21 Tahunan ===",
            f"Penghasilan Bruto Setahun: Rp {kwargs['annual_gross']:,.0f}",
            f"Biaya Jabatan: Rp {kwargs['annual_biaya_jabatan']:,.0f}",
            f"Total BPJS: Rp {kwargs['annual_bpjs']:,.0f}",
            f"Penghasilan Neto: Rp {kwargs['annual_netto']:,.0f}",
            f"PTKP: Rp {kwargs['ptkp']:,.0f}",
            f"PKP: Rp {kwargs['pkp']:,.0f}",
            "",
            "Perhitungan Per Lapisan Pajak:",
            *[
                f"- Lapisan {d['rate']:.0f}%: "
                f"Rp {d['taxable']:,.0f} × {d['rate']:.0f}% = "
                f"Rp {d['tax']:,.0f}"
                for d in kwargs['tax_details']
            ],
            "",
            f"Total PPh 21 Setahun: Rp {kwargs['annual_pph']:,.0f}",
            f"PPh 21 Sudah Dibayar: Rp {kwargs['ytd_pph']:,.0f}",
            f"Koreksi Desember: Rp {kwargs['correction']:,.0f}",
            f"({'Kurang Bayar' if kwargs['correction'] > 0 else 'Lebih Bayar'})"
        ])
    
    def update_all_totals(self):
        """Update all total fields"""
        self.total_deduction = sum(flt(d.amount) for d in self.deductions)
        self.net_pay = self.gross_pay - self.total_deduction
        self.rounded_total = round(self.net_pay)
        
        company_currency = frappe.get_cached_value(
            'Company', 
            self.company,
            'default_currency'
        )
        self.total_in_words = money_in_words(
            self.rounded_total,
            company_currency
        )
    
    def is_december(self):
        """Check if salary slip is for December"""
        return getdate(self.end_date).month == 12
