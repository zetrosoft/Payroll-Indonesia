# Payroll Indonesia

Payroll module for Indonesian companies, integrated with ERPNext's Human Resource Management system and customized for Indonesian regulations.

## Features

- Integration with native ERPNext payroll modules (Salary Component, Salary Structure, Salary Slip, Payroll Entry)
- BPJS (Health & Employment Insurance) calculations
- PPh 21 TER (Monthly) tax calculation + progressive December rates for SPT
- Support for various tax statuses (TK/K)
- NPWP Spouse Joint processing
- Support for Non-Permanent Employees (PMK 168/2023)
- December tax correction (SPT)
- Ready for VPS or Frappe Cloud deployment

## Installation

### Prerequisites
- ERPNext v15
- Frappe Framework v15

### From GitHub
```bash
# In your bench directory
bench get-app https://github.com/dannyaudian/payroll_indonesia
bench --site yoursite.local install-app payroll_indonesia
bench migrate

📘 Konfigurasi Wajib: Akun dan Pengaturan
🔶 BPJS Account Setup
Sistem ini membutuhkan akun-akun GL (Chart of Accounts) untuk mencatat potongan dan beban BPJS.

1. Akun Potongan Karyawan (Liability)
BPJS Kesehatan - Karyawan

BPJS JHT - Karyawan

BPJS JP - Karyawan

2. Akun Beban Perusahaan (Expense)
BPJS Kesehatan - Perusahaan

BPJS JHT - Perusahaan

BPJS JP - Perusahaan

BPJS JKK - Perusahaan

BPJS JKM - Perusahaan

3. Akun Utang Perusahaan (Liability)
BPJS Kesehatan - Perusahaan

BPJS JHT - Perusahaan

BPJS JP - Perusahaan

BPJS JKK - Perusahaan

BPJS JKM - Perusahaan

📌 Tips: Letakkan akun di bawah Current Liabilities dan Payroll Expenses sesuai struktur internal perusahaan Anda.

4. Pengaturan BPJS Account Mapping
Buka DocType BPJS Account Mapping

Pilih perusahaan

Hubungkan akun-akun untuk masing-masing komponen (karyawan & perusahaan)

Simpan dan aktifkan untuk Salary Slip

5. Pengaturan BPJS Settings
Tentukan persentase kontribusi (employee & employer) per komponen

Tentukan batas maksimal gaji

Tentukan akun GL untuk pembayaran BPJS jika menggunakan Payment Entry

🔷 PPh 21 Settings
Modul mendukung dua metode perhitungan:

Progressive (default, sesuai tarif lapisan pajak)

TER (Tarif Efektif Rata-rata - sesuai PMK 168/2023)

Pengaturan:
Buka PPh 21 Settings

Pilih metode: Progressive atau TER

Isi:

Tabel PTKP (PPh 21 PTKP)

Tabel Tax Bracket (PPh 21 Tax Bracket) untuk Progressive

Tabel TER (PPh 21 TER Table) untuk TER

✅ Aktifkan opsi "Use TER for Monthly Calculation" jika menggunakan metode TER.

📂 Struktur Modul
BPJS Settings – Konfigurasi tarif dan batas gaji

BPJS Account Mapping – Pemetaan akun per perusahaan

PPh 21 Settings – Pengaturan metode pajak

Salary Slip – Override validasi & komponen Indonesia

Journal Entry – Otomatisasi entri berdasarkan mapping

🧪 Status
Modul ini sedang dikembangkan secara aktif dan digunakan di lingkungan produksi. Silakan laporkan bug atau request fitur di GitHub Issues.