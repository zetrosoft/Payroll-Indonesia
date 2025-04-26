# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-26 17:25:45 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt

def validate_salary_slip(doc, method=None):
    """Additional validation for salary slip"""
    # Validate employee is specified
    if not doc.employee:
        frappe.throw(_("Employee is mandatory for Salary Slip"))
    
    # Initialize custom fields
    if not hasattr(doc, 'is_final_gabung_suami'):
        doc.is_final_gabung_suami = 0
    if not hasattr(doc, 'koreksi_pph21'):
        doc.koreksi_pph21 = 0
    if not hasattr(doc, 'payroll_note'):
        doc.payroll_note = ""
    if not hasattr(doc, 'biaya_jabatan'):
        doc.biaya_jabatan = 0
    if not hasattr(doc, 'netto'):
        doc.netto = 0
    if not hasattr(doc, 'total_bpjs'):
        doc.total_bpjs = 0
    if not hasattr(doc, 'is_using_ter'):
        doc.is_using_ter = 0
    if not hasattr(doc, 'ter_rate'):
        doc.ter_rate = 0
    
    # Check if all required components exist in salary slip
    required_components = {
        "earnings": ["Gaji Pokok"],
        "deductions": [
            "BPJS JHT Employee",
            "BPJS JP Employee", 
            "BPJS Kesehatan Employee",
            "PPh 21"
        ]
    }
    
    for component_type, components in required_components.items():
        components_in_slip = [d.salary_component for d in getattr(doc, component_type)]
        for component in components:
            if component not in components_in_slip:
                # Add the missing component if it exists in the system
                if frappe.db.exists("Salary Component", component):
                    try:
                        # Get abbr from component
                        component_doc = frappe.get_doc("Salary Component", component)
                        
                        # Create a new row
                        doc.append(component_type, {
                            "salary_component": component,
                            "abbr": component_doc.salary_component_abbr,
                            "amount": 0
                        })
                        
                        frappe.msgprint(f"Added missing component: {component}")
                    except Exception as e:
                        frappe.log_error(f"Error adding component {component}: {str(e)}")

def on_submit_salary_slip(doc, method=None):
    """Actions after salary slip is submitted"""
    # Update employee YTD tax paid
    update_employee_ytd_tax(doc)
    
    # Log payroll event
    log_payroll_event(doc)

def update_employee_ytd_tax(doc):
    """Update employee's year-to-date tax information"""
    try:
        # Get the current year
        year = doc.end_date.year
        
        # Get the PPh 21 amount
        pph21_amount = 0
        for deduction in doc.deductions:
            if deduction.salary_component == "PPh 21":
                pph21_amount = flt(deduction.amount)
                break
        
        if pph21_amount > 0 or getattr(doc, 'is_using_ter', 0):
            # Check if we already have a record for this employee/year combination
            if frappe.db.exists({
                "doctype": "Employee Tax Summary",
                "employee": doc.employee,
                "year": year
            }):
                # Update existing record
                tax_record = frappe.get_doc("Employee Tax Summary", {
                    "employee": doc.employee,
                    "year": year
                })
                tax_record.ytd_tax = flt(tax_record.ytd_tax) + pph21_amount
                
                # Update TER information if applicable
                if getattr(doc, 'is_using_ter', 0) and getattr(doc, 'ter_rate', 0) > 0:
                    tax_record.is_using_ter = 1
                    tax_record.ter_rate = getattr(doc, 'ter_rate', 0)
                
                tax_record.save(ignore_permissions=True)
            else:
                # Create a new record
                tax_record = frappe.new_doc("Employee Tax Summary")
                tax_record.employee = doc.employee
                tax_record.employee_name = doc.employee_name
                tax_record.year = year
                tax_record.ytd_tax = pph21_amount
                
                # Set TER information if applicable
                if getattr(doc, 'is_using_ter', 0) and getattr(doc, 'ter_rate', 0) > 0:
                    tax_record.is_using_ter = 1
                    tax_record.ter_rate = getattr(doc, 'ter_rate', 0)
                
                tax_record.insert(ignore_permissions=True)
                
            frappe.db.commit()
    except Exception as e:
        frappe.log_error(f"Error updating YTD tax for {doc.employee}: {str(e)}")

def log_payroll_event(doc):
    """Log payroll processing event"""
    try:
        # Record the payroll processing event
        log = frappe.new_doc("Payroll Log")
        log.employee = doc.employee
        log.employee_name = doc.employee_name
        log.salary_slip = doc.name
        log.posting_date = doc.posting_date
        log.start_date = doc.start_date
        log.end_date = doc.end_date
        log.gross_pay = doc.gross_pay
        log.net_pay = doc.net_pay
        log.total_deduction = doc.total_deduction
        
        # Add TER information if applicable
        if getattr(doc, 'is_using_ter', 0):
            log.calculation_method = "TER"
            log.ter_rate = getattr(doc, 'ter_rate', 0)
        else:
            log.calculation_method = "Progressive"
            
        # Add correction information if December
        if doc.end_date.month == 12 and getattr(doc, 'koreksi_pph21', 0) != 0:
            log.has_correction = 1
            log.correction_amount = getattr(doc, 'koreksi_pph21', 0)
            
        log.status = "Success"
        log.notes = doc.payroll_note[:500] if doc.payroll_note else ""
        log.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(f"Error logging payroll event for {doc.employee}: {str(e)}")

# Fungsi baru yang ditambahkan
def after_insert_salary_slip(doc, method=None):
    """
    Hook yang dijalankan setelah Salary Slip dibuat
    
    Args:
        doc: Object dari Salary Slip yang baru dibuat
        method: Metode yang memanggil hook (tidak digunakan)
    """
    try:
        # Pastikan field Payroll Indonesia diinisialisasi dengan benar
        initialize_custom_fields(doc)
        
        # Log bahwa Salary Slip telah dibuat
        frappe.logger().debug(f"Salary Slip {doc.name} created for employee {doc.employee}")
        
        # Tambahkan ke notifikasi jika aplikasi mendukung
        add_to_payroll_notifications(doc)
        
    except Exception as e:
        frappe.log_error(
            f"Error in after_insert_salary_slip for {doc.name}: {str(e)}", 
            "Salary Slip Hook Error"
        )

def initialize_custom_fields(doc):
    """Inisialisasi field custom Payroll Indonesia"""
    if not hasattr(doc, 'is_final_gabung_suami') or doc.is_final_gabung_suami is None:
        doc.is_final_gabung_suami = 0
        
    if not hasattr(doc, 'koreksi_pph21') or doc.koreksi_pph21 is None:
        doc.koreksi_pph21 = 0
        
    if not hasattr(doc, 'payroll_note') or doc.payroll_note is None:
        doc.payroll_note = ""
        
    if not hasattr(doc, 'biaya_jabatan') or doc.biaya_jabatan is None:
        doc.biaya_jabatan = 0
        
    if not hasattr(doc, 'netto') or doc.netto is None:
        doc.netto = 0
        
    if not hasattr(doc, 'total_bpjs') or doc.total_bpjs is None:
        doc.total_bpjs = 0
        
    if not hasattr(doc, 'is_using_ter') or doc.is_using_ter is None:
        doc.is_using_ter = 0
        
    if not hasattr(doc, 'ter_rate') or doc.ter_rate is None:
        doc.ter_rate = 0
        
    # Update database jika diperlukan
    has_changed = False
    for field in ['is_final_gabung_suami', 'koreksi_pph21', 'payroll_note', 
                 'biaya_jabatan', 'netto', 'total_bpjs', 'is_using_ter', 'ter_rate']:
        if doc.has_value_changed(field):
            has_changed = True
            
    if has_changed:
        doc.db_update()

def add_to_payroll_notifications(doc):
    """Menambahkan entri ke notifikasi payroll jika fitur tersedia"""
    # Cek apakah doctype Payroll Notification ada
    if not frappe.db.exists('DocType', 'Payroll Notification'):
        return
        
    try:
        notification = frappe.new_doc("Payroll Notification")
        notification.employee = doc.employee
        notification.employee_name = doc.employee_name
        notification.salary_slip = doc.name
        notification.posting_date = doc.posting_date or frappe.utils.today()
        notification.amount = doc.net_pay or 0
        notification.status = "Draft"
        notification.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(
            f"Failed to create payroll notification for {doc.name}: {str(e)}",
            "Payroll Notification Error"
        )