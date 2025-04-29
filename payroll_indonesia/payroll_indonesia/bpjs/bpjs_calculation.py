# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last updated: 2025-04-29 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, cint, now_datetime
from payroll_indonesia.payroll_indonesia.utils import get_bpjs_settings


def debug_log(message, module_name="BPJS Calculation"):
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    frappe.log_error("[{}] {}".format(timestamp, message), module_name)


def get_bpjs_config(emp, settings):
    config = {}

    if cint(emp.get("ikut_bpjs_kesehatan", 1)):
        config["kesehatan"] = {
            "employee_percent": settings.get("kesehatan_employee_percent", 1.0),
            "employer_percent": settings.get("kesehatan_employer_percent", 4.0),
            "max_salary": settings.get("kesehatan_max_salary", 12000000),
        }

    if cint(emp.get("ikut_bpjs_ketenagakerjaan", 1)):
        config["jht"] = {
            "employee_percent": settings.get("jht_employee_percent", 2.0),
            "employer_percent": settings.get("jht_employer_percent", 3.7),
        }

        config["jp"] = {
            "employee_percent": settings.get("jp_employee_percent", 1.0),
            "employer_percent": settings.get("jp_employer_percent", 2.0),
            "max_salary": settings.get("jp_max_salary", 9077600),
        }

        config["jkk"] = {"percent": settings.get("jkk_percent", 0.24)}
        config["jkm"] = {"percent": settings.get("jkm_percent", 0.3)}

    return config


def hitung_bpjs(employee, gaji_pokok):
    debug_log("Start hitung_bpjs for {} with salary {}".format(employee, gaji_pokok))
    
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

    if not employee or not gaji_pokok or gaji_pokok <= 0:
        debug_log("Invalid input: employee={}, gaji_pokok={}".format(employee, gaji_pokok))
        return result

    try:
        emp = frappe.get_doc("Employee", employee)
    except Exception as e:
        debug_log("Error fetching Employee: {}".format(str(e)))
        return result

    try:
        settings = get_bpjs_settings()
    except Exception as e:
        debug_log("Error fetching BPJS settings: {}".format(str(e)))
        return result

    config = get_bpjs_config(emp, settings)
    if not config:
        debug_log("Employee {} not participating in any BPJS".format(employee))
        return result

    # Apply salary caps
    kesehatan_salary = min(gaji_pokok, config.get("kesehatan", {}).get("max_salary", gaji_pokok))
    jp_salary = min(gaji_pokok, config.get("jp", {}).get("max_salary", gaji_pokok))

    # Kesehatan
    if "kesehatan" in config:
        result["kesehatan_employee"] = kesehatan_salary * config["kesehatan"]["employee_percent"] / 100
        result["kesehatan_employer"] = kesehatan_salary * config["kesehatan"]["employer_percent"] / 100

    # JHT
    if "jht" in config:
        result["jht_employee"] = gaji_pokok * config["jht"]["employee_percent"] / 100
        result["jht_employer"] = gaji_pokok * config["jht"]["employer_percent"] / 100

    # JP
    if "jp" in config:
        result["jp_employee"] = jp_salary * config["jp"]["employee_percent"] / 100
        result["jp_employer"] = jp_salary * config["jp"]["employer_percent"] / 100

    # JKK
    if "jkk" in config:
        result["jkk_employer"] = gaji_pokok * config["jkk"]["percent"] / 100

    # JKM
    if "jkm" in config:
        result["jkm_employer"] = gaji_pokok * config["jkm"]["percent"] / 100

    # Total
    result["total_employee"] = (
        result["kesehatan_employee"] + result["jht_employee"] + result["jp_employee"]
    )
    result["total_employer"] = (
        result["kesehatan_employer"] + result["jht_employer"] +
        result["jp_employer"] + result["jkk_employer"] + result["jkm_employer"]
    )

    debug_log("BPJS result for {}: {}".format(employee, result))
    return result
