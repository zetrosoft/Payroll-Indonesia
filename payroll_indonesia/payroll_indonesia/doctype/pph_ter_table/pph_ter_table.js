// Import required utilities
const flt = frappe.utils.flt;

frappe.ui.form.on('PPh TER Table', {
    refresh: function(frm) {
        // Add Generate Payment Entry button
        if(frm.doc.docstatus === 1 && !frm.doc.payment_entry) {
            frm.add_custom_button(__('Generate Payment Entry'), function() {
                frappe.confirm(
                    __('Are you sure you want to create Payment Entry for PPh 21 payment?'),
                    function() {
                        // Check if Tax Office supplier exists
                        frappe.db.exists('Supplier', 'Kantor Pajak')
                            .then(exists => {
                                if (!exists) {
                                    frappe.msgprint(__('Supplier "Kantor Pajak" does not exist. Please create it first.'));
                                    return;
                                }
                                
                                // Proceed with payment entry creation
                                frm.call({
                                    doc: frm.doc,
                                    method: 'generate_payment_entry',
                                    freeze: true,
                                    freeze_message: __('Generating Payment Entry...'),
                                    callback: function(r) {
                                        if(r.message) {
                                            frappe.show_alert({
                                                message: __('Payment Entry {0} created', [r.message]),
                                                indicator: 'green'
                                            });
                                            frappe.set_route('Form', 'Payment Entry', r.message);
                                        }
                                    }
                                });
                            });
                    }
                );
            }).addClass('btn-primary');
        }
        
        // Add view button if payment entry exists
        if(frm.doc.payment_entry) {
            frm.add_custom_button(__('View Payment Entry'), function() {
                frappe.set_route('Form', 'Payment Entry', frm.doc.payment_entry);
            }, __('Actions'));
        }
        
        // Add buttons to generate reports
        if(frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Generate PPh 21 Report'), function() {
                frm.call({
                    method: 'payroll_indonesia.payroll_indonesia.reports.pph21_report.generate_report',
                    args: {
                        'doc_name': frm.doc.name
                    },
                    callback: function(r) {
                        if (r.message) {
                            frappe.msgprint(__('PPh 21 Report generated. <a href="{0}">Click here to view</a>', [r.message]));
                        }
                    }
                });
            }, __('Reports'));
            
            frm.add_custom_button(__('Generate CSV Export'), function() {
                frm.call({
                    method: 'payroll_indonesia.payroll_indonesia.reports.pph21_csv.export_csv',
                    args: {
                        'doc_name': frm.doc.name
                    },
                    callback: function(r) {
                        if (r.message) {
                            window.open(r.message, '_blank');
                        }
                    }
                });
            }, __('Reports'));
        }
        
        // Add button to calculate from salary slips
        if(frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Calculate From Salary Slips'), function() {
                if (!frm.doc.period || !frm.doc.year) {
                    frappe.msgprint(__('Please set Period and Year first'));
                    return;
                }
                
                frappe.confirm(
                    __('This will fetch data from salary slips for {0} {1}. Continue?', [frm.doc.period, frm.doc.year]),
                    function() {
                        frappe.call({
                            method: 'payroll_indonesia.payroll_indonesia.tax.pph_ter.calculate_from_salary_slips',
                            args: {
                                'period': frm.doc.period,
                                'year': frm.doc.year,
                                'company': frm.doc.company
                            },
                            freeze: true,
                            freeze_message: __('Calculating from salary slips...'),
                            callback: function(r) {
                                if (r.message) {
                                    frm.clear_table('details');
                                    
                                    r.message.forEach(emp => {
                                        let row = frm.add_child('details');
                                        row.employee = emp.employee;
                                        row.employee_name = emp.employee_name;
                                        row.npwp = emp.npwp;
                                        row.biaya_jabatan = emp.biaya_jabatan;
                                        row.penghasilan_bruto = emp.penghasilan_bruto;
                                        row.penghasilan_netto = emp.penghasilan_netto;
                                        row.penghasilan_kena_pajak = emp.penghasilan_kena_pajak;
                                        row.amount = emp.pph21;
                                    });
                                    
                                    frm.refresh_field('details');
                                    calculate_total(frm);
                                    frappe.show_alert({
                                        message: __('Loaded data from {0} salary slips', [r.message.length]),
                                        indicator: 'green'
                                    });
                                }
                            }
                        });
                    }
                );
            }, __('Actions'));
        }
    },
    
    onload: function(frm) {
        if(frm.is_new()) {
            // Set default values for new document
            frm.set_value('posting_date', frappe.datetime.get_today());
            
            // Set period and year
            let today = frappe.datetime.get_today();
            let month_names = ['January', 'February', 'March', 'April', 'May', 'June', 
                             'July', 'August', 'September', 'October', 'November', 'December'];
            let current_month_index = new Date().getMonth();
            let current_year = new Date().getFullYear();
            
            frm.set_value('period', month_names[current_month_index]);
            frm.set_value('year', current_year);
            frm.set_value('month', current_month_index + 1); // Add month as number (1-12)
        }
        
        // Set month year title
        if(frm.doc.period && frm.doc.year) {
            frm.set_value('month_year_title', frm.doc.period + ' ' + frm.doc.year);
        }
    },
    
    period: function(frm) {
        // Set month based on period
        if(frm.doc.period) {
            let month_names = ['January', 'February', 'March', 'April', 'May', 'June', 
                             'July', 'August', 'September', 'October', 'November', 'December'];
            let month_index = month_names.indexOf(frm.doc.period);
            if(month_index !== -1) {
                frm.set_value('month', month_index + 1);
            }
        }
        
        if(frm.doc.period && frm.doc.year) {
            frm.set_value('month_year_title', frm.doc.period + ' ' + frm.doc.year);
            
            // Check for duplicates
            if (frm.doc.period && frm.doc.year && !frm.is_new()) {
                frappe.db.get_list('PPh TER Table', {
                    filters: {
                        'period': frm.doc.period,
                        'year': frm.doc.year,
                        'company': frm.doc.company,
                        'name': ['!=', frm.doc.name]
                    }
                }).then(records => {
                    if (records && records.length > 0) {
                        frappe.msgprint({
                            title: __('Warning'),
                            indicator: 'orange',
                            message: __('A PPh TER record already exists for {0} {1} in this company.', [frm.doc.period, frm.doc.year])
                        });
                    }
                });
            }
        }
    },
    
    month: function(frm) {
        // Set period based on month
        if(frm.doc.month && frm.doc.month >= 1 && frm.doc.month <= 12) {
            let month_names = ['January', 'February', 'March', 'April', 'May', 'June', 
                             'July', 'August', 'September', 'October', 'November', 'December'];
            frm.set_value('period', month_names[frm.doc.month - 1]);
        }
    },
    
    year: function(frm) {
        if(frm.doc.period && frm.doc.year) {
            frm.set_value('month_year_title', frm.doc.period + ' ' + frm.doc.year);
            
            // Check for duplicates (same as in period)
            if (frm.doc.period && frm.doc.year && !frm.is_new()) {
                frappe.db.get_list('PPh TER Table', {
                    filters: {
                        'period': frm.doc.period,
                        'year': frm.doc.year,
                        'company': frm.doc.company,
                        'name': ['!=', frm.doc.name]
                    }
                }).then(records => {
                    if (records && records.length > 0) {
                        frappe.msgprint({
                            title: __('Warning'),
                            indicator: 'orange',
                            message: __('A PPh TER record already exists for {0} {1} in this company.', [frm.doc.period, frm.doc.year])
                        });
                    }
                });
            }
        }
    },
    
    validate: function(frm) {
        calculate_total(frm);
    }
});

// Employee tax details calculations
frappe.ui.form.on('PPh TER Detail', {
    details_add: function(frm) {
        calculate_total(frm);
    },
    
    employee: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (row.employee) {
            // Fetch tax information if available
            frappe.db.get_value('Employee', row.employee, ['npwp', 'ktp', 'status_pajak']).then(r => {
                if (r.message) {
                    frappe.model.set_value(cdt, cdn, 'npwp', r.message.npwp);
                    frappe.model.set_value(cdt, cdn, 'ktp', r.message.ktp);
                }
            });
        }
    },
    
    penghasilan_bruto: function(frm, cdt, cdn) {
        // Auto-calculate biaya jabatan
        const row = locals[cdt][cdn];
        if (row.penghasilan_bruto) {
            // Calculate biaya jabatan (5% of bruto, max 500k)
            const biaya_jabatan = Math.min(row.penghasilan_bruto * 0.05, 500000);
            frappe.model.set_value(cdt, cdn, 'biaya_jabatan', biaya_jabatan);
            
            // Calculate netto
            const penghasilan_netto = row.penghasilan_bruto - biaya_jabatan;
            frappe.model.set_value(cdt, cdn, 'penghasilan_netto', penghasilan_netto);
        }
    },
    
    biaya_jabatan: function(frm, cdt, cdn) {
        // Recalculate netto when biaya jabatan changes
        const row = locals[cdt][cdn];
        if (row.penghasilan_bruto && row.biaya_jabatan) {
            const penghasilan_netto = row.penghasilan_bruto - row.biaya_jabatan;
            frappe.model.set_value(cdt, cdn, 'penghasilan_netto', penghasilan_netto);
        }
    },
    
    amount: function(frm) {
        calculate_total(frm);
    },
    
    details_remove: function(frm) {
        calculate_total(frm);
    }
});

// Account calculations
frappe.ui.form.on('PPh TER Account Detail', {
    account_details_add: function(frm) {
        calculate_total(frm);
    },
    
    tax_category: function(frm, cdt, cdn) {
        // Auto-set description based on tax category
        const row = locals[cdt][cdn];
        if (row.tax_category && !row.description) {
            const descriptions = {
                "PPh 21": "Pajak Penghasilan Pasal 21",
                "PPh 23": "Pajak Penghasilan Pasal 23",
                "PPh Final": "Pajak Penghasilan Final",
                "PPN": "Pajak Pertambahan Nilai"
            };
            
            if (descriptions[row.tax_category]) {
                frappe.model.set_value(cdt, cdn, 'description', descriptions[row.tax_category]);
            }
        }
    },
    
    amount: function(frm) {
        calculate_total(frm);
    },
    
    account_details_remove: function(frm) {
        calculate_total(frm);
    }
});

/**
 * Calculate total from PPh TER details
 * @param {Object} frm - The form object
 */
function calculate_total(frm) {
    let total = 0;
    
    // Calculate from employee details
    if(frm.doc.details && frm.doc.details.length) {
        frm.doc.details.forEach(function(d) {
            total += flt(d.amount);
        });
    }
    
    frm.set_value('total', total);
    frm.refresh_field('total');
    
    // Optional: Update account details with the total
    if(frm.doc.account_details && frm.doc.account_details.length === 0 && total > 0) {
        // Auto-create account detail for PPh 21
        let d = frm.add_child('account_details');
        d.tax_category = "PPh 21";
        d.description = "Pajak Penghasilan Pasal 21";
        
        // Try to find Hutang PPh 21 account
        frappe.db.get_list('Account', {
            filters: {
                'account_name': ['like', '%Hutang PPh 21%'],
                'company': frm.doc.company
            },
            fields: ['name']
        }).then(accounts => {
            if (accounts && accounts.length > 0) {
                d.account = accounts[0].name;
            }
            d.amount = total;
            frm.refresh_field('account_details');
        });
    }
}