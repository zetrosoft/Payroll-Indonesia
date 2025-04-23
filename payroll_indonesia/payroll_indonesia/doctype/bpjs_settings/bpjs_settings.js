frappe.ui.form.on('BPJS Settings', {
    refresh: function(frm) {
        frm.add_fetch('company', 'default_currency', 'currency');
        
        // Add help about BPJS settings
        if (!frm.doc.__islocal) {
            frm.add_custom_button(__("Update BPJS Components"), function() {
                frappe.confirm(
                    "Apakah Anda ingin memperbarui semua komponen BPJS pada salary slip yang belum disubmit?",
                    function() {
                        // Yes - Update components
                        frappe.call({
                            method: "payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation.update_all_bpjs_components",
                            args: {},
                            freeze: true,
                            freeze_message: __("Memperbarui komponen BPJS..."),
                            callback: function(r) {
                                frappe.msgprint("Komponen BPJS berhasil diperbarui.");
                            }
                        });
                    }
                );
            }, "Aksi");
        }
    },
    
    // Auto-calculate combined contributions
    setup: function(frm) {
        frm.set_query("company", function() {
            return {
                "filters": {
                    "country": "Indonesia"
                }
            };
        });
    },
    
    // Validate values when changed
    kesehatan_employee_percent: function(frm) {
        validate_percentage(frm, "kesehatan_employee_percent", 5);
    },
    kesehatan_employer_percent: function(frm) {
        validate_percentage(frm, "kesehatan_employer_percent", 10);
    },
    jht_employee_percent: function(frm) {
        validate_percentage(frm, "jht_employee_percent", 5);
    },
    jht_employer_percent: function(frm) {
        validate_percentage(frm, "jht_employer_percent", 10);
    },
    jp_employee_percent: function(frm) {
        validate_percentage(frm, "jp_employee_percent", 5);
    },
    jp_employer_percent: function(frm) {
        validate_percentage(frm, "jp_employer_percent", 5);
    },
    jkk_percent: function(frm) {
        validate_percentage(frm, "jkk_percent", 5);
    },
    jkm_percent: function(frm) {
        validate_percentage(frm, "jkm_percent", 5);
    },
});

// Helper function to validate percentage values
function validate_percentage(frm, field, max_value) {
    if (frm.doc[field] < 0) {
        frappe.model.set_value(frm.doctype, frm.docname, field, 0);
        frappe.show_alert({message: __("Nilai persentase tidak bisa negatif"), indicator: 'red'});
    } else if (frm.doc[field] > max_value) {
        frappe.model.set_value(frm.doctype, frm.docname, field, max_value);
        frappe.show_alert({
            message: __(`Nilai maksimum untuk ${frappe.meta.get_label(frm.doctype, field, frm.docname)} adalah ${max_value}%`), 
            indicator: 'red'
        });
    }
}