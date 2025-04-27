# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 02:08:23 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate, money_in_words, cint
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip

class CustomSalarySlip(SalarySlip):
    def validate(self):
        """Validate salary slip data with improved error handling"""
        try:
            # Check if employee exists before proceeding
            if not self.employee:
                frappe.throw(_("Employee is mandatory for Salary Slip"))
                
            # Initialize custom fields first to avoid NoneType errors
            self.initialize_custom_fields()
            
            # Check if required DocTypes and settings exist
            self.validate_dependent_doctypes()
            
            # Validate employee data is complete
            self.validate_employee_data()
            
            # Then call parent validate
            super().validate()
            
            # Validate required salary components
            self.validate_required_components()
            
        except Exception as e:
            frappe.log_error(
                f"Error validating salary slip for {self.employee if hasattr(self, 'employee') else 'unknown employee'}: {str(e)}",
                "Salary Slip Validation Error"
            )
            frappe.throw(_("Error validating salary slip: {0}").format(str(e)))
    
    def validate_dependent_doctypes(self):
        """Check if all dependent DocTypes and settings exist"""
        try:
            # Check BPJS Settings
            if not frappe.db.exists("DocType", "BPJS Settings"):
                frappe.throw(_("BPJS Settings DocType not found. Please make sure Payroll Indonesia is properly installed."))
                
            # Check if BPJS Settings document exists
            if not frappe.db.exists("BPJS Settings", "BPJS Settings"):
                frappe.throw(_("BPJS Settings document not configured. Please create BPJS Settings first."))
                
            # Check PPh 21 Settings
            if not frappe.db.exists("DocType", "PPh 21 Settings"):
                frappe.throw(_("PPh 21 Settings DocType not found. Please make sure Payroll Indonesia is properly installed."))
                
            # Check if PPh 21 Settings document exists
            if not frappe.db.exists("PPh 21 Settings", "PPh 21 Settings"):
                frappe.throw(_("PPh 21 Settings document not configured. Please create PPh 21 Settings first."))
                
            # Check Employee Tax Summary DocType
            if not frappe.db.exists("DocType", "Employee Tax Summary"):
                frappe.throw(_("Employee Tax Summary DocType not found. Please make sure Payroll Indonesia is properly installed."))
                
            # Check BPJS Payment Summary DocType
            if not frappe.db.exists("DocType", "BPJS Payment Summary"):
                frappe.throw(_("BPJS Payment Summary DocType not found. Please make sure Payroll Indonesia is properly installed."))
                
            # Check PPh TER Table DocType
            if not frappe.db.exists("DocType", "PPh TER Table"):
                frappe.throw(_("PPh TER Table DocType not found. Please make sure Payroll Indonesia is properly installed."))
                
        except Exception as e:
            if isinstance(e, frappe.exceptions.ValidationError):
                raise
            frappe.log_error(
                f"Error validating dependent DocTypes: {str(e)}",
                "Dependent DocType Validation Error"
            )
            frappe.throw(_("Error validating dependent DocTypes: {0}").format(str(e)))
    
    def validate_employee_data(self):
        """Validate that employee has all required data"""
        try:
            if not self.employee:
                return
                
            employee = frappe.get_doc("Employee", self.employee)
            
            # Check if essential fields exist
            required_fields = [
                ("status_pajak", "TK0", "Tax status not set for employee {0}, using default (TK0)"),
                ("ikut_bpjs_kesehatan", 0, "BPJS Kesehatan participation not set for employee {0}, using default (No)"),
                ("ikut_bpjs_ketenagakerjaan", 0, "BPJS Ketenagakerjaan participation not set for employee {0}, using default (No)")
            ]
            
            for field, default_value, message in required_fields:
                if not hasattr(employee, field) or getattr(employee, field) is None:
                    setattr(employee, field, default_value)
                    frappe.msgprint(_(message).format(employee.name))
                    
            # For female employees, check npwp_gabung_suami
            if employee.gender == "Female" and not hasattr(employee, 'npwp_gabung_suami'):
                employee.npwp_gabung_suami = 0
                frappe.msgprint(_("NPWP Gabung Suami not set for employee {0}, using default (No)").format(employee.name))
                
        except Exception as e:
            frappe.log_error(
                f"Error validating employee data for {self.employee if hasattr(self, 'employee') else 'unknown employee'}: {str(e)}",
                "Employee Data Validation Error"
            )
            frappe.throw(_("Error validating employee data: {0}").format(str(e)))
            
    def initialize_custom_fields(self):
        """Initialize custom fields with default values"""
        try:
            # Define all custom fields with their default values
            custom_fields = {
                'is_final_gabung_suami': 0,
                'koreksi_pph21': 0,
                'payroll_note': "",
                'biaya_jabatan': 0,
                'netto': 0,
                'total_bpjs': 0,
                'is_using_ter': 0,
                'ter_rate': 0
            }
            
            # Set default values for all fields
            for field, default_value in custom_fields.items():
                if not hasattr(self, field) or getattr(self, field) is None:
                    setattr(self, field, default_value)
        except Exception as e:
            frappe.log_error(
                f"Error initializing custom fields for {self.employee if hasattr(self, 'employee') else 'unknown employee'}: {str(e)}",
                "Field Initialization Error"
            )
            frappe.throw(_("Error initializing custom fields: {0}").format(str(e)))
    
    def validate_required_components(self):
        """Validate existence of required salary components"""
        try:
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
                # Create a detailed error message
                error_message = _(
                    "Required salary components not found: {0}. "
                    "Please create these components before proceeding."
                ).format(", ".join(missing))
                
                frappe.throw(error_message)
                
            # Also validate that all components are assigned to this salary slip
            for component_type, components in required_components.items():
                components_in_slip = [d.salary_component for d in getattr(self, component_type)]
                for component in components:
                    if component not in components_in_slip:
                        # Add the missing component
                        try:
                            component_doc = frappe.get_doc("Salary Component", component)
                            self.append(component_type, {
                                "salary_component": component,
                                "abbr": component_doc.salary_component_abbr,
                                "amount": 0
                            })
                            frappe.msgprint(_(
                                "Added missing component {0} to salary slip"
                            ).format(component))
                        except Exception as e:
                            frappe.log_error(
                                f"Error adding component {component}: {str(e)}",
                                "Component Addition Error"
                            )
                            frappe.throw(_("Error adding component {0}: {1}").format(component, str(e)))
                
        except Exception as e:
            if isinstance(e, frappe.exceptions.ValidationError):
                raise
            frappe.log_error(
                f"Error validating required components: {str(e)}",
                "Component Validation Error"
            )
            frappe.throw(_("Error validating required salary components: {0}").format(str(e)))

    def calculate_component_amounts(self, component_type):
        """
        Calculate salary components with Indonesian payroll rules.
        
        Args:
            component_type (str): Type of component (earnings or deductions)
        """
        try:
            # Call standard ERPNext calculation first
            super().calculate_component_amounts(component_type)
            
            # After both component types are calculated, do Indonesia-specific calculations
            if component_type == "deductions":
                # Ensure payroll_note is initialized as empty string before calculation
                if not hasattr(self, 'payroll_note') or self.payroll_note is None:
                    self.payroll_note = ""
                    
                self.calculate_indonesia_specific_components()
                
        except Exception as e:
            frappe.log_error(
                f"Salary Slip Calculation Error for {self.employee}: {str(e)}",
                "Component Calculation Error"
            )
            frappe.throw(_(
                "Error calculating {0} components: {1}"
            ).format(component_type, str(e)))
    
    def calculate_indonesia_specific_components(self):
        """Calculate Indonesia-specific salary components"""
        try:
            # Ensure payroll_note is initialized as empty string
            if not hasattr(self, 'payroll_note') or self.payroll_note is None:
                self.payroll_note = ""
                
            # Validate employee object
            if not self.employee:
                frappe.throw(_("Employee is required for calculating components"))
                
            # Get employee details with error handling
            try:
                employee = frappe.get_doc("Employee", self.employee)
            except Exception as e:
                frappe.throw(_("Could not retrieve employee data: {0}").format(str(e)))
                
            # Get basic salary (Gaji Pokok)
            gaji_pokok = self.get_component_amount("Gaji Pokok", "earnings")
            if not gaji_pokok:
                frappe.msgprint(_("Warning: 'Gaji Pokok' amount is zero"))
                
            # Calculate BPJS components
            self.calculate_bpjs_components(employee, gaji_pokok)
            
            # Calculate tax components
            self.calculate_tax_components(employee)
            
            # Update totals
            self.update_all_totals()
            
        except Exception as e:
            frappe.log_error(
                f"Indonesia Salary Component Calculation Error for {self.employee}: {str(e)}",
                "Indonesia Component Calculation Error"
            )
            frappe.throw(_(
                "Error calculating Indonesia-specific components: {0}"
            ).format(str(e)))
    
    def calculate_bpjs_components(self, employee, gaji_pokok):
        """Calculate and update BPJS components based on settings"""
        # Ensure payroll_note is initialized as empty string
        if not hasattr(self, 'payroll_note') or self.payroll_note is None:
            self.payroll_note = ""
            
        # Initialize BPJS participation fields if not exist
        if not hasattr(employee, 'ikut_bpjs_ketenagakerjaan'):
            employee.ikut_bpjs_ketenagakerjaan = 0
            frappe.msgprint(_("BPJS Ketenagakerjaan participation not set for employee {0}, using default (No)").format(employee.name))
            
        if not hasattr(employee, 'ikut_bpjs_kesehatan'):
            employee.ikut_bpjs_kesehatan = 0
            frappe.msgprint(_("BPJS Kesehatan participation not set for employee {0}, using default (No)").format(employee.name))
            
        # Skip if employee doesn't participate in any BPJS programs
        if not employee.ikut_bpjs_ketenagakerjaan and not employee.ikut_bpjs_kesehatan:
            return
        
        try:
            # Get BPJS Settings with validation
            try:
                bpjs_settings = frappe.get_single("BPJS Settings")
            except Exception as e:
                frappe.throw(_("Error retrieving BPJS Settings: {0}. Please configure BPJS Settings properly.").format(str(e)))
                
            # Validate required fields in BPJS Settings
            required_bpjs_fields = [
                'kesehatan_max_salary', 'kesehatan_employee_percent',
                'jht_employee_percent', 'jp_max_salary', 'jp_employee_percent'
            ]
            
            for field in required_bpjs_fields:
                if not hasattr(bpjs_settings, field) or getattr(bpjs_settings, field) is None:
                    frappe.throw(_("BPJS Settings missing required field: {0}").format(field))
            
            # Initialize values
            kesehatan_employee = 0
            jht_employee = 0
            jp_employee = 0
            
            # Calculate Kesehatan contribution
            if employee.ikut_bpjs_kesehatan:
                # Limit salary for BPJS Kesehatan calculation
                kesehatan_salary = min(gaji_pokok, bpjs_settings.kesehatan_max_salary)
                kesehatan_employee = kesehatan_salary * (bpjs_settings.kesehatan_employee_percent / 100)
                
                self.update_component_amount(
                    "BPJS Kesehatan Employee", 
                    kesehatan_employee,
                    "deductions"
                )
            
            # Calculate Ketenagakerjaan contributions
            if employee.ikut_bpjs_ketenagakerjaan:
                # JHT has no salary limit
                jht_employee = gaji_pokok * (bpjs_settings.jht_employee_percent / 100)
                
                # Limit salary for JP calculation
                jp_salary = min(gaji_pokok, bpjs_settings.jp_max_salary)
                jp_employee = jp_salary * (bpjs_settings.jp_employee_percent / 100)
                
                # Update components
                self.update_component_amount(
                    "BPJS JHT Employee", 
                    jht_employee,
                    "deductions"
                )
                
                self.update_component_amount(
                    "BPJS JP Employee",
                    jp_employee,
                    "deductions"
                )
            
            # Calculate total BPJS for tax purposes with double verification
            total_bpjs_kesehatan = 0
            total_bpjs_jht = 0
            total_bpjs_jp = 0
            
            if employee.ikut_bpjs_kesehatan:
                total_bpjs_kesehatan = self.get_component_amount("BPJS Kesehatan Employee", "deductions")
                
            if employee.ikut_bpjs_ketenagakerjaan:
                total_bpjs_jht = self.get_component_amount("BPJS JHT Employee", "deductions")
                total_bpjs_jp = self.get_component_amount("BPJS JP Employee", "deductions")
            
            self.total_bpjs = total_bpjs_kesehatan + total_bpjs_jht + total_bpjs_jp
            
            # Update payroll note with BPJS details
            self.payroll_note += "\n\n=== Perhitungan BPJS ==="
            
            if employee.ikut_bpjs_kesehatan:
                self.payroll_note += f"\nBPJS Kesehatan ({bpjs_settings.kesehatan_employee_percent}%): Rp {total_bpjs_kesehatan:,.0f}"
            
            if employee.ikut_bpjs_ketenagakerjaan:
                self.payroll_note += f"\nBPJS JHT ({bpjs_settings.jht_employee_percent}%): Rp {total_bpjs_jht:,.0f}"
                self.payroll_note += f"\nBPJS JP ({bpjs_settings.jp_employee_percent}%): Rp {total_bpjs_jp:,.0f}"
            
            self.payroll_note += f"\nTotal BPJS: Rp {self.total_bpjs:,.0f}"
                
        except Exception as e:
            frappe.log_error(
                f"BPJS Calculation Error for Employee {employee.name}: {str(e)}",
                "BPJS Calculation Error"
            )
            # Convert to user-friendly error
            frappe.throw(_("Error calculating BPJS components: {0}").format(str(e)))
    
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
                f"Tax Calculation Error for Employee {employee.name}: {str(e)}",
                "Tax Calculation Error"
            )
            # Convert to user-friendly error
            frappe.throw(_("Error calculating tax components: {0}").format(str(e)))
    
    # Override get_holidays_for_employee to be more tolerant
    def get_holidays_for_employee(self, start_date, end_date):
        """
        Override for get_holidays_for_employee that doesn't throw errors if Holiday List not found
        """
        holidays = []
        try:
            # Try to get holiday list from employee or company
            holiday_list = frappe.db.get_value("Employee", self.employee, "holiday_list")
            if not holiday_list:
                holiday_list = frappe.db.get_value("Company", self.company, "default_holiday_list")
                
            # If holiday list exists, get the holidays
            if holiday_list:
                holidays = frappe.get_all(
                    "Holiday",
                    filters={"parent": holiday_list, "holiday_date": ["between", [start_date, end_date]]},
                    fields=["holiday_date", "description"],
                    order_by="holiday_date",
                )
                
        except Exception as e:
            frappe.log_error(
                f"Error getting holidays for employee {self.employee}: {str(e)}",
                "Holiday List Error"
            )
            # Don't throw error, just add a message
            frappe.msgprint(_("Could not retrieve holidays: {0}").format(str(e)))
            
        # Return holidays or empty list if none
        return holidays

    def calculate_monthly_pph(self, employee):
        """Calculate PPh 21 for regular months"""
        try:
            # Get PPh 21 Settings with validation
            try:
                pph_settings = frappe.get_single("PPh 21 Settings")
            except Exception as e:
                frappe.throw(_("Error retrieving PPh 21 Settings: {0}. Please configure PPh 21 Settings properly.").format(str(e)))
            
            # Check if calculation_method and use_ter fields exist
            if not hasattr(pph_settings, 'calculation_method'):
                frappe.msgprint(_("PPh 21 Settings missing calculation_method, defaulting to Progressive"))
                pph_settings.calculation_method = "Progressive"
                
            if not hasattr(pph_settings, 'use_ter'):
                frappe.msgprint(_("PPh 21 Settings missing use_ter, defaulting to No"))
                pph_settings.use_ter = 0

            # Check if TER method is enabled
            if pph_settings.calculation_method == "TER" and pph_settings.use_ter:
                self.calculate_monthly_pph_with_ter(employee)
            else:
                self.calculate_monthly_pph_progressive(employee)
                
        except Exception as e:
            frappe.log_error(
                f"Monthly PPh Calculation Error for Employee {employee.name}: {str(e)}",
                "PPh Calculation Error"
            )
            # Convert to user-friendly error
            frappe.throw(_("Error calculating monthly PPh 21: {0}").format(str(e)))

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
                f"TER Calculation Error for Employee {employee.name}: {str(e)}",
                "TER Calculation Error"
            )
            frappe.throw(_("Error calculating PPh 21 with TER: {0}").format(str(e)))

    def get_ter_rate(self, status_pajak, income):
        """Get TER rate based on status and income"""
        try:
            # Validate inputs
            if not status_pajak:
                status_pajak = "TK0"
                frappe.msgprint(_("Tax status not provided, using TK0 as default"))
                
            if not income or income <= 0:
                frappe.throw(_("Income must be greater than zero for TER calculation"))
                
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
                # Try fallback to simpler status (e.g., TK3 -> TK0)
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
                    # As a last resort, use default rate if defined in settings
                    try:
                        pph_settings = frappe.get_single("PPh 21 Settings")
                        if hasattr(pph_settings, 'default_ter_rate'):
                            default_rate = flt(pph_settings.default_ter_rate)
                            frappe.msgprint(_(
                                "No TER rate found for status {0} or {1} and income {2}. "
                                "Using default rate of {3}%."
                            ).format(status_pajak, status_fallback, 
                                    frappe.format(income, {"fieldtype": "Currency"}),
                                    default_rate))
                            return default_rate / 100.0
                    except Exception:
                        pass
                        
                    # If we get here, we have no rate to use
                    frappe.throw(_(
                        "No TER rate found for status {0} or {1} and income {2}. "
                        "Please check PPh 21 TER Table settings."
                    ).format(status_pajak, status_fallback,
                            frappe.format(income, {"fieldtype": "Currency"})))

            # Convert percent to decimal (e.g., 5% to 0.05)
            return float(ter[0].rate) / 100.0
            
        except Exception as e:
            if isinstance(e, frappe.exceptions.ValidationError):
                raise
            frappe.log_error(
                f"Error getting TER rate for status {status_pajak} and income {income}: {str(e)}",
                "TER Rate Error"
            )
            frappe.throw(_("Error retrieving TER rate: {0}").format(str(e)))

    def calculate_monthly_pph_progressive(self, employee):
        """Calculate PPh 21 using progressive method"""
        try:
            # Get PPh 21 Settings
            try:
                pph_settings = frappe.get_single("PPh 21 Settings")
            except Exception as e:
                frappe.throw(_("Error retrieving PPh 21 Settings: {0}. Please configure PPh 21 Settings properly.").format(str(e)))

            # Get PTKP value
            if not hasattr(employee, 'status_pajak') or not employee.status_pajak:
                employee.status_pajak = "TK0"  # Default to TK0 if not set
                frappe.msgprint(_("Warning: Employee tax status not set, using TK0 as default"))

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
            
        except Exception as e:
            frappe.log_error(
                f"Progressive Tax Calculation Error for Employee {employee.name}: {str(e)}",
                "Progressive Tax Error"
            )
            frappe.throw(_("Error calculating progressive tax: {0}").format(str(e)))

    def get_ptkp_amount(self, pph_settings, status_pajak):
        """Get PTKP amount for a given tax status"""
        try:
            # Validate inputs
            if not status_pajak:
                status_pajak = "TK0"
                frappe.msgprint(_("Tax status not provided, using TK0 as default"))
            
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
                
                # If we don't have a default for this status, use TK0
                if status_pajak not in default_ptkp:
                    frappe.msgprint(_("No default PTKP for status {0}, using TK0 value.").format(status_pajak))
                    return default_ptkp["TK0"]
                    
                return default_ptkp.get(status_pajak)

            return flt(ptkp[0].ptkp_amount)
            
        except Exception as e:
            frappe.log_error(
                f"Error getting PTKP for status {status_pajak}: {str(e)}",
                "PTKP Retrieval Error"
            )
            frappe.throw(_("Error retrieving PTKP amount: {0}").format(str(e)))

    def calculate_december_pph(self, employee):
        """Calculate year-end tax correction for December"""
        try:
            year = getdate(self.end_date).year

            # Get PPh 21 Settings
            try:
                pph_settings = frappe.get_single("PPh 21 Settings")
            except Exception as e:
                frappe.throw(_("Error retrieving PPh 21 Settings: {0}. Please configure PPh 21 Settings properly.").format(str(e)))

            # For December, always use progressive method even if TER is enabled
            # This is according to PMK 168/2023

            # Get year-to-date totals from tax summary instead of recalculating
            ytd = self.get_ytd_totals_from_tax_summary(year)

            # Calculate annual totals
            annual_gross = ytd.get("gross", 0) + self.gross_pay
            annual_bpjs = ytd.get("bpjs", 0) + self.total_bpjs
            annual_biaya_jabatan = min(annual_gross * 0.05, 500000)
            annual_netto = annual_gross - annual_bpjs - annual_biaya_jabatan

            # Get PTKP value
            if not hasattr(employee, 'status_pajak') or not employee.status_pajak:
                employee.status_pajak = "TK0"  # Default to TK0 if not set
                frappe.msgprint(_("Warning: Employee tax status not set, using TK0 as default"))

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
            
        except Exception as e:
            frappe.log_error(
                f"December PPh Calculation Error for Employee {employee.name}: {str(e)}",
                "December PPh Error"
            )
            frappe.throw(_("Error calculating December PPh 21 correction: {0}").format(str(e)))

    def calculate_progressive_tax(self, pkp, pph_settings=None):
        """Calculate tax using progressive rates"""
        try:
            if not pph_settings:
                try:
                    pph_settings = frappe.get_single("PPh 21 Settings")
                except Exception as e:
                    frappe.throw(_("Error retrieving PPh 21 Settings: {0}").format(str(e)))

            # First check if bracket_table is directly available as attribute
            bracket_table = []
            if hasattr(pph_settings, 'bracket_table'):
                bracket_table = pph_settings.bracket_table
                
            # If not found or empty, query from database
            if not bracket_table:
                bracket_table = frappe.db.sql("""
                    SELECT income_from, income_to, tax_rate
                    FROM `tabPPh 21 Tax Bracket`
                    WHERE parent = 'PPh 21 Settings'
                    ORDER BY income_from ASC
                """, as_dict=1)

            # If still not found, use default values
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

            # Calculate tax
            total_tax = 0
            tax_details = []
            remaining_pkp = pkp

            for bracket in sorted(bracket_table, key=lambda x: flt(x.get("income_from", 0))):
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
            
        except Exception as e:
            frappe.log_error(
                f"Progressive Tax Calculation Error for PKP {pkp}: {str(e)}",
                "Tax Bracket Calculation Error"
            )
            frappe.throw(_("Error calculating progressive tax brackets: {0}").format(str(e)))

    def set_basic_payroll_note(self, employee):
        """Set basic payroll note with component details"""
        try:
            status_pajak = employee.status_pajak if hasattr(employee, 'status_pajak') and employee.status_pajak else "TK0"
            
            self.payroll_note = "\n".join([
                f"Status Pajak: {status_pajak}",
                f"Penghasilan Bruto: Rp {self.gross_pay:,.0f}",
                f"Biaya Jabatan: Rp {self.biaya_jabatan:,.0f}",
                f"BPJS (JHT+JP+Kesehatan): Rp {self.total_bpjs:,.0f}",
                f"Penghasilan Neto: Rp {self.netto:,.0f}"
            ])
        except Exception as e:
            frappe.log_error(
                f"Error setting basic payroll note for {self.employee}: {str(e)}",
                "Payroll Note Error"
            )
            # Just set a basic note
            self.payroll_note = f"Penghasilan Bruto: Rp {self.gross_pay:,.0f}"
            frappe.msgprint(_("Error setting detailed payroll note: {0}").format(str(e)))

    def set_december_note(self, **kwargs):
        """Set detailed December correction note"""
        try:
            # Build the note with proper error handling
            note_parts = [
                "=== Perhitungan PPh 21 Tahunan ===",
                f"Penghasilan Bruto Setahun: Rp {kwargs.get('annual_gross', 0):,.0f}",
                f"Biaya Jabatan: Rp {kwargs.get('annual_biaya_jabatan', 0):,.0f}",
                f"Total BPJS: Rp {kwargs.get('annual_bpjs', 0):,.0f}",
                f"Penghasilan Neto: Rp {kwargs.get('annual_netto', 0):,.0f}",
                f"PTKP: Rp {kwargs.get('ptkp', 0):,.0f}",
                f"PKP: Rp {kwargs.get('pkp', 0):,.0f}",
                "",
                "Perhitungan Per Lapisan Pajak:"
            ]
            
            # Add tax bracket details if available
            tax_details = kwargs.get('tax_details', [])
            if tax_details:
                for d in tax_details:
                    rate = flt(d.get('rate', 0))
                    taxable = flt(d.get('taxable', 0))
                    tax = flt(d.get('tax', 0))
                    note_parts.append(
                        f"- Lapisan {rate:.0f}%: "
                        f"Rp {taxable:,.0f} × {rate:.0f}% = "
                        f"Rp {tax:,.0f}"
                    )
            else:
                note_parts.append("- (Tidak ada rincian pajak)")
                
            # Add summary values
            annual_pph = flt(kwargs.get('annual_pph', 0))
            ytd_pph = flt(kwargs.get('ytd_pph', 0))
            correction = flt(kwargs.get('correction', 0))
            
            note_parts.extend([
                "",
                f"Total PPh 21 Setahun: Rp {annual_pph:,.0f}",
                f"PPh 21 Sudah Dibayar: Rp {ytd_pph:,.0f}",
                f"Koreksi Desember: Rp {correction:,.0f}",
                f"({'Kurang Bayar' if correction > 0 else 'Lebih Bayar'})"
            ])

            # Add note about using progressive method for annual correction
            note_parts.append("\n\nMetode perhitungan Desember menggunakan metode progresif sesuai PMK 168/2023")
            
            # Set the note
            self.payroll_note = "\n".join(note_parts)
            
        except Exception as e:
            frappe.log_error(
                f"Error setting December payroll note for {self.employee}: {str(e)}",
                "December Note Error"
            )
            # Set a basic note
            self.payroll_note = "Perhitungan koreksi PPh 21 tahunan"
            frappe.msgprint(_("Error setting detailed December note: {0}").format(str(e)))

    def update_all_totals(self):
        """Update all total fields with validation"""
        try:
            # Calculate total deduction
            self.total_deduction = sum(flt(d.amount) for d in self.deductions)
            
            # Validate net pay can't be negative
            self.net_pay = max(self.gross_pay - self.total_deduction, 0)
            
            # Round the total
            self.rounded_total = round(self.net_pay)

            # Get company currency
            try:
                company_currency = frappe.get_cached_value(
                    'Company',
                    self.company,
                    'default_currency'
                )
                if not company_currency:
                    company_currency = "IDR"  # Default for Indonesia
            except Exception:
                company_currency = "IDR"  # Default fallback
                
            # Set total in words
            try:
                self.total_in_words = money_in_words(
                    self.rounded_total,
                    company_currency
                )
            except Exception as e:
                frappe.log_error(
                    f"Error converting amount to words: {str(e)}",
                    "Money In Words Error"
                )
                self.total_in_words = f"Rupiah {self.rounded_total}"
                
        except Exception as e:
            frappe.log_error(
                f"Error updating totals for {self.employee}: {str(e)}",
                "Totals Update Error"
            )
            frappe.throw(_("Error updating salary slip totals: {0}").format(str(e)))

    def is_december(self):
        """Check if salary slip is for December"""
        try:
            return getdate(self.end_date).month == 12
        except Exception:
            # Default to False if there's an error
            return False

    def get_component_amount(self, component_name, component_type):
        """Get amount for a specific component with validation"""
        try:
            if not component_name or not component_type:
                return 0
                
            components = self.earnings if component_type == "earnings" else self.deductions
            
            for component in components:
                if component.salary_component == component_name:
                    return flt(component.amount)
            return 0
            
        except Exception as e:
            frappe.log_error(
                f"Error getting component {component_name}: {str(e)}",
                "Component Amount Error"
            )
            return 0

    def update_component_amount(self, component_name, amount, component_type):
        """Update amount for a specific component with validation"""
        try:
            if not component_name or not component_type:
                frappe.throw(_("Component name and type are required"))
                
            # Validate amount is a number
            try:
                amount = flt(amount)
            except Exception:
                amount = 0
                frappe.msgprint(_("Invalid amount for component {0}, using 0").format(component_name))
                
            components = self.earnings if component_type == "earnings" else self.deductions

            # Find if component exists
            for component in components:
                if component.salary_component == component_name:
                    component.amount = amount
                    return

            # If not found, ensure component exists in the system
            if not frappe.db.exists("Salary Component", component_name):
                frappe.throw(_("Salary Component {0} does not exist").format(component_name))
                
            # Get component details
            try:
                component_doc = frappe.get_doc("Salary Component", component_name)
                component_abbr = component_doc.salary_component_abbr
            except Exception:
                component_abbr = component_name[:3].upper()
                
            # Create a new row
            try:
                row = frappe.new_doc("Salary Detail")
                row.salary_component = component_name
                row.abbr = component_abbr
                row.amount = amount
                row.parentfield = component_type
                row.parenttype = "Salary Slip"
                components.append(row)
            except Exception as e:
                frappe.throw(_("Error creating component {0}: {1}").format(component_name, str(e)))
                
        except Exception as e:
            frappe.log_error(
                f"Error updating component {component_name}: {str(e)}",
                "Component Update Error"
            )
            frappe.throw(_("Error updating component {0}: {1}").format(component_name, str(e)))

    def get_ytd_totals_from_tax_summary(self, year):
        """
        Get YTD data from Employee Tax Summary instead of recalculating from salary slips
        
        Args:
            year: The tax year
            
        Returns:
            dict: A dictionary with YTD values
        """
        result = {"gross": 0, "bpjs": 0, "pph21": 0}
        
        try:
            # Validate year
            if not year or not isinstance(year, int):
                year = getdate(self.end_date).year

            # Check if Employee Tax Summary DocType exists
            if not frappe.db.exists("DocType", "Employee Tax Summary"):
                frappe.msgprint(_("Employee Tax Summary DocType not found, using traditional YTD calculation"))
                return self.get_ytd_totals(year)
                
            # Get Employee Tax Summary
            tax_summary = frappe.db.get_value(
                "Employee Tax Summary",
                {"employee": self.employee, "year": year},
                ["name"]
            )
            
            if tax_summary:
                # Get the full document
                try:
                    tax_doc = frappe.get_doc("Employee Tax Summary", tax_summary)
                except Exception as e:
                    frappe.log_error(
                        f"Error retrieving Employee Tax Summary {tax_summary}: {str(e)}",
                        "Tax Summary Retrieval Error"
                    )
                    return self.get_ytd_totals(year)
                
                # Get current month
                current_month = getdate(self.start_date).month
                
                # Calculate totals from monthly details
                if hasattr(tax_doc, 'monthly_details') and tax_doc.monthly_details:
                    for monthly in tax_doc.monthly_details:
                        if hasattr(monthly, 'month') and monthly.month < current_month:
                            result["gross"] += flt(monthly.gross_pay if hasattr(monthly, 'gross_pay') else 0)
                            result["bpjs"] += flt(monthly.bpjs_deductions if hasattr(monthly, 'bpjs_deductions') else 0)
                            result["pph21"] += flt(monthly.tax_amount if hasattr(monthly, 'tax_amount') else 0)
                    
                    return result
                else:
                    frappe.msgprint(_("No monthly details found in Tax Summary, using traditional YTD calculation"))
        
        except Exception as e:
            frappe.log_error(
                f"Error getting YTD data from tax summary for {self.employee}: {str(e)}", 
                "YTD Tax Calculation Error"
            )
            frappe.msgprint(_("Error retrieving tax summary data: {0}").format(str(e)))
            
        # Fall back to traditional method if tax summary not found or error occurs
        return self.get_ytd_totals(year)

    def get_ytd_totals(self, year):
        """Get year-to-date totals for the employee (legacy method)"""
        try:
            # Create a default result with zeros
            result = {"gross": 0, "bpjs": 0, "pph21": 0}
            
            # Validate year
            if not year or not isinstance(year, int):
                year = getdate(self.end_date).year
                
            # Validate employee
            if not self.employee:
                return result

            # Get salary slips for the current employee in the current year
            # but before the current month
            try:
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
            except Exception as e:
                frappe.log_error(
                    f"Error querying salary slips for {self.employee}: {str(e)}",
                    "Salary Slip Query Error"
                )
                return result

            # Sum up the values
            for slip in salary_slips:
                try:
                    slip_doc = frappe.get_doc("Salary Slip", slip.name)
                except Exception as e:
                    frappe.log_error(
                        f"Error retrieving Salary Slip {slip.name}: {str(e)}",
                        "Salary Slip Retrieval Error"
                    )
                    continue

                # Add to gross
                result["gross"] += flt(slip_doc.gross_pay)

                # Add BPJS components
                bpjs_components = ["BPJS JHT Employee", "BPJS JP Employee", "BPJS Kesehatan Employee"]
                for component in bpjs_components:
                    result["bpjs"] += self.get_component_amount_from_doc(slip_doc, component)

                # Add PPh 21
                result["pph21"] += self.get_component_amount_from_doc(slip_doc, "PPh 21")

            return result
            
        except Exception as e:
            frappe.log_error(
                f"Error calculating YTD totals for {self.employee}: {str(e)}",
                "YTD Totals Error"
            )
            # Return empty result on error
            return {"gross": 0, "bpjs": 0, "pph21": 0}

    def get_component_amount_from_doc(self, doc, component_name):
        """Get component amount from a document"""
        try:
            if hasattr(doc, 'deductions'):
                for component in doc.deductions:
                    if component.salary_component == component_name:
                        return flt(component.amount)
            return 0
        except Exception as e:
            frappe.log_error(
                f"Error getting component {component_name} from doc {doc.name}: {str(e)}",
                "Component Retrieval Error"
            )
            return 0
            
    def on_submit(self):
        """
        Override on_submit to ensure proper creation of related entries
        This is called by the framework after the document is submitted
        """
        try:
            # Call parent method first
            super().on_submit()
            
            # Create additional entries after submitting
            self.create_tax_summary()
            self.create_bpjs_payment_summary()
            self.create_pph_ter_table()
            
        except Exception as e:
            frappe.log_error(
                f"Error in on_submit for {self.name}: {str(e)}",
                "Salary Slip Submit Error"
            )
            frappe.throw(_("Error submitting salary slip: {0}").format(str(e)))
            
    def create_tax_summary(self):
        """Create or update Employee Tax Summary entry"""
        try:
            year = getdate(self.end_date).year
            month = getdate(self.end_date).month
            
            # Get the PPh 21 amount
            pph21_amount = 0
            for deduction in self.deductions:
                if deduction.salary_component == "PPh 21":
                    pph21_amount = flt(deduction.amount)
                    break
            
            # Get BPJS components from salary slip
            bpjs_deductions = 0
            for deduction in self.deductions:
                if deduction.salary_component in ["BPJS JHT Employee", "BPJS JP Employee", "BPJS Kesehatan Employee"]:
                    bpjs_deductions += flt(deduction.amount)
            
            # Check if Employee Tax Summary DocType exists
            if not frappe.db.exists("DocType", "Employee Tax Summary"):
                frappe.msgprint(_("Employee Tax Summary DocType not found. Cannot create tax summary."))
                return
            
            # Check if we already have a record for this employee/year combination
            existing_tax_summary = frappe.db.get_value("Employee Tax Summary", 
                {"employee": self.employee, "year": year}, "name")
            
            if existing_tax_summary:
                # Get existing record and update it
                try:
                    tax_record = frappe.get_doc("Employee Tax Summary", existing_tax_summary)
                except Exception as e:
                    frappe.throw(_("Error retrieving existing Tax Summary: {0}").format(str(e)))
                
                # Check if monthly_details field exists
                if not hasattr(tax_record, 'monthly_details'):
                    frappe.throw(_("Employee Tax Summary structure is invalid. missing monthly_details child table."))
                
                # Append monthly detail
                has_month = False
                for m in tax_record.monthly_details:
                    if hasattr(m, 'month') and m.month == month:
                        m.gross_pay = self.gross_pay
                        m.bpjs_deductions = bpjs_deductions
                        m.tax_amount = pph21_amount
                        m.salary_slip = self.name
                        m.is_using_ter = 1 if getattr(self, 'is_using_ter', 0) else 0
                        m.ter_rate = getattr(self, 'ter_rate', 0)
                        has_month = True
                        break
                
                if not has_month:
                    # Create new monthly entry
                    monthly_data = {
                        "month": month,
                        "salary_slip": self.name,
                        "gross_pay": self.gross_pay,
                        "bpjs_deductions": bpjs_deductions,
                        "tax_amount": pph21_amount,
                        "is_using_ter": 1 if getattr(self, 'is_using_ter', 0) else 0,
                        "ter_rate": getattr(self, 'ter_rate', 0)
                    }
                    
                    # Add to monthly_details
                    tax_record.append("monthly_details", monthly_data)
                
                # Recalculate YTD tax
                total_tax = 0
                if tax_record.monthly_details:
                    for m in tax_record.monthly_details:
                        if hasattr(m, 'tax_amount'):
                            total_tax += flt(m.tax_amount)
                
                tax_record.ytd_tax = total_tax
                
                # Set title if empty
                if not tax_record.title:
                    tax_record.title = f"{self.employee_name} - {year}"
                    
                # Set TER information at year level if applicable
                if hasattr(tax_record, 'is_using_ter') and hasattr(tax_record, 'ter_rate'):
                    if getattr(self, 'is_using_ter', 0):
                        tax_record.is_using_ter = 1
                        tax_record.ter_rate = getattr(self, 'ter_rate', 0)
                    
                try:
                    tax_record.save(ignore_permissions=True)
                except Exception as e:
                    frappe.throw(_("Error saving Tax Summary: {0}").format(str(e)))
                
            else:
                # Create a new Employee Tax Summary
                try:
                    tax_record = frappe.new_doc("Employee Tax Summary")
                    
                    # Set basic fields
                    tax_record.employee = self.employee
                    tax_record.employee_name = self.employee_name
                    tax_record.year = year
                    tax_record.ytd_tax = pph21_amount
                    tax_record.title = f"{self.employee_name} - {year}"
                    
                    # Set TER information if applicable and fields exist
                    if hasattr(tax_record, 'is_using_ter') and hasattr(tax_record, 'ter_rate'):
                        if getattr(self, 'is_using_ter', 0):
                            tax_record.is_using_ter = 1
                            tax_record.ter_rate = getattr(self, 'ter_rate', 0)
                    
                    # Add monthly detail
                    monthly_data = {
                        "month": month,
                        "salary_slip": self.name,
                        "gross_pay": self.gross_pay,
                        "bpjs_deductions": bpjs_deductions,
                        "tax_amount": pph21_amount,
                        "is_using_ter": 1 if getattr(self, 'is_using_ter', 0) else 0,
                        "ter_rate": getattr(self, 'ter_rate', 0)
                    }
                    
                    # Add to monthly_details if field exists
                    if hasattr(tax_record, 'monthly_details'):
                        tax_record.append("monthly_details", monthly_data)
                    else:
                        frappe.throw(_("Employee Tax Summary structure is invalid. missing monthly_details child table."))
                    
                    tax_record.insert(ignore_permissions=True)
                except Exception as e:
                    frappe.throw(_("Error creating Tax Summary: {0}").format(str(e)))
                
        except Exception as e:
            frappe.log_error(
                f"Error creating Tax Summary for {self.name}: {str(e)}",
                "Tax Summary Error"
            )
            frappe.throw(_("Error creating Tax Summary: {0}").format(str(e)))
            
    def create_bpjs_payment_summary(self):
        """Create or update BPJS Payment Summary based on submitted salary slip"""
        try:
            # Check if BPJS Payment Summary DocType exists
            if not frappe.db.exists("DocType", "BPJS Payment Summary"):
                frappe.msgprint(_("BPJS Payment Summary DocType not found. Cannot create BPJS summary."))
                return
                
            # Determine year and month from salary slip
            end_date = getdate(self.end_date)
            month = end_date.month
            year = end_date.year
            
            # Get BPJS components from salary slip
            bpjs_data = {
                "jht_employee": 0,
                "jp_employee": 0,
                "kesehatan_employee": 0
            }
            
            # Get employee components
            for deduction in self.deductions:
                if deduction.salary_component == "BPJS JHT Employee":
                    bpjs_data["jht_employee"] = flt(deduction.amount)
                elif deduction.salary_component == "BPJS JP Employee":
                    bpjs_data["jp_employee"] = flt(deduction.amount)
                elif deduction.salary_component == "BPJS Kesehatan Employee":
                    bpjs_data["kesehatan_employee"] = flt(deduction.amount)
            
            # Get BPJS Settings for employer calculations
            try:
                bpjs_settings = frappe.get_single("BPJS Settings")
            except Exception as e:
                frappe.throw(_("Error retrieving BPJS Settings: {0}").format(str(e)))
                
            # Validate required fields exist in BPJS Settings
            required_fields = [
                'jht_employer_percent', 'jp_max_salary', 'jp_employer_percent',
                'jkk_percent', 'jkm_percent', 'kesehatan_max_salary',
                'kesehatan_employer_percent'
            ]
            
            for field in required_fields:
                if not hasattr(bpjs_settings, field) or getattr(bpjs_settings, field) is None:
                    frappe.throw(_("BPJS Settings missing required field: {0}").format(field))
            
            # Calculate employer components
            # JHT Employer (3.7%)
            jht_employer = self.gross_pay * (bpjs_settings.jht_employer_percent / 100)
            
            # JP Employer (2%)
            jp_salary = min(self.gross_pay, bpjs_settings.jp_max_salary)
            jp_employer = jp_salary * (bpjs_settings.jp_employer_percent / 100)
            
            # JKK (0.24% - 1.74% depending on risk)
            jkk = self.gross_pay * (bpjs_settings.jkk_percent / 100)
            
            # JKM (0.3%)
            jkm = self.gross_pay * (bpjs_settings.jkm_percent / 100)
            
            # Kesehatan Employer (4%)
            kesehatan_salary = min(self.gross_pay, bpjs_settings.kesehatan_max_salary)
            kesehatan_employer = kesehatan_salary * (bpjs_settings.kesehatan_employer_percent / 100)
            
            # Check if BPJS Payment Summary exists for this period
            bpjs_summary = frappe.db.get_value(
                "BPJS Payment Summary",
                {"company": self.company, "year": year, "month": month, "docstatus": ["!=", 2]},
                "name"
            )
            
            if not bpjs_summary:
                # Create new BPJS Payment Summary
                try:
                    bpjs_summary_doc = frappe.new_doc("BPJS Payment Summary")
                    bpjs_summary_doc.company = self.company
                    bpjs_summary_doc.year = year
                    bpjs_summary_doc.month = month
                    
                    # Set title if field exists
                    if hasattr(bpjs_summary_doc, 'month_year_title'):
                        bpjs_summary_doc.month_year_title = f"{month:02d}-{year}"
                        
                    # Check if employee_details field exists
                    if not hasattr(bpjs_summary_doc, 'employee_details'):
                        frappe.throw(_("BPJS Payment Summary structure is invalid. missing employee_details child table."))
                    
                    # Create first employee detail
                    bpjs_summary_doc.append("employee_details", {
                        "employee": self.employee,
                        "employee_name": self.employee_name,
                        "salary_slip": self.name,
                        "jht_employee": bpjs_data["jht_employee"],
                        "jp_employee": bpjs_data["jp_employee"],
                        "kesehatan_employee": bpjs_data["kesehatan_employee"],
                        "jht_employer": jht_employer,
                        "jp_employer": jp_employer,
                        "jkk": jkk,
                        "jkm": jkm,
                        "kesehatan_employer": kesehatan_employer
                    })
                    
                    bpjs_summary_doc.insert(ignore_permissions=True)
                except Exception as e:
                    frappe.throw(_("Error creating BPJS Payment Summary: {0}").format(str(e)))
                
            else:
                # Update existing BPJS Payment Summary
                try:
                    bpjs_summary_doc = frappe.get_doc("BPJS Payment Summary", bpjs_summary)
                    
                    # Check if employee_details field exists
                    if not hasattr(bpjs_summary_doc, 'employee_details'):
                        frappe.throw(_("BPJS Payment Summary structure is invalid. missing employee_details child table."))
                    
                    # Check if employee already exists
                    employee_exists = False
                    for detail in bpjs_summary_doc.employee_details:
                        if detail.employee == self.employee:
                            # Update existing employee
                            detail.salary_slip = self.name
                            detail.jht_employee = bpjs_data["jht_employee"]
                            detail.jp_employee = bpjs_data["jp_employee"] 
                            detail.kesehatan_employee = bpjs_data["kesehatan_employee"]
                            detail.jht_employer = jht_employer
                            detail.jp_employer = jp_employer
                            detail.jkk = jkk
                            detail.jkm = jkm
                            detail.kesehatan_employer = kesehatan_employer
                            employee_exists = True
                            break
                    
                    if not employee_exists:
                        # Add new employee
                        bpjs_summary_doc.append("employee_details", {
                            "employee": self.employee,
                            "employee_name": self.employee_name,
                            "salary_slip": self.name,
                            "jht_employee": bpjs_data["jht_employee"],
                            "jp_employee": bpjs_data["jp_employee"],
                            "kesehatan_employee": bpjs_data["kesehatan_employee"],
                            "jht_employer": jht_employer,
                            "jp_employer": jp_employer,
                            "jkk": jkk,
                            "jkm": jkm,
                            "kesehatan_employer": kesehatan_employer
                        })
                    
                    # Save changes
                    bpjs_summary_doc.save(ignore_permissions=True)
                except Exception as e:
                    frappe.throw(_("Error updating BPJS Payment Summary: {0}").format(str(e)))
            
        except Exception as e:
            frappe.log_error(
                f"Error creating/updating BPJS Payment Summary for {self.name}: {str(e)}",
                "BPJS Summary Error"
            )
            frappe.throw(_("Error creating/updating BPJS Payment Summary: {0}").format(str(e)))
            
    def create_pph_ter_table(self):
        """Create or update PPh TER Table entry if using TER method"""
        try:
            # Only proceed if using TER
            if not getattr(self, 'is_using_ter', 0):
                return
                
            # Check if PPh TER Table DocType exists
            if not frappe.db.exists("DocType", "PPh TER Table"):
                frappe.msgprint(_("PPh TER Table DocType not found. Cannot create TER entry."))
                return
            
            # Determine year and month from salary slip
            end_date = getdate(self.end_date)
            month = end_date.month
            year = end_date.year
            
            # Get PPh 21 amount
            pph21_amount = 0
            for deduction in self.deductions:
                if deduction.salary_component == "PPh 21":
                    pph21_amount = flt(deduction.amount)
                    break
            
            # Get employee status pajak
            employee = frappe.get_doc("Employee", self.employee)
            status_pajak = "TK0"  # Default
            
            if hasattr(employee, 'status_pajak') and employee.status_pajak:
                status_pajak = employee.status_pajak
            
            # Check if PPh TER Table exists for this period
            ter_table = frappe.db.get_value(
                "PPh TER Table", 
                {"company": self.company, "year": year, "month": month, "docstatus": ["!=", 2]},
                "name"
            )
            
            if not ter_table:
                # Create new PPh TER Table
                try:
                    ter_table_doc = frappe.new_doc("PPh TER Table")
                    ter_table_doc.company = self.company
                    ter_table_doc.year = year
                    ter_table_doc.month = month
                    
                    # Set title if field exists
                    if hasattr(ter_table_doc, 'month_year_title'):
                        ter_table_doc.month_year_title = f"{month:02d}-{year}"
                    
                    # Check if employee_details field exists
                    if not hasattr(ter_table_doc, 'employee_details'):
                        frappe.throw(_("PPh TER Table structure is invalid. missing employee_details child table."))
                    
                    # Create first employee detail
                    ter_table_doc.append("employee_details", {
                        "employee": self.employee,
                        "employee_name": self.employee_name,
                        "status_pajak": status_pajak,
                        "salary_slip": self.name,
                        "gross_income": self.gross_pay,
                        "ter_rate": getattr(self, 'ter_rate', 0),
                        "pph21_amount": pph21_amount
                    })
                    
                    ter_table_doc.insert(ignore_permissions=True)
                except Exception as e:
                    frappe.throw(_("Error creating PPh TER Table: {0}").format(str(e)))
                
            else:
                # Update existing PPh TER Table
                try:
                    ter_table_doc = frappe.get_doc("PPh TER Table", ter_table)
                    
                    # Check if employee_details field exists
                    if not hasattr(ter_table_doc, 'employee_details'):
                        frappe.throw(_("PPh TER Table structure is invalid. Missing employee_details child table."))
                    
                    # Check if employee already exists
                    employee_exists = False
                    for detail in ter_table_doc.employee_details:
                        if detail.employee == self.employee:
                            # Update existing employee
                            detail.status_pajak = status_pajak
                            detail.salary_slip = self.name
                            detail.gross_income = self.gross_pay
                            detail.ter_rate = getattr(self, 'ter_rate', 0)
                            detail.pph21_amount = pph21_amount
                            employee_exists = True
                            break
                    
                    if not employee_exists:
                        # Add new employee
                        ter_table_doc.append("employee_details", {
                            "employee": self.employee,
                            "employee_name": self.employee_name,
                            "status_pajak": status_pajak,
                            "salary_slip": self.name,
                            "gross_income": self.gross_pay,
                            "ter_rate": getattr(self, 'ter_rate', 0),
                            "pph21_amount": pph21_amount
                        })
                    
                    # Save changes
                    ter_table_doc.save(ignore_permissions=True)
                except Exception as e:
                    frappe.throw(_("Error updating PPh TER Table: {0}").format(str(e)))
                    
        except Exception as e:
            frappe.log_error(
                f"Error creating/updating PPh TER Table for {self.name}: {str(e)}",
                "TER Table Error"
            )
            frappe.throw(_("Error creating/updating PPh TER Table: {0}").format(str(e)))