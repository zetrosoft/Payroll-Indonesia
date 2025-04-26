import frappe
from frappe.utils import cstr

def execute():
    """Patch to fix company field validation during migration"""
    try:
        # Cek apakah kolom is_default ada di Income Tax Slab
        has_is_default = check_column_exists("Income Tax Slab", "is_default")
        
        # Ambil semua Salary Structure dengan company=%
        salary_structures = frappe.get_all("Salary Structure", 
                                        filters={"company": "%"}, 
                                        fields=["name", "docstatus"])
        
        if not salary_structures:
            return
            
        # Dapatkan Income Tax Slab untuk IDR
        tax_slab = None
        if has_is_default:
            # Jika kolom is_default ada
            tax_slab = frappe.db.get_value("Income Tax Slab", 
                                        {"currency": "IDR", "is_default": 1}, 
                                        "name")
        else:
            # Jika kolom is_default tidak ada, ambil tax slab IDR pertama
            tax_slabs = frappe.get_all("Income Tax Slab", 
                                        filters={"currency": "IDR"}, 
                                        fields=["name"])
            if tax_slabs:
                tax_slab = tax_slabs[0].name
        
        # Jika tidak ada Income Tax Slab, coba buat
        if not tax_slab:
            try:
                from payroll_indonesia.utilities.tax_slab import create_income_tax_slab
                tax_slab = create_income_tax_slab()
                frappe.db.commit()
            except Exception as e:
                frappe.log_error(f"Failed to create Income Tax Slab: {cstr(e)}", "Fix Company Validation")
            
        # Loop semua Salary Structure
        for ss in salary_structures:
            try:
                # Update Income Tax Slab
                if tax_slab:
                    frappe.db.set_value("Salary Structure", ss.name, "income_tax_slab", tax_slab)
                    frappe.db.set_value("Salary Structure", ss.name, "tax_calculation_method", "Manual")
                    
                # Jika sebelumnya submitted, set docstatus=1
                if ss.docstatus == 1:
                    frappe.db.set_value("Salary Structure", ss.name, "docstatus", 1)
            except Exception as e:
                frappe.log_error(f"Error updating {ss.name}: {cstr(e)}", "Fix Company Validation")
                
        frappe.db.commit()
        
    except Exception as e:
        frappe.log_error(f"Error in fix_company_field_validation: {cstr(e)}", "Patch Error")

def check_column_exists(doctype, column):
    """Check if column exists in DocType"""
    try:
        frappe.db.sql(f"SELECT `{column}` FROM `tab{doctype}` LIMIT 1")
        return True
    except Exception:
        return False