## Healthcare Eligibility Pipeline

### What it does
- Reads eligibility files from multiple partners (config-driven)
- Maps partner columns to a standard schema:
  external_id, first_name, last_name, dob, email, phone, partner_code
- Standardizes values (title case names, ISO dob, phone formatting, etc.)
- Outputs a unified CSV

### How to run
1. Put input files in `data/` (not committed)
2. Run:
   python src/pipeline.py --data-dir data --output output/unified_eligibility.csv

### Adding a new partner
- Add a new entry in `PARTNER_CONFIGS` with:
  - delimiter
  - partner_code
  - file_name
  - column_mapping
### Output in this case of sample data

<img width="810" height="172" alt="image" src="https://github.com/user-attachments/assets/ea1467bf-86d6-492f-bcce-af1642ab6614" />
