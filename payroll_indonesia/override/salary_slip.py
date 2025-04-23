# -*- coding: utf-8 -*-
# Copyright (c) 2025, Danny Audian and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, money_in_words, cint
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip

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
        self.is_using_ter = 0  # Flag untuk menandai penggunaan TER
        self.ter_rate = 0      # Menyimpan rate TER yang digunakan
    
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
        from payroll_indonesia.payroll_indonesia.utils import calculate_bpjs_contributions
        
        if not hasattr(employee, 'ikut_bpjs_ketenagakerjaan'):
            employee.ikut_bpjs_ketenagakerjaan = 0
            
        if not hasattr(employee, 'ikut_bpjs_kesehatan'):
            employee.ikut_bpjs_kesehatan = 0
            
        if not employee.ikut_bpjs_ketenagakerjaan and not employee.ikut_bpjs_kesehatan:
            return
        
        try:
            bpjs_result = calculate_bpjs_contributions(gaji_pokok)
            
            # Update BPJS components
            if employee.ikut_bpjs_ketenagakerjaan:
                self.update_component_amount(
                    "BPJS JHT Employee", 
                    bpjs_result["ketenagakerjaan"]["jht"]["karyawan"],
                    "deductions"
                )
                self.update_component_amount(
                    "BPJS JP Employee",
                    bpjs_result["ketenagakerjaan"]["jp"]["karyawan"],
                    "deductions"
                )
            
            if employee.ikut_bpjs_kesehatan:
                self.update_component_amount(
                    "BPJS Kesehatan Employee",
                    bpjs_result["kesehatan"]["karyawan"],
                    "deductions"
                )
            
            # Store total BPJS for tax calculation
            self.total_bpjs = (
                (bpjs_result["ketenagakerjaan"]["jht"]["karyawan"] if employee.ikut_bpjs_ketenagakerjaan else 0) +
                (bpjs_result["ketenagakerjaan"]["jp"]["karyawan"] if employee.ikut_bpjs_ketenagakerjaan else 0) +
                (bpjs_result["kesehatan"]["karyawan"] if employee.ikut_bpjs_kesehatan else 0)
            )
            
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
            if hasattr(employee, 'gender') and employee.gender == "Female" and hasattr(employee, 'npwp_gabung_suami') and cint(employee.get("npwp_gabung_suami")):
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
        """Calculate PPh 21 for regular months"""
        # Get PPh 21 Settings
        pph_settings = frappe.get_single("PPh 21 Settings")
        
        # Check if TER method is enabled
        if pph_settings.calculation_method == "TER" and pph_settings.use_ter:
            self.calculate_monthly_pph_with_ter(employee)
        else:
            self.calculate_monthly_pph_progressive(employee)
            
    def calculate_monthly_pph_with_ter(self, employee):
        """Calculate PPh 21 using TER method"""
        try:
            # Validate employee status_pajak
            if not hasattr(employee, 'status_pajak') or not employee.status_pajak:
                employee.status_pajak = "TK0"  # Default to TK0 if not set
                frappe.msgprint(_("Warning: Employee tax status not set, using TK0 as default"))
            
            # Get TER rate based on status and gross income
            ter_rate = self.get_ter_rate(employee.status_pajak, self.gross_pay)
            
            # Calculate tax using TER
            monthly_tax = self.gross_pay * ter_rate
            
            # Save TER info
            self.is_using_ter = 1
            self.ter_rate = ter_rate * 100  # Convert to percentage for display
            
            # Update PPh 21 component
            self.update_component_amount("PPh 21", monthly_tax, "deductions")
            
            # Update note with TER info
            self.payroll_note += "\n\n=== Perhitungan PPh 21 dengan TER ==="
            self.payroll_note += f"\nStatus Pajak: {employee.status_pajak}"
            self.payroll_note += f"\nPenghasilan Bruto: Rp {self.gross_pay:,.0f}"
            self.payroll_note += f"\nTarif Efektif Rata-rata: {ter_rate * 100:.2f}%"
            self.payroll_note += f"\nPPh 21 Sebulan: Rp {monthly_tax:,.0f}"
            self.payroll_note += "\n\nSesuai PMK 168/2023 tentang Tarif Efektif Rata-rata"
            
        except Exception as e:
            frappe.log_error(
                "TER Calculation Error",
                f"Employee: {employee.name}\nError: {str(e)}"
            )
            frappe.throw(_("Error calculating PPh 21 with TER: {0}").format(str(e)))
    
    def get_ter_rate(self, status_pajak, income):
        """Get TER rate based on status and income"""
        # Query the TER table for matching bracket
        ter = frappe.db.sql("""
            SELECT rate
            FROM `tabPPh 21 TER Table`
            WHERE status_pajak = %s
              AND %s >= income_from
              AND (%s <= income_to OR income_to = 0)
            LIMIT 1
        """, (status_pajak, income, income), as_dict=1)
        
        if not ter:
            status_fallback = status_pajak[0:2] + "0"  # Fallback to TK0/K0/HB0
            frappe.msgprint(_(
                "No TER rate found for status {0} and income {1}, falling back to {2}."
            ).format(status_pajak, frappe.format(income, {"fieldtype": "Currency"}), status_fallback))
            
            ter = frappe.db.sql("""
                SELECT rate
                FROM `tabPPh 21 TER Table`
                WHERE status_pajak = %s
                  AND %s >= income_from
                  AND (%s <= income_to OR income_to = 0)
                LIMIT 1
            """, (status_fallback, income, income), as_dict=1)
            
            if not ter:
                frappe.throw(_(
                    "No TER rate found for status {0} or {1} and income {2}. "
                    "Please check PPh 21 TER Table settings."
                ).format(status_pajak, status_fallback, 
                        frappe.format(income, {"fieldtype": "Currency"})))
        
        # Convert percent to decimal (e.g., 5% to 0.05)
        return float(ter[0].rate) / 100.0
    
    def calculate_monthly_pph_progressive(self, employee):
        """Calculate PPh 21 using progressive method"""
        # Get PPh 21 Settings
        pph_settings = frappe.get_single("PPh 21 Settings")
        
        # Get PTKP value
        if not hasattr(employee, 'status_pajak'):
            employee.status_pajak = "TK0"  # Default to TK0 if not set
            
        ptkp = self.get_ptkp_amount(pph_settings, employee.status_pajak)
        
        # Annualize monthly netto
        annual_netto = self.netto * 12
        
        # Calculate PKP
        pkp = max(annual_netto - ptkp, 0)
        
        # Calculate annual tax
        annual_tax, tax_details = self.calculate_progressive_tax(pkp, pph_settings)
        
        # Get monthly tax (1/12 of annual)
        monthly_tax = annual_tax / 12
        
        # Update PPh 21 component
        self.update_component_amount("PPh 21", monthly_tax, "deductions")
        
        # Update note with tax info
        self.payroll_note += f"\n\n=== Perhitungan PPh 21 Progresif ==="
        self.payroll_note += f"\nPenghasilan Neto Setahun: Rp {annual_netto:,.0f}"
        self.payroll_note += f"\nPTKP ({employee.status_pajak}): Rp {ptkp:,.0f}"
        self.payroll_note += f"\nPKP: Rp {pkp:,.0f}"
        
        # Add tax calculation details
        if tax_details:
            self.payroll_note += f"\n\nPerhitungan Pajak:"
            for detail in tax_details:
                self.payroll_note += f"\n- {detail['rate']}% x Rp {detail['taxable']:,.0f} = Rp {detail['tax']:,.0f}"
        
        self.payroll_note += f"\n\nPPh 21 Setahun: Rp {annual_tax:,.0f}"
        self.payroll_note += f"\nPPh 21 Sebulan: Rp {monthly_tax:,.0f}"
    
    def get_ptkp_amount(self, pph_settings, status_pajak):
        """Get PTKP amount for a given tax status"""
        # Attempt to get from method if it exists
        if hasattr(pph_settings, 'get_ptkp_amount'):
            return pph_settings.get_ptkp_amount(status_pajak)
            
        # Otherwise query directly from PTKP table
        ptkp = frappe.db.sql("""
            SELECT ptkp_amount
            FROM `tabPPh 21 PTKP`
            WHERE status_pajak = %s
            AND parent = 'PPh 21 Settings'
            LIMIT 1
        """, status_pajak, as_dict=1)
        
        if not ptkp:
            # Default PTKP values if not found
            default_ptkp = {
                "TK0": 54000000, "K0": 58500000, "K1": 63000000, 
                "K2": 67500000, "K3": 72000000, "TK1": 58500000,
                "TK2": 63000000, "TK3": 67500000
            }
            frappe.msgprint(_(
                "PTKP for status {0} not found in settings, using default value."
            ).format(status_pajak))
            return default_ptkp.get(status_pajak, 54000000)
            
        return flt(ptkp[0].ptkp_amount)
    
    def calculate_december_pph(self, employee):
        """Calculate year-end tax correction for December"""
        year = getdate(self.end_date).year
        
        # Get PPh 21 Settings
        pph_settings = frappe.get_single("PPh 21 Settings")
        
        # For December, always use progressive method even if TER is enabled
        # This is according to PMK 168/2023
        
        # Get year-to-date totals
        ytd = self.get_ytd_totals(year)
        
        # Calculate annual totals
        annual_gross = ytd.get("gross", 0) + self.gross_pay
        annual_bpjs = ytd.get("bpjs", 0) + self.total_bpjs
        annual_biaya_jabatan = min(annual_gross * 0.05, 500000)
        annual_netto = annual_gross - annual_bpjs - annual_biaya_jabatan
        
        # Get PTKP value
        if not hasattr(employee, 'status_pajak'):
            employee.status_pajak = "TK0"  # Default to TK0 if not set
            
        ptkp = self.get_ptkp_amount(pph_settings, employee.status_pajak)
        pkp = max(annual_netto - ptkp, 0)
        
        # Calculate annual PPh
        annual_pph, tax_details = self.calculate_progressive_tax(pkp, pph_settings)
        
        # Calculate correction
        correction = annual_pph - ytd.get("pph21", 0)
        self.koreksi_pph21 = correction
        
        # Update December PPh 21
        self.update_component_amount(
            "PPh 21",
            correction,
            "deductions"
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
            ytd_pph=ytd.get("pph21", 0),
            correction=correction
        )
    
    def calculate_progressive_tax(self, pkp, pph_settings=None):
        """Calculate tax using progressive rates"""
        if not pph_settings:
            pph_settings = frappe.get_single("PPh 21 Settings")
            
        bracket_table = pph_settings.bracket_table if hasattr(pph_settings, 'bracket_table') else []
        
        if not bracket_table:
            bracket_table = frappe.db.sql("""
                SELECT income_from, income_to, tax_rate
                FROM `tabPPh 21 Tax Bracket`
                WHERE parent = 'PPh 21 Settings'
                ORDER BY income_from ASC
            """, as_dict=1)
        
        if not bracket_table:
            # Default bracket values if not found
            bracket_table = [
                {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
                {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
                {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
                {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
            ]
            frappe.msgprint(_("Tax brackets not configured, using default progressive rates."))
        
        total_tax = 0
        tax_details = []
        remaining_pkp = pkp
        
        for bracket in sorted(bracket_table, key=lambda x: x.get("income_from", 0)):
            if remaining_pkp <= 0:
                break
                
            income_from = flt(bracket.get("income_from", 0))
            income_to = flt(bracket.get("income_to", 0))
            tax_rate = flt(bracket.get("tax_rate", 0))
            
            upper_limit = income_to if income_to > 0 else float('inf')
            lower_limit = income_from
            taxable = min(remaining_pkp, upper_limit - lower_limit)
            
            tax = taxable * (tax_rate / 100)
            total_tax += tax
            
            if tax > 0:
                tax_details.append({
                    'rate': tax_rate,
                    'taxable': taxable,
                    'tax': tax
                })
            
            remaining_pkp -= taxable
        
        return total_tax, tax_details
    
    def set_basic_payroll_note(self, employee):
        """Set basic payroll note with component details"""
        self.payroll_note = "\n".join([
            f"Status Pajak: {employee.status_pajak if hasattr(employee, 'status_pajak') else 'TK0'}",
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
        
        # Tambahkan catatan tentang penggunaan metode progresif untuk koreksi tahunan
        self.payroll_note += "\n\nMetode perhitungan Desember menggunakan metode progresif sesuai PMK 168/2023"
    
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
        
    def get_component_amount(self, component_name, component_type):
        """Get amount for a specific component"""
        components = self.earnings if component_type == "earnings" else self.deductions
        for component in components:
            if component.salary_component == component_name:
                return flt(component.amount)
        return 0
    
    def update_component_amount(self, component_name, amount, component_type):
        """Update amount for a specific component"""
        components = self.earnings if component_type == "earnings" else self.deductions
        
        # Find if component exists
        for component in components:
            if component.salary_component == component_name:
                component.amount = flt(amount)
                return
        
        # If not found, append new component
        component_doc = frappe.get_doc("Salary Component", component_name)
        row = frappe.new_doc("Salary Detail")
        row.salary_component = component_name
        row.abbr = component_doc.salary_component_abbr
        row.amount = flt(amount)
        row.parentfield = component_type
        row.parenttype = "Salary Slip"
        
        components.append(row)
    
    def get_ytd_totals(self, year):
        """Get year-to-date totals for the employee"""
        # This is a simplified implementation - in a real app you'd query
        # the database to get actual YTD totals from previous salary slips
        
        # Create a default result with zeros
        result = {"gross": 0, "bpjs": 0, "pph21": 0}
        
        # Get salary slips for the current employee in the current year
        # but before the current month
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters={
                "employee": self.employee,
                "start_date": [">=", f"{year}-01-01"],
                "end_date": ["<", self.start_date],
                "docstatus": 1
            },
            fields=["name", "gross_pay", "total_deduction"]
        )
        
        # Sum up the values
        for slip in salary_slips:
            slip_doc = frappe.get_doc("Salary Slip", slip.name)
            
            # Add to gross
            result["gross"] += flt(slip_doc.gross_pay)
            
            # Add BPJS components
            bpjs_components = ["BPJS JHT Employee", "BPJS JP Employee", "BPJS Kesehatan Employee"]
            for component in bpjs_components:
                result["bpjs"] += self.get_component_amount_from_doc(slip_doc, component)
            
            # Add PPh 21
            result["pph21"] += self.get_component_amount_from_doc(slip_doc, "PPh 21")
        
        return result
    
    def get_component_amount_from_doc(self, doc, component_name):
        """Get component amount from a document"""
        for component in doc.deductions:
            if component.salary_component == component_name:
                return flt(component.amount)
        return 0