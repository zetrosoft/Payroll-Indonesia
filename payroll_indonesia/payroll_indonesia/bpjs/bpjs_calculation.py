import frappe
from frappe.utils import flt
from payroll_indonesia.payroll_indonesia.utils import get_bpjs_settings

def hitung_bpjs(employee, gaji_pokok):
    """
    Calculate BPJS contributions based on basic salary
    
    Args:
        employee (str): Employee ID
        gaji_pokok (float): Basic salary
        
    Returns:
        dict: BPJS calculation results
    """
    emp = frappe.get_doc("Employee", employee)
    settings = get_bpjs_settings()
    
    result = {
        "kesehatan_employee": 0,
        "kesehatan_employer": 0,
        "jht_employee": 0,
        "jht_employer": 0,
        "jp_employee": 0,
        "jp_employer": 0,
        "jkk_employer": 0,
        "jkm_employer": 0,
        "total_employee": 0,
        "total_employer": 0
    }
    
    # Skip if employee doesn't participate
    if not emp.get("ikut_bpjs_kesehatan") and not emp.get("ikut_bpjs_ketenagakerjaan"):
        return result
    
    # Apply maximum salary cap for BPJS calculations
    bpjs_salary = min(flt(gaji_pokok), settings.get('max_salary', 12000000))
    
    # BPJS Kesehatan (Health Insurance)
    if emp.get("ikut_bpjs_kesehatan"):
        result["kesehatan_employee"] = bpjs_salary * flt(settings.get("kesehatan_employee", 1.0)) / 100
        result["kesehatan_employer"] = bpjs_salary * flt(settings.get("kesehatan_employer", 4.0)) / 100
    
    # BPJS Ketenagakerjaan (Employment Insurance)
    if emp.get("ikut_bpjs_ketenagakerjaan"):
        # JHT (Jaminan Hari Tua - Old Age Security)
        result["jht_employee"] = bpjs_salary * flt(settings.get("jht_employee", 2.0)) / 100
        result["jht_employer"] = bpjs_salary * flt(settings.get("jht_employer", 3.7)) / 100
        
        # JP (Jaminan Pensiun - Pension Security)
        result["jp_employee"] = bpjs_salary * flt(settings.get("jp_employee", 1.0)) / 100
        result["jp_employer"] = bpjs_salary * flt(settings.get("jp_employer", 2.0)) / 100
        
        # JKK (Jaminan Kecelakaan Kerja - Work Accident Security)
        result["jkk_employer"] = bpjs_salary * flt(settings.get("jkk_employer", 0.24)) / 100
        
        # JKM (Jaminan Kematian - Death Security)
        result["jkm_employer"] = bpjs_salary * flt(settings.get("jkm_employer", 0.3)) / 100
    
    # Calculate totals
    result["total_employee"] = (
        result["kesehatan_employee"] +
        result["jht_employee"] +
        result["jp_employee"]
    )
    
    result["total_employer"] = (
        result["kesehatan_employer"] +
        result["jht_employer"] +
        result["jp_employer"] +
        result["jkk_employer"] +
        result["jkm_employer"]
    )
    
    return result