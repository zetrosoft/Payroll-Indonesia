# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 08:05:54 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate
from erpnext.payroll.doctype.salary_slip.salary_slip import SalarySlip

# Import functions from modular files
from payroll_indonesia.override.salary_slip.base import get_formatted_currency, get_component_amount, update_component_amount
from payroll_indonesia.override.salary_slip.tax_calculator import calculate_tax_components
from payroll_indonesia.override.salary_slip.bpjs_calculator import calculate_bpjs_components
from payroll_indonesia.override.salary_slip.ter_calculator import calculate_monthly_pph_with_ter, should_use_ter_method, get_ter_rate
from payroll_indonesia.override.salary_slip.tax_summary_creator import create_tax_summary
from payroll_indonesia.override.salary_slip.bpjs_summary_creator import create_bpjs_payment_summary, create_bpjs_payment_component
from payroll_indonesia.override.salary_slip.ter_table_creator import create_pph_ter_table

class IndonesiaPayrollSalarySlip(SalarySlip):
    """
    Enhanced Salary Slip for Indonesian Payroll
    Extends erpnext.payroll.doctype.salary_slip.salary_slip.SalarySlip
    """
    def validate(self):
        """Validate and calculate payroll Indonesia components"""
        try:
            # Call parent class validate method first
            super(IndonesiaPayrollSalarySlip, self).validate()
            
            # Initialize additional fields if they don't exist
            self.initialize_payroll_fields()
            
            # Get employee document with validation
            employee = self.get_employee_doc()
            
            # Calculate basic salary for BPJS calculations
            gaji_pokok = self.get_gaji_pokok()
            
            # Calculate BPJS components
            calculate_bpjs_components(self, employee, gaji_pokok)
            
            # Calculate Tax components
            calculate_tax_components(self, employee)
            
            # Generate NPWP and KTP data
            self.generate_tax_id_data(employee)
            
        except Exception as e:
            frappe.log_error(
                f"Error in Salary Slip validation for {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Slip Validation Error"
            )
            frappe.throw(_("Error in Salary Slip validation: {0}").format(str(e)))
    
    def on_submit(self):
        """Create related documents on submit"""
        try:
            # Call parent class on_submit first
            super(IndonesiaPayrollSalarySlip, self).on_submit()
            
            # Create tax summary document
            create_tax_summary(self)
            
            # Create BPJS document if any BPJS components exist
            bpjs_components = [
                self.get_component_amount("BPJS JHT Employee", "deductions"),
                self.get_component_amount("BPJS JP Employee", "deductions"),
                self.get_component_amount("BPJS Kesehatan Employee", "deductions")
            ]
            
            if any(component > 0 for component in bpjs_components):
                bpjs_summary = create_bpjs_payment_summary(self)
                # Now create the BPJS Payment Component if setting enabled
                try:
                    bpjs_settings = frappe.get_single("BPJS Settings")
                    if hasattr(bpjs_settings, 'auto_create_component') and bpjs_settings.auto_create_component:
                        create_bpjs_payment_component(self)
                except Exception:
                    pass  # Silently skip if setting not found
                
            # Create PPh TER Table if using TER method
            if getattr(self, 'is_using_ter', 0):
                create_pph_ter_table(self)
                
        except Exception as e:
            frappe.log_error(
                f"Error in Salary Slip on_submit for {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Slip Submit Error"
            )
            frappe.msgprint(_("Warning: Error creating related documents: {0}").format(str(e)))
    
    def on_cancel(self):
        """Handle document cancellation"""
        try:
            # Call parent class on_cancel first
            super(IndonesiaPayrollSalarySlip, self).on_cancel()
            
            # Update related documents
            self.update_related_documents_on_cancel()
            
        except Exception as e:
            frappe.log_error(
                f"Error in Salary Slip on_cancel for {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Slip Cancel Error"
            )
            frappe.msgprint(_("Warning: Error updating related documents on cancel: {0}").format(str(e)))
    
    def update_related_documents_on_cancel(self):
        """Update related documents when canceling salary slip"""
        month = getdate(self.end_date).month
        year = getdate(self.end_date).year
        
        # Remove from BPJS Payment Summary
        self.update_bpjs_summary_on_cancel(month, year)
        
        # Remove from PPh TER Table
        self.update_ter_table_on_cancel(month, year)
        
        # Remove from Employee Tax Summary
        self.update_tax_summary_on_cancel(year)
        
        # Delete any BPJS Payment Components related to this salary slip
        self.delete_related_bpjs_components()
    
    def delete_related_bpjs_components(self):
        """Delete BPJS Payment Components created for this salary slip"""
        try:
            # Find related BPJS Payment Components
            components = frappe.get_all(
                "BPJS Payment Component",
                filters={"salary_slip": self.name, "docstatus": 0},  # Only drafts
                pluck="name"
            )
            
            # Delete each component
            for component in components:
                try:
                    frappe.delete_doc("BPJS Payment Component", component, force=False)
                    frappe.msgprint(_("Deleted BPJS Payment Component {0}").format(component))
                except Exception as e:
                    frappe.log_error(
                        f"Error deleting BPJS Payment Component {component}: {str(e)}",
                        "BPJS Component Delete Error"
                    )
                    frappe.msgprint(_(
                        "Could not delete BPJS Payment Component {0}: {1}"
                    ).format(component, str(e)))
        except Exception as e:
            frappe.log_error(
                f"Error finding BPJS Payment Components for {self.name}: {str(e)}",
                "BPJS Component Query Error"
            )
            frappe.msgprint(_("Error finding related BPJS Payment Components: {0}").format(str(e)))
    
    def update_bpjs_summary_on_cancel(self, month, year):
        """Update BPJS Payment Summary when salary slip is cancelled"""
        try:
            # Find BPJS Payment Summary for this period
            bpjs_summary = frappe.db.get_value(
                "BPJS Payment Summary",
                {"company": self.company, "year": year, "month": month, "docstatus": ["!=", 2]},
                "name"
            )
            
            if not bpjs_summary:
                return
                
            # Get document
            bpjs_doc = frappe.get_doc("BPJS Payment Summary", bpjs_summary)
            
            # Check if it can be modified
            if bpjs_doc.docstatus > 0:
                frappe.msgprint(_(
                    "BPJS Payment Summary {0} has already been submitted and cannot be updated."
                ).format(bpjs_summary))
                return
                
            # Find and remove our employee
            if hasattr(bpjs_doc, 'employee_details'):
                to_remove = []
                for i, d in enumerate(bpjs_doc.employee_details):
                    if hasattr(d, 'salary_slip') and d.salary_slip == self.name:
                        to_remove.append(d)
                        
                for d in to_remove:
                    bpjs_doc.employee_details.remove(d)
                    
                # Save if we removed any entries
                if len(to_remove) > 0:
                    bpjs_doc.save()
                    frappe.msgprint(_("Removed entry from BPJS Payment Summary {0}").format(bpjs_summary))
                    
        except Exception as e:
            frappe.log_error(
                f"Error updating BPJS Summary on cancel: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Summary Cancel Error"
            )
            frappe.msgprint(_("Error updating BPJS Payment Summary: {0}").format(str(e)))
    
    def update_ter_table_on_cancel(self, month, year):
        """Update PPh TER Table when salary slip is cancelled"""
        try:
            # Only proceed if using TER
            if not getattr(self, 'is_using_ter', 0):
                return
                
            # Find TER Table for this period
            ter_table = frappe.db.get_value(
                "PPh TER Table",
                {"company": self.company, "year": year, "month": month, "docstatus": ["!=", 2]},
                "name"
            )
            
            if not ter_table:
                return
                
            # Get document
            ter_doc = frappe.get_doc("PPh TER Table", ter_table)
            
            # Check if it can be modified
            if ter_doc.docstatus > 0:
                frappe.msgprint(_(
                    "PPh TER Table {0} has already been submitted and cannot be updated."
                ).format(ter_table))
                return
                
            # Find and remove our employee
            if hasattr(ter_doc, 'details'):
                to_remove = []
                for i, d in enumerate(ter_doc.details):
                    if d.employee == self.employee:
                        to_remove.append(d)
                        
                for d in to_remove:
                    ter_doc.details.remove(d)
                    
                # Save if we removed any entries
                if len(to_remove) > 0:
                    ter_doc.save()
                    frappe.msgprint(_("Removed entry from PPh TER Table {0}").format(ter_table))
                    
        except Exception as e:
            frappe.log_error(
                f"Error updating TER Table on cancel: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "TER Table Cancel Error"
            )
            frappe.msgprint(_("Error updating PPh TER Table: {0}").format(str(e)))
    
    def update_tax_summary_on_cancel(self, year):
        """Update Employee Tax Summary when salary slip is cancelled"""
        try:
            # Find Tax Summary for this employee and year
            tax_summary = frappe.db.get_value(
                "Employee Tax Summary",
                {"employee": self.employee, "year": year},
                "name"
            )
            
            if not tax_summary:
                return
                
            # Get document
            tax_doc = frappe.get_doc("Employee Tax Summary", tax_summary)
                
            # Find and update our month
            if hasattr(tax_doc, 'monthly_details'):
                month = getdate(self.end_date).month
                changed = False
                
                for d in tax_doc.monthly_details:
                    if hasattr(d, 'month') and d.month == month and hasattr(d, 'salary_slip') and d.salary_slip == self.name:
                        # Zero out the values for this month
                        d.gross_pay = 0
                        d.bpjs_deductions = 0
                        d.tax_amount = 0
                        d.salary_slip = None
                        changed = True
                        
                # Recalculate YTD if we made changes
                if changed:
                    # Recalculate YTD
                    total_tax = 0
                    if tax_doc.monthly_details:
                        for m in tax_doc.monthly_details:
                            if hasattr(m, 'tax_amount'):
                                total_tax += flt(m.tax_amount)
                                
                    tax_doc.ytd_tax = total_tax
                    tax_doc.save()
                    frappe.msgprint(_("Updated Employee Tax Summary {0}").format(tax_summary))
                    
        except Exception as e:
            frappe.log_error(
                f"Error updating Tax Summary on cancel: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Tax Summary Cancel Error"
            )
            frappe.msgprint(_("Error updating Employee Tax Summary: {0}").format(str(e)))
    
    # Helper methods
    def initialize_payroll_fields(self):
        """Initialize additional payroll fields"""
        if not hasattr(self, 'biaya_jabatan') or self.biaya_jabatan is None:
            self.biaya_jabatan = 0
            
        if not hasattr(self, 'netto') or self.netto is None:
            self.netto = 0
            
        if not hasattr(self, 'total_bpjs') or self.total_bpjs is None:
            self.total_bpjs = 0
            
        if not hasattr(self, 'is_using_ter') or self.is_using_ter is None:
            self.is_using_ter = 0
            
        if not hasattr(self, 'ter_rate') or self.ter_rate is None:
            self.ter_rate = 0
            
        if not hasattr(self, 'koreksi_pph21') or self.koreksi_pph21 is None:
            self.koreksi_pph21 = 0
            
        if not hasattr(self, 'payroll_note') or self.payroll_note is None:
            self.payroll_note = ""
            
        if not hasattr(self, 'npwp') or self.npwp is None:
            self.npwp = ""
            
        if not hasattr(self, 'ktp') or self.ktp is None:
            self.ktp = ""
    
    def get_employee_doc(self):
        """Get employee document with validation"""
        if not self.employee:
            frappe.throw(_("Employee is mandatory for salary slip"))
            
        try:
            employee_doc = frappe.get_doc("Employee", self.employee)
            return employee_doc
        except Exception as e:
            frappe.throw(_("Error retrieving employee {0}: {1}").format(self.employee, str(e)))
    
    def get_gaji_pokok(self):
        """Get gaji pokok (basic salary) from earnings"""
        gaji_pokok = 0
        
        # Find Basic component
        for earning in self.earnings:
            if earning.salary_component == "Basic":
                gaji_pokok = flt(earning.amount)
                break
                
        # If Basic not found, use first component
        if gaji_pokok == 0 and len(self.earnings) > 0:
            gaji_pokok = flt(self.earnings[0].amount)
            
        return gaji_pokok
    
    def generate_tax_id_data(self, employee):
        """Generate NPWP and KTP information from employee data"""
        try:
            # Get NPWP from employee
            if hasattr(employee, 'npwp'):
                self.npwp = employee.npwp
                
            # Get KTP from employee
            if hasattr(employee, 'ktp'):
                self.ktp = employee.ktp
                
        except Exception as e:
            frappe.log_error(
                f"Error generating tax ID data for {self.name}: {str(e)}",
                "Tax ID Data Error"
            )
            frappe.msgprint(_("Error generating tax ID data: {0}").format(str(e)))
    
    def get_component_amount(self, component_name, component_type):
        """Wrapper for component amount function"""
        return get_component_amount(self, component_name, component_type)
        
    def update_component_amount(self, component_name, amount, component_type):
        """Wrapper for update component function"""
        return update_component_amount(self, component_name, amount, component_type)

# Override the standard SalarySlip class with our enhanced version
frappe.model.document.get_controller("Salary Slip")._controller = IndonesiaPayrollSalarySlip