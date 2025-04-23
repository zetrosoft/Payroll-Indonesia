frappe.ui.form.on('Salary Slip', {
    refresh: function(frm) {
        // Add custom buttons or functionality for Indonesian payroll
        if (frm.doc.is_final_gabung_suami) {
            frm.dashboard.add_indicator(__("NPWP Gabung Suami"), "blue");
        }
        
        // Add indicator for TER method
        if (frm.doc.is_using_ter) {
            frm.dashboard.add_indicator(__("Using TER Method") + ` (${frm.doc.ter_rate}%)`, "green");
        }
        
        // Add indicator for December correction
        if (frm.doc.koreksi_pph21 && frm.doc.end_date && 
            (new Date(frm.doc.end_date).getMonth() + 1) === 12) {
            const indicator_color = frm.doc.koreksi_pph21 > 0 ? "orange" : "green";
            const indicator_text = frm.doc.koreksi_pph21 > 0 ? "Kurang Bayar" : "Lebih Bayar";
            frm.dashboard.add_indicator(__(`PPh 21 Koreksi: ${indicator_text}`), indicator_color);
        }
    },
    
    // Show payroll note in a dialog for better readability
    after_save: function(frm) {
        if (frm.doc.payroll_note && frm.doc.payroll_note.trim().length > 0) {
            // Create a button to view payroll calculation details
            frm.add_custom_button(__('View Tax Calculation'), function() {
                let d = new frappe.ui.Dialog({
                    title: __('PPh 21 Calculation Details'),
                    fields: [{
                        fieldtype: 'HTML',
                        fieldname: 'calculation_html'
                    }]
                });
                
                const noteContent = frm.doc.payroll_note
                    .replace(/\n/g, '<br>')
                    .replace(/===(.+?)===/g, '<strong>$1</strong>')
                    .replace(/Rp\s(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)/g, '<b>Rp $1</b>');
                
                d.fields_dict.calculation_html.$wrapper.html(
                    `<div style="max-height: 300px; overflow-y: auto; padding: 10px;">${noteContent}</div>`
                );
                
                d.show();
            }, __('Actions'));
        }
    }
});