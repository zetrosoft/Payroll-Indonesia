# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-26 18:37:42 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate

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
    
    # Update BPJS Payment Summary
    update_bpjs_payment_summary(doc)
    
    # Update PPh TER Table if using TER
    if getattr(doc, 'is_using_ter', 0):
        update_pph_ter_table(doc)

def update_employee_ytd_tax(doc):
    """Update employee's year-to-date tax information"""
    try:
        # Get the current year
        year = doc.end_date.year
        month = doc.end_date.month
        
        # Get the PPh 21 amount
        pph21_amount = 0
        for deduction in doc.deductions:
            if deduction.salary_component == "PPh 21":
                pph21_amount = flt(deduction.amount)
                break
        
        # Get BPJS components from salary slip
        bpjs_deductions = 0
        for deduction in doc.deductions:
            if deduction.salary_component in ["BPJS JHT Employee", "BPJS JP Employee", "BPJS Kesehatan Employee"]:
                bpjs_deductions += flt(deduction.amount)
        
        # Check if we already have a record for this employee/year combination
        existing_tax_summary = frappe.db.get_value("Employee Tax Summary", 
            {"employee": doc.employee, "year": year}, "name")
        
        if existing_tax_summary:
            # Get existing record and update it
            tax_record = frappe.get_doc("Employee Tax Summary", existing_tax_summary)
            
            # Append monthly detail
            has_month = False
            for m in tax_record.monthly_details:
                if m.month == month:
                    m.gross_pay = doc.gross_pay
                    m.bpjs_deductions = bpjs_deductions
                    m.tax_amount = pph21_amount
                    m.salary_slip = doc.name
                    m.is_using_ter = 1 if getattr(doc, 'is_using_ter', 0) else 0
                    m.ter_rate = getattr(doc, 'ter_rate', 0) if hasattr(doc, 'ter_rate') else 0
                    has_month = True
                    break
            
            if not has_month:
                tax_record.append("monthly_details", {
                    "month": month,
                    "salary_slip": doc.name,
                    "gross_pay": doc.gross_pay,
                    "bpjs_deductions": bpjs_deductions,
                    "tax_amount": pph21_amount,
                    "is_using_ter": 1 if getattr(doc, 'is_using_ter', 0) else 0,
                    "ter_rate": getattr(doc, 'ter_rate', 0) if hasattr(doc, 'ter_rate') else 0
                })
            
            # Recalculate YTD tax
            total_tax = 0
            for m in tax_record.monthly_details:
                total_tax += flt(m.tax_amount)
            
            tax_record.ytd_tax = total_tax
            
            # Set title if empty
            if not tax_record.title:
                tax_record.title = f"{doc.employee_name} - {year}"
                
            # Set TER information at year level if applicable
            if getattr(doc, 'is_using_ter', 0) and hasattr(tax_record, 'is_using_ter'):
                tax_record.is_using_ter = 1
                if hasattr(tax_record, 'ter_rate'):
                    tax_record.ter_rate = getattr(doc, 'ter_rate', 0)
                
            tax_record.save(ignore_permissions=True)
            frappe.db.commit()
        else:
            # Create a new Employee Tax Summary
            tax_record = frappe.new_doc("Employee Tax Summary")
            tax_record.employee = doc.employee
            tax_record.employee_name = doc.employee_name
            tax_record.year = year
            tax_record.ytd_tax = pph21_amount
            tax_record.title = f"{doc.employee_name} - {year}"
            
            # Set TER information at year level if applicable
            if getattr(doc, 'is_using_ter', 0) and hasattr(tax_record, 'is_using_ter'):
                tax_record.is_using_ter = 1
                if hasattr(tax_record, 'ter_rate'):
                    tax_record.ter_rate = getattr(doc, 'ter_rate', 0)
            
            # Add first monthly detail
            tax_record.append("monthly_details", {
                "month": month,
                "salary_slip": doc.name,
                "gross_pay": doc.gross_pay,
                "bpjs_deductions": bpjs_deductions,
                "tax_amount": pph21_amount,
                "is_using_ter": 1 if getattr(doc, 'is_using_ter', 0) else 0,
                "ter_rate": getattr(doc, 'ter_rate', 0) if hasattr(doc, 'ter_rate') else 0
            })
            
            tax_record.insert(ignore_permissions=True)
            frappe.db.commit()
                
    except Exception as e:
        frappe.log_error(f"Error updating YTD tax for {doc.employee}: {str(e)}", 
                        "Employee Tax Summary Error")

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

def update_bpjs_payment_summary(doc):
    """Update BPJS Payment Summary based on submitted salary slip"""
    try:
        # Determine year and month from salary slip
        end_date = getdate(doc.end_date)
        month = end_date.month
        year = end_date.year
        
        # Get BPJS components from salary slip
        bpjs_data = {
            "jht_employee": 0,
            "jp_employee": 0,
            "kesehatan_employee": 0
        }
        
        # Get employee components
        for deduction in doc.deductions:
            if deduction.salary_component == "BPJS JHT Employee":
                bpjs_data["jht_employee"] = flt(deduction.amount)
            elif deduction.salary_component == "BPJS JP Employee":
                bpjs_data["jp_employee"] = flt(deduction.amount)
            elif deduction.salary_component == "BPJS Kesehatan Employee":
                bpjs_data["kesehatan_employee"] = flt(deduction.amount)
        
        # Get BPJS Settings for employer calculations
        bpjs_settings = frappe.get_single("BPJS Settings")
        
        # Calculate employer components
        # JHT Employer (3.7%)
        jht_employer = doc.gross_pay * (bpjs_settings.jht_employer_percent / 100)
        
        # JP Employer (2%)
        jp_salary = min(doc.gross_pay, bpjs_settings.jp_max_salary)
        jp_employer = jp_salary * (bpjs_settings.jp_employer_percent / 100)
        
        # JKK (0.24% - 1.74% depending on risk)
        jkk = doc.gross_pay * (bpjs_settings.jkk_percent / 100)
        
        # JKM (0.3%)
        jkm = doc.gross_pay * (bpjs_settings.jkm_percent / 100)
        
        # Kesehatan Employer (4%)
        kesehatan_salary = min(doc.gross_pay, bpjs_settings.kesehatan_max_salary)
        kesehatan_employer = kesehatan_salary * (bpjs_settings.kesehatan_employer_percent / 100)
        
        # Check if BPJS Payment Summary exists for this period
        bpjs_summary = frappe.db.get_value(
            "BPJS Payment Summary",
            {"company": doc.company, "year": year, "month": month, "docstatus": ["!=", 2]},
            "name"
        )
        
        if not bpjs_summary:
            # Create new BPJS Payment Summary
            bpjs_summary_doc = frappe.new_doc("BPJS Payment Summary")
            bpjs_summary_doc.company = doc.company
            bpjs_summary_doc.year = year
            bpjs_summary_doc.month = month
            bpjs_summary_doc.month_year_title = f"{month:02d}-{year}"
            
            # Create first employee detail
            bpjs_summary_doc.append("employee_details", {
                "employee": doc.employee,
                "employee_name": doc.employee_name,
                "salary_slip": doc.name,
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
            frappe.db.commit()
            
        else:
            # Update existing BPJS Payment Summary
            bpjs_summary_doc = frappe.get_doc("BPJS Payment Summary", bpjs_summary)
            
            # Check if employee already exists
            employee_exists = False
            for detail in bpjs_summary_doc.employee_details:
                if detail.employee == doc.employee:
                    # Update existing employee
                    detail.salary_slip = doc.name
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
                    "employee": doc.employee,
                    "employee_name": doc.employee_name,
                    "salary_slip": doc.name,
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
            frappe.db.commit()
        
    except Exception as e:
        frappe.log_error(f"Error updating BPJS Payment Summary for {doc.employee}: {str(e)}", "BPJS Update Error")

def update_pph_ter_table(doc):
    """Update PPh TER Table based on submitted salary slip"""
    try:
        # Only proceed if using TER
        if not getattr(doc, 'is_using_ter', 0):
            return
            
        # Determine year and month from salary slip
        end_date = getdate(doc.end_date)
        month = end_date.month
        year = end_date.year
        
        # Get PPh 21 amount
        pph21_amount = 0
        for deduction in doc.deductions:
            if deduction.salary_component == "PPh 21":
                pph21_amount = flt(deduction.amount)
                break
        
        # Get employee status pajak
        employee = frappe.get_doc("Employee", doc.employee)
        status_pajak = getattr(employee, 'status_pajak', 'TK0')
        
        # Check if PPh TER Table exists for this period
        ter_table = frappe.db.get_value(
            "PPh TER Table", 
            {"company": doc.company, "year": year, "month": month, "docstatus": ["!=", 2]},
            "name"
        )
        
        if not ter_table:
            # Create new PPh TER Table
            ter_table_doc = frappe.new_doc("PPh TER Table")
            ter_table_doc.company = doc.company
            ter_table_doc.year = year
            ter_table_doc.month = month
            ter_table_doc.month_year_title = f"{month:02d}-{year}"
            
            # Create first employee detail
            ter_table_doc.append("employee_details", {
                "employee": doc.employee,
                "employee_name": doc.employee_name,
                "status_pajak": status_pajak,
                "salary_slip": doc.name,
                "gross_income": doc.gross_pay,
                "ter_rate": getattr(doc, 'ter_rate', 0),
                "pph21_amount": pph21_amount
            })
            
            ter_table_doc.insert(ignore_permissions=True)
            frappe.db.commit()
            
        else:
            # Update existing PPh TER Table
            ter_table_doc = frappe.get_doc("PPh TER Table", ter_table)
            
            # Check if employee already exists
            employee_exists = False
            for detail in ter_table_doc.employee_details:
                if detail.employee == doc.employee:
                    # Update existing employee
                    detail.status_pajak = status_pajak
                    detail.salary_slip = doc.name
                    detail.gross_income = doc.gross_pay
                    detail.ter_rate = getattr(doc, 'ter_rate', 0)
                    detail.pph21_amount = pph21_amount
                    employee_exists = True
                    break
            
            if not employee_exists:
                # Add new employee
                ter_table_doc.append("employee_details", {
                    "employee": doc.employee,
                    "employee_name": doc.employee_name,
                    "status_pajak": status_pajak,
                    "salary_slip": doc.name,
                    "gross_income": doc.gross_pay,
                    "ter_rate": getattr(doc, 'ter_rate', 0),
                    "pph21_amount": pph21_amount
                })
            
            # Save changes
            ter_table_doc.save(ignore_permissions=True)
            frappe.db.commit()
        
    except Exception as e:
        frappe.log_error(f"Error updating PPh TER Table for {doc.employee}: {str(e)}", "PPh TER Update Error")

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