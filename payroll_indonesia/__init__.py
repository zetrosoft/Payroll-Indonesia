# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

__version__ = '0.0.1'

# Tambahkan skrip inisialisasi untuk mendaftarkan app di Frappe
import frappe

# Varian untuk patch get_versions
def patch_get_versions():
    """Patch frappe.utils.change_log.get_versions untuk menangani app_title dengan lebih baik"""
    try:
        from frappe.utils import change_log
        
        # Simpan fungsi asli
        if not hasattr(change_log, '_original_get_versions'):
            change_log._original_get_versions = change_log.get_versions
        
        # Define patched function
        def safe_get_versions():
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
                    frappe.log_error(f"Error getting version for {app}: {str(e)}")
                    versions[app] = {
                        "title": app.replace('_', ' ').title(),
                        "description": "",
                        "version": "0.0.1",
                        "branch": ""
                    }
            
            return versions
        
        # Apply the patch
        change_log.get_versions = safe_get_versions
        
        return True
    except Exception as e:
        frappe.log_error(f"Failed to patch get_versions: {str(e)}")
        return False

# Apply the patch when module is imported
patch_get_versions()