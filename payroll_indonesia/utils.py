import frappe
from frappe.utils import flt

def get_bpjs_settings():
    """Get BPJS settings as a dictionary"""
    settings = frappe.get_single("BPJS Settings")
    return {
        "kesehatan": {
            "employee_percent": flt(settings.kesehatan_employee_percent),
            "employer_percent": flt(settings.kesehatan_employer_percent),
            "max_salary": flt(settings.kesehatan_max_salary)
        },
        "jht": {
            "employee_percent": flt(settings.jht_employee_percent),
            "employer_percent": flt(settings.jht_employer_percent)
        },
        "jp": {
            "employee_percent": flt(settings.jp_employee_percent),
            "employer_percent": flt(settings.jp_employer_percent),
            "max_salary": flt(settings.jp_max_salary)
        },
        "jkk": {
            "percent": flt(settings.jkk_percent)
        },
        "jkm": {
            "percent": flt(settings.jkm_percent)
        }
    }

def calculate_bpjs_contributions(salary, bpjs_settings=None):
    """
    Calculate BPJS contributions based on salary and settings
    
    Args:
        salary (float): Base salary amount
        bpjs_settings (object, optional): BPJS Settings or dict. Will fetch if not provided.
        
    Returns:
        dict: Dictionary containing BPJS contribution details
    """
    if not bpjs_settings:
        bpjs_settings = frappe.get_single("BPJS Settings")
    
    # Check if bpjs_settings is a dict or an object
    if isinstance(bpjs_settings, dict):
        # Use dict values
        kesehatan_employee_percent = bpjs_settings.get("kesehatan", {}).get("employee_percent", 1)
        kesehatan_employer_percent = bpjs_settings.get("kesehatan", {}).get("employer_percent", 4)
        kesehatan_max_salary = bpjs_settings.get("kesehatan", {}).get("max_salary", 12000000)
        
        jht_employee_percent = bpjs_settings.get("jht", {}).get("employee_percent", 2)
        jht_employer_percent = bpjs_settings.get("jht", {}).get("employer_percent", 3.7)
        
        jp_employee_percent = bpjs_settings.get("jp", {}).get("employee_percent", 1)
        jp_employer_percent = bpjs_settings.get("jp", {}).get("employer_percent", 2)
        jp_max_salary = bpjs_settings.get("jp", {}).get("max_salary", 9077600)
        
        jkk_percent = bpjs_settings.get("jkk", {}).get("percent", 0.24)
        jkm_percent = bpjs_settings.get("jkm", {}).get("percent", 0.3)
    else:
        # Use object attributes
        kesehatan_employee_percent = flt(bpjs_settings.kesehatan_employee_percent)
        kesehatan_employer_percent = flt(bpjs_settings.kesehatan_employer_percent)
        kesehatan_max_salary = flt(bpjs_settings.kesehatan_max_salary)
        
        jht_employee_percent = flt(bpjs_settings.jht_employee_percent)
        jht_employer_percent = flt(bpjs_settings.jht_employer_percent)
        
        jp_employee_percent = flt(bpjs_settings.jp_employee_percent)
        jp_employer_percent = flt(bpjs_settings.jp_employer_percent)
        jp_max_salary = flt(bpjs_settings.jp_max_salary)
        
        jkk_percent = flt(bpjs_settings.jkk_percent)
        jkm_percent = flt(bpjs_settings.jkm_percent)
    
    # Cap salaries at maximum thresholds
    kesehatan_salary = min(flt(salary), kesehatan_max_salary)
    jp_salary = min(flt(salary), jp_max_salary)
    
    # Calculate BPJS Kesehatan
    kesehatan_karyawan = kesehatan_salary * (kesehatan_employee_percent / 100)
    kesehatan_perusahaan = kesehatan_salary * (kesehatan_employer_percent / 100)
    
    # Calculate BPJS Ketenagakerjaan - JHT
    jht_karyawan = flt(salary) * (jht_employee_percent / 100)
    jht_perusahaan = flt(salary) * (jht_employer_percent / 100)
    
    # Calculate BPJS Ketenagakerjaan - JP
    jp_karyawan = jp_salary * (jp_employee_percent / 100)
    jp_perusahaan = jp_salary * (jp_employer_percent / 100)
    
    # Calculate BPJS Ketenagakerjaan - JKK and JKM
    jkk = flt(salary) * (jkk_percent / 100)
    jkm = flt(salary) * (jkm_percent / 100)
    
    # Return structured result
    return {
        "kesehatan": {
            "karyawan": kesehatan_karyawan,
            "perusahaan": kesehatan_perusahaan,
            "total": kesehatan_karyawan + kesehatan_perusahaan
        },
        "ketenagakerjaan": {
            "jht": {
                "karyawan": jht_karyawan,
                "perusahaan": jht_perusahaan,
                "total": jht_karyawan + jht_perusahaan
            },
            "jp": {
                "karyawan": jp_karyawan,
                "perusahaan": jp_perusahaan,
                "total": jp_karyawan + jp_perusahaan
            },
            "jkk": jkk,
            "jkm": jkm
        }
    }