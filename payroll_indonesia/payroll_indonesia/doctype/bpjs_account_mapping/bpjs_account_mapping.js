// Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
// For license information, please see license.txt
// Last modified: 2025-04-27 09:52:03 by dannyaudian

frappe.ui.form.on('BPJS Account Mapping', {
    refresh: function(frm) {
        // Tambahkan tombol untuk melihat BPJS Settings
        frm.add_custom_button(__('View BPJS Settings'), function() {
            frappe.set_route('Form', 'BPJS Settings');
        }, __('Actions'));
        
        // Tambahkan tombol untuk test jurnal entry jika dokumen tersimpan
        if (!frm.is_new()) {
            frm.add_custom_button(__('Test Journal Entry'), function() {
                validate_create_journal_entry(frm);
            }, __('Actions'));
        }
        
        // Tambahkan tombol untuk membuka BPJS Payment Summary jika ada
        if (!frm.is_new()) {
            frm.add_custom_button(__('BPJS Payment Summaries'), function() {
                frappe.set_route('List', 'BPJS Payment Summary', {
                    'company': frm.doc.company
                });
            }, __('View'));
        }
        
        // Tambahkan indikator jika semua akun terisi
        update_mapping_status(frm);
    },
    
    company: function(frm) {
        // Reset field ketika company berubah
        ['kesehatan_employee_account', 'kesehatan_employer_debit_account', 
         'kesehatan_employer_credit_account', 'jht_employee_account',
         'jht_employer_debit_account', 'jht_employer_credit_account',
         'jp_employee_account', 'jp_employer_debit_account',
         'jp_employer_credit_account', 'jkk_employer_debit_account',
         'jkk_employer_credit_account', 'jkm_employer_debit_account',
         'jkm_employer_credit_account'].forEach(function(field) {
            frm.set_value(field, '');
        });
        
        // Set nama pemetaan secara otomatis
        if (frm.doc.company) {
            frm.set_value('mapping_name', 'BPJS Account Mapping - ' + frm.doc.company);
        } else {
            frm.set_value('mapping_name', '');
        }
    }
});

// Validasi dan test pembuatan journal entry
function validate_create_journal_entry(frm) {
    frappe.prompt([
        {
            fieldtype: 'Link',
            label: __('BPJS Payment Component'),
            fieldname: 'bpjs_component',
            options: 'BPJS Payment Component',
            reqd: 1,
            get_query: function() {
                return {
                    filters: {
                        'docstatus': 1,
                        'company': frm.doc.company
                    }
                };
            }
        }
    ], function(values) {
        frappe.call({
            method: 'payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping.test_create_journal_entry',
            args: {
                mapping_name: frm.doc.name,
                bpjs_component: values.bpjs_component
            },
            callback: function(r) {
                if (r.message) {
                    frappe.msgprint(__('Test Journal Entry created successfully. Entry ID: {0}', [r.message]));
                } else {
                    frappe.msgprint(__('Failed to create test Journal Entry. Check console for details.'));
                }
            }
        });
    }, __('Select BPJS Component for Test'), __('Create Test Entry'));
}

// Update status indicator berdasarkan kelengkapan mapping
function update_mapping_status(frm) {
    let required_accounts = [
        'kesehatan_employee_account', 
        'kesehatan_employer_debit_account',
        'kesehatan_employer_credit_account',
        'jht_employee_account',
        'jht_employer_debit_account',
        'jht_employer_credit_account'
    ];
    
    let total_filled = 0;
    required_accounts.forEach(function(field) {
        if (frm.doc[field]) {
            total_filled++;
        }
    });
    
    let percentage = Math.round((total_filled / required_accounts.length) * 100);
    
    if (percentage == 100) {
        frm.dashboard.set_headline(
            __('All required accounts are set ({0}%)', [percentage]),
            'green'
        );
    } else if (percentage >= 50) {
        frm.dashboard.set_headline(
            __('Some required accounts are missing ({0}%)', [percentage]),
            'orange'
        );
    } else {
        frm.dashboard.set_headline(
            __('Many required accounts are missing ({0}%)', [percentage]),
            'red'
        );
    }
}