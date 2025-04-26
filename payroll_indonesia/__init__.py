# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

__version__ = '0.0.1'

def fix_app_title_at_runtime():
    """
    Perbaiki app_title secara aman tanpa melakukan patch yang invasif
    Dipanggil oleh hook on_app_init di hooks.py
    """
    try:
        import frappe
        
        # Jangan modifikasi jika frappe belum fully initialized
        if not frappe.get_installed_apps:
            return
        
        # Jika get_versions sudah ada di change_log, kita amankan
        from frappe.utils import change_log
        
        # Hanya jalankan sekali
        if hasattr(change_log, '_safe_app_title_applied'):
            return
            
        # Definisi fungsi yang aman
        def safe_get_versions():
            versions = {}
            
            # Dapatkan semua installed apps
            try:
                installed_apps = frappe.get_installed_apps(_ensure_on_bench=True)
            except:
                # Fallback jika error
                installed_apps = ["frappe", "payroll_indonesia"]
                
            # Loop melalui semua app
            for app in installed_apps:
                try:
                    # Dapatkan hooks dari app
                    app_hooks = frappe.get_hooks(app_name=app)
                    
                    # Buat title yang aman dari app name
                    safe_title = app.replace('_', ' ').title()
                    safe_description = ""
                    
                    # Handle app_title
                    if app_hooks and "app_title" in app_hooks:
                        app_title = app_hooks["app_title"]
                        if isinstance(app_title, list) and len(app_title) > 0:
                            safe_title = app_title[0]
                        elif isinstance(app_title, str):
                            safe_title = app_title
                    
                    # Handle app_description
                    if app_hooks and "app_description" in app_hooks:
                        app_description = app_hooks["app_description"]
                        if isinstance(app_description, list) and len(app_description) > 0:
                            safe_description = app_description[0]
                        elif isinstance(app_description, str):
                            safe_description = app_description
                    
                    # Buat object version
                    versions[app] = {
                        "title": safe_title, 
                        "description": safe_description,
                        "branch": change_log.get_app_branch(app),
                        "version": "0.0.1"
                    }
                    
                    # Coba dapatkan versi
                    try:
                        versions[app]["version"] = frappe.get_attr(app + ".__version__")
                    except:
                        pass
                    
                    # Handle branch version
                    if versions[app]["branch"] != "master":
                        try:
                            branch_version_key = "{}_version".format(versions[app]["branch"])
                            if branch_version_key in app_hooks:
                                branch_version = app_hooks[branch_version_key]
                                if isinstance(branch_version, list) and len(branch_version) > 0:
                                    commit_ref = change_log.get_app_last_commit_ref(app)
                                    versions[app]["branch_version"] = f"{branch_version[0]} ({commit_ref})"
                        except:
                            pass
                            
                except Exception:
                    # Jika ada error, gunakan fallback
                    versions[app] = {
                        "title": safe_title,
                        "description": "",
                        "version": "0.0.1",
                        "branch": ""
                    }
            
            return versions
        
        # Simpan fungsi asli dan terapkan fungsi baru
        if not hasattr(change_log, '_original_get_versions'):
            change_log._original_get_versions = change_log.get_versions
            
        # Terapkan fungsi baru dan tandai
        change_log.get_versions = safe_get_versions
        change_log._safe_app_title_applied = True
        
        return True
    except Exception:
        # Jangan crash proses app init
        return False