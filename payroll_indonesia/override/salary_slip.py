import frappe
from frappe import _
from frappe.utils import flt, getdate
from erpnext.payroll.doctype.salary_slip.salary_slip import SalarySlip
from payroll_indonesia.payroll_indonesia.tax.pph_ter import hitung_pph_ter, hitung_biaya_jabatan
from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import hitung_bpjs
from payroll_indonesia.payroll_indonesia.tax.annual_calculation import hitung_pph_tahunan
from payroll_indonesia.payroll_indonesia.utils import get_spt_month

class CustomSalarySlip(SalarySlip):
    def calculate_component_amounts(self):
        # Call original method first
        super(CustomSalarySlip, self).calculate_component_amounts()
        
        # Additional Indonesian calculations
        self.calculate_indonesia_payroll()
    
    def calculate_indonesia_payroll(self):
        # Get basic salary for calculations
        gaji_pokok = 0
        for earning in self.earnings:
            if earning.salary_component == "Gaji Pokok":
                gaji_pokok = earning.amount
                break
        
        if not gaji_pokok:
            return
        
        # Get employee details
        employee_doc = frappe.get_doc("Employee", self.employee)
        status_pajak = employee_doc.get("status_pajak", "TK0")
        
        # Calculate gross pay (already done by ERPNext)
        gross_pay = self.gross_pay
        
        # Calculate BPJS
        bpjs_result = hitung_bpjs(self.employee, gaji_pokok)
        bpjs_employee_total = bpjs_result["total_employee"]
        
        # Calculate Biaya Jabatan
        biaya_jabatan = hitung_biaya_jabatan(gross_pay)
        
        # Calculate net income for tax
        penghasilan_neto = gross_pay - biaya_jabatan - bpjs_employee_total
        
        # Calculate PPh 21 (TER method)
        pph21_ter = hitung_pph_ter(penghasilan_neto, status_pajak)
        
        # Check if this is SPT month (usually December)
        spt_month = get_spt_month()
        is_spt_month = getdate(self.posting_date).month == spt_month
        correction = 0
        
        if is_spt_month:
            tahun_pajak = getdate(self.posting_date).year
            annual_calc = hitung_pph_tahunan(self.employee, tahun_pajak)
            correction = annual_calc["correction"]
            
            if employee_doc.get("npwp_gabung_suami"):
                self.custom_status = "Final Gabung Suami"
        
        # Update deductions with calculated values
        self.update_component_row("BPJS Kesehatan", bpjs_result["kesehatan_employee"])
        self.update_component_row("BPJS TK", 
                                  bpjs_result["jht_employee"] + 
                                  bpjs_result["jp_employee"])
        self.update_component_row("Biaya Jabatan", biaya_jabatan)
        self.update_component_row("PPh 21", pph21_ter)
        
        if is_spt_month and correction != 0:
            self.update_component_row("PPh 21 Correction", correction)
        
        # Re-calculate totals
        self.calculate_totals()
    
    def update_component_row(self, component_name, amount):
        """Update or add a salary component row"""
        for row in self.deductions:
            if row.salary_component == component_name:
                row.amount = amount
                return
        
        # If component doesn't exist, fetch it from the database
        component = frappe.db.get_value("Salary Component", {"name": component_name}, 
                                        ["name", "is_tax_applicable", "is_flexible_benefit"], 
                                        as_dict=1)
        
        if component:
            self.append("deductions", {
                "salary_component": component_name,
                "amount": amount,
                "default_amount": amount,
                "is_tax_applicable": component.is_tax_applicable,
                "is_flexible_benefit": component.is_flexible_benefit,
            })
    
    def calculate_totals(self):
        """Re-calculate all totals"""
        self.total_deduction = sum(d.amount for d in self.deductions if d.amount)
        self.net_pay = self.gross_pay - self.total_deduction
        
        # Calculate total tax
        self.total_tax_deducted = 0
        for d in self.deductions:
            if d.salary_component in ["PPh 21", "PPh 21 Correction"]:
                self.total_tax_deducted += d.amount