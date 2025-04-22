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
bench get-app https://github.com/yourusername/payroll_indonesia
bench --site yoursite.local install-app payroll_indonesia
bench migrate