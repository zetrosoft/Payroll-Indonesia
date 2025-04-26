import frappe

def execute():
    """Patch to fix company field validation during migration"""
    
    # Ambil semua Salary Structure dengan company=%
    salary_structures = frappe.get_all("Salary Structure", 
                                       filters={"company": "%"}, 
                                       fields=["name", "docstatus"])
    
    if not salary_structures:
        return
        
    # Dapatkan Income Tax Slab default
    tax_slab = frappe.db.get_value("Income Tax Slab", 
                                    {"currency": "IDR", "is_default": 1}, 
                                    "name")
    
    # Jika tidak ada Income Tax Slab, coba buat
    if not tax_slab:
        try:
            from payroll_indonesia.utilities.tax_slab import create_default_tax_slab
            tax_slab = create_default_tax_slab()
        except:
            frappe.log_error("Failed to create default Income Tax Slab", "Fix Company Validation")
        
    # Loop semua Salary Structure
    for ss in salary_structures:
        # Update Income Tax Slab
        if tax_slab:
            frappe.db.set_value("Salary Structure", ss.name, "income_tax_slab", tax_slab)
            frappe.db.set_value("Salary Structure", ss.name, "tax_calculation_method", "Manual")
            
        # Jika sebelumnya submitted, set docstatus=1
        if ss.docstatus == 1:
            frappe.db.set_value("Salary Structure", ss.name, "docstatus", 1)
            
    frappe.db.commit()