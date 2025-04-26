# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import change_log

# Simpan fungsi asli untuk referensi jika belum disimpan
if not hasattr(change_log, '_original_get_versions'):
    change_log._original_get_versions = change_log.get_versions

def safe_get_versions():
    """
    Versi yang lebih aman dari get_versions() untuk menangani kasus di mana
    app_title dan app_description mungkin tidak dalam format yang diharapkan
    """
    versions = {}
    for app in frappe.get_installed_apps(_ensure_on_bench=True):
        try:
            app_hooks = frappe.get_hooks(app_name=app)
            
            # Handle app_title dengan aman
            app_title = app_hooks.get("app_title")
            if isinstance(app_title, list) and len(app_title) > 0:
                title = app_title[0]
            elif isinstance(app_title, str):
                title = app_title
            else:
                title = app.replace('_', ' ').title()
            
            # Handle app_description dengan aman
            app_description = app_hooks.get("app_description")
            if isinstance(app_description, list) and len(app_description) > 0:
                description = app_description[0]
            elif isinstance(app_description, str):
                description = app_description
            else:
                description = ""
            
            versions[app] = {
                "title": title,
                "description": description,
                "branch": change_log.get_app_branch(app),
            }

            if versions[app]["branch"] != "master":
                branch_version = app_hooks.get("{}_version".format(versions[app]["branch"]))
                if branch_version:
                    versions[app]["branch_version"] = branch_version[0] + f" ({change_log.get_app_last_commit_ref(app)})"

            try:
                versions[app]["version"] = frappe.get_attr(app + ".__version__")
            except AttributeError:
                versions[app]["version"] = "0.0.1"
                
        except Exception as e:
            # Fallback jika terjadi error
            versions[app] = {
                "title": app.replace('_', ' ').title(),
                "description": "",
                "version": "0.0.1",
                "branch": ""
            }
    
    return versions

# Fungsi untuk menerapkan monkey patch
def apply_patches():
    """Terapkan semua monkey patch yang diperlukan"""
    try:
        # Patch get_versions
        change_log.get_versions = safe_get_versions
        
        # Jika fungsi original memiliki whitelist property, pertahankan
        if hasattr(change_log._original_get_versions, "__func__"):
            if hasattr(change_log._original_get_versions.__func__, "whitelisted"):
                safe_get_versions.whitelisted = change_log._original_get_versions.__func__.whitelisted
        
        # Tambahkan fix langsung untuk hooks payroll_indonesia jika diperlukan
        # Ini akan memastikan app_title tersedia bahkan jika tidak di hooks.py
        try:
            hooks = frappe.get_hooks(app_name="payroll_indonesia")
            if not hooks.get("app_title"):
                hooks["app_title"] = ["Payroll Indonesia"]
        except Exception:
            pass
        
        frappe.log_error("Boot override patches applied successfully", "Boot Override")
        print("Boot override patches applied successfully")
        return True
    except Exception as e:
        frappe.log_error(f"Failed to apply boot override patches: {str(e)}", "Boot Override Error")
        print(f"Failed to apply boot override patches: {str(e)}")
        return False