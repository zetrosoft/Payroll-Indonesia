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
        
        // TAMBAHKAN INI: Tombol untuk Debug TER Calculation
        frm.add_custom_button(__('Debug TER Calc'), function() {
            let total_earnings = 0;
            (frm.doc.earnings || []).forEach(function(e) {
                total_earnings += flt(e.amount);
            });
            
            let pph21_amount = 0;
            (frm.doc.deductions || []).forEach(function(d) {
                if (d.salary_component === "PPh 21") {
                    pph21_amount += flt(d.amount);
                }
            });
            
            let using_ter = frm.doc.is_using_ter || 0;
            let ter_rate = (frm.doc.ter_rate || 0) / 100;
            let expected_ter_tax = total_earnings * ter_rate;
            
            let message = `
                <div style="max-width: 600px;">
                    <h3>TER Calculation Debug</h3>
                    <table class="table table-bordered">
                        <tr>
                            <td><strong>Gross Pay</strong></td>
                            <td>${format_currency(frm.doc.gross_pay)}</td>
                        </tr>
                        <tr>
                            <td><strong>Total Earnings</strong></td>
                            <td>${format_currency(total_earnings)}</td>
                        </tr>
                        <tr>
                            <td><strong>Menggunakan TER</strong></td>
                            <td>${using_ter ? 'Ya' : 'Tidak'}</td>
                        </tr>
                        <tr>
                            <td><strong>TER Rate</strong></td>
                            <td>${frm.doc.ter_rate || 0}%</td>
                        </tr>
                        <tr>
                            <td><strong>PPh 21 (Saved)</strong></td>
                            <td>${format_currency(pph21_amount)}</td>
                        </tr>
                        <tr>
                            <td><strong>Expected TER Tax</strong></td>
                            <td>${format_currency(expected_ter_tax)}</td>
                            <td>${Math.abs(pph21_amount - expected_ter_tax) > 1 ? 
                                  '<span style="color: red;">Mismatch!</span>' : 
                                  '<span style="color: green;">Match</span>'}</td>
                        </tr>
                    </table>
                    
                    ${Math.abs(frm.doc.gross_pay - total_earnings) > 1 ? 
                      `<div class="alert alert-warning">
                       gross_pay (${format_currency(frm.doc.gross_pay)}) berbeda dengan 
                       total earnings (${format_currency(total_earnings)}). 
                       Ini bisa menjadi indikasi masalah perhitungan.
                      </div>` : ''}
                </div>
            `;
            
            frappe.msgprint({
                title: __('TER Calculation Debug'),
                indicator: 'blue',
                message: message
            });
        }, __('Actions'));
        
        // TAMBAHKAN INI: Tombol untuk Fix TER Calculation
        if (frm.is_new() || frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Fix TER Calculation'), function() {
                if (!frm.doc.is_using_ter) {
                    frappe.msgprint("Slip gaji ini tidak menggunakan metode TER.");
                    return;
                }
                
                let total_earnings = 0;
                (frm.doc.earnings || []).forEach(function(e) {
                    total_earnings += flt(e.amount);
                });
                
                let ter_rate = (frm.doc.ter_rate || 0) / 100;
                let correct_tax = total_earnings * ter_rate;
                
                // Update PPh 21 component
                let found_pph21 = false;
                frm.doc.deductions.forEach(function(d) {
                    if (d.salary_component === "PPh 21") {
                        d.amount = correct_tax;
                        found_pph21 = true;
                    }
                });
                
                if (!found_pph21) {
                    frappe.msgprint("Komponen PPh 21 tidak ditemukan.");
                    return;
                }
                
                frm.refresh_field('deductions');
                frappe.msgprint({
                    title: __('TER Calculation Fixed'),
                    indicator: 'green',
                    message: __('PPh 21 sekarang dihitung langsung dari penghasilan bulanan: {0}', 
                                [format_currency(correct_tax)])
                });
            }).addClass('btn-primary');
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