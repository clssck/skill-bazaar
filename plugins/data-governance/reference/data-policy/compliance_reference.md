# Compliance Regulations Reference

Quick reference for common data protection regulations and their implications for Snowflake policies. Use the linked official sources in each section to make authoritative judgements.

---

## PCI-DSS (Payment Card Industry Data Security Standard)

**Applies to:** Any organization that stores, processes, or transmits payment card data.

**Key data elements:**

> 📚 Check the [PCI Security Standards Document Library](https://docs.pcisecuritystandards.org/) to find sensitive fields that need to be masked/tokenized for PCI compliance. Once you've identified those fields, use the sample policy below to mask the column.

**Snowflake implementation:**
```sql
-- Mask full card number (show last 4 only)
CREATE MASKING POLICY pci_card_mask AS (val STRING) RETURNS STRING ->
  CASE
    WHEN IS_ROLE_IN_SESSION('PCI_AUTHORIZED') THEN val
    ELSE CONCAT('****-****-****-', RIGHT(val, 4))
  END
  COMMENT = 'PCI-DSS: Mask card numbers, show last 4 digits only';
```

**Example Red flags to check:**
- [ ] CVV stored anywhere in database → **Delete immediately**
- [ ] Unencrypted card numbers → **Encrypt or tokenize**
- [ ] Card data accessible to non-essential roles → **Restrict access**


---

## HIPAA (Health Insurance Portability and Accountability Act)

**Applies to:** Healthcare providers, health plans, healthcare clearinghouses, and their business associates in the US.

**Protected Health Information (PHI):**

> 📚 Check the official HHS HIPAA resources to identify PHI that needs protection:
> - [HHS HIPAA Privacy Rule](https://www.hhs.gov/hipaa/for-professionals/privacy/index.html)
> - [HHS HIPAA Security Rule](https://www.hhs.gov/hipaa/for-professionals/security/index.html)
>
> Once you've identified sensitive fields, use the sample policies below.

**Minimum Necessary Rule:** Only the minimum amount of PHI necessary should be disclosed.

**Snowflake implementation:**
```sql
-- Row access: Restrict to treating provider
CREATE ROW ACCESS POLICY hipaa_patient_access AS (patient_id STRING)
RETURNS BOOLEAN ->
  EXISTS (
    SELECT 1 FROM provider_patient_assignments
    WHERE provider_id = CURRENT_USER()
      AND patient_id = patient_id
  );

-- Masking: Hide PHI from non-clinical roles
CREATE MASKING POLICY hipaa_phi_mask AS (val STRING) RETURNS STRING ->
  CASE
    WHEN IS_ROLE_IN_SESSION('CLINICAL_STAFF') THEN val
    WHEN IS_ROLE_IN_SESSION('BILLING') THEN val  -- Billing needs some PHI
    ELSE '***PHI_PROTECTED***'
  END
  COMMENT = 'HIPAA: PHI visible only to clinical staff and billing';
```

**Example Red flags to check:**
- [ ] PHI accessible to non-clinical staff → **Restrict to need-to-know**
- [ ] No audit trail for PHI access → **Enable access logging**
- [ ] PHI shared without authorization → **Implement consent tracking**

---

## GDPR (General Data Protection Regulation)

**Applies to:** Any organization processing personal data of EU residents, regardless of where the organization is located.

**Personal data categories and rights:**

> 📚 Check the official GDPR resources to identify personal data requiring protection:
> - [GDPR Full Text (gdpr-info.eu)](https://gdpr-info.eu/)
> - [UK ICO Guide to GDPR](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/)
> - [European Commission GDPR Overview](https://commission.europa.eu/law/law-topic/data-protection_en)
>
> Once you've identified sensitive fields and data subject rights, use the sample policies below.

**Snowflake implementation:**
```sql
-- Masking for non-EU processing
CREATE MASKING POLICY gdpr_pii_mask AS (val STRING, user_region STRING) 
RETURNS STRING ->
  CASE
    WHEN user_region != 'EU' THEN val  -- Non-EU data, normal access
    WHEN IS_ROLE_IN_SESSION('GDPR_PROCESSOR') THEN val
    ELSE '***GDPR_PROTECTED***'
  END
  COMMENT = 'GDPR: EU personal data requires authorized access';

-- Row access for data subject requests
CREATE ROW ACCESS POLICY gdpr_data_subject_access AS (email STRING)
RETURNS BOOLEAN ->
  CASE
    WHEN IS_ROLE_IN_SESSION('DATA_CONTROLLER') THEN TRUE
    WHEN CURRENT_USER() = email THEN TRUE  -- Self-service access
    ELSE FALSE
  END;
```

**Example Red flags to check:**
- [ ] EU data accessible without legal basis → **Document lawful basis**
- [ ] No process for erasure requests → **Implement deletion workflow**
- [ ] Cross-border transfers without safeguards → **Implement SCCs or adequacy**

---

## CCPA/CPRA (California Consumer Privacy Act / California Privacy Rights Act)

**Applies to:** Businesses that collect personal information of California residents and meet thresholds (revenue >$25M, or data on >100K consumers, or >50% revenue from selling data).

**Personal information categories and consumer rights:**

> 📚 Check the official California privacy resources to identify personal information requiring protection:
> - [California Privacy Protection Agency (CPPA) Regulations](https://cppa.ca.gov/regulations/)
> - [California Attorney General - CCPA](https://oag.ca.gov/privacy/ccpa)
> - [CCPA/CPRA Full Statute Text](https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml?division=3.&part=4.&lawCode=CIV&title=1.81.5)
>
> Once you've identified sensitive fields and consumer rights, use the sample policies below.

**Snowflake implementation:**
```sql
-- Tag to track CCPA-covered data
CREATE TAG ccpa_category ALLOWED_VALUES 
  'identifiers', 'commercial', 'internet_activity', 
  'geolocation', 'employment', 'education', 'inferences';

-- Masking for sensitive categories
CREATE MASKING POLICY ccpa_sensitive_mask AS (val STRING) RETURNS STRING ->
  CASE
    WHEN IS_ROLE_IN_SESSION('CCPA_PROCESSOR') THEN val
    ELSE '***CCPA_PROTECTED***'
  END
  COMMENT = 'CCPA: California consumer data protection';
```

**Example Red flags to check:**
- [ ] No "Do Not Sell" flag → **Implement opt-out tracking**
- [ ] Can't identify California residents → **Add geo/residency tracking**
- [ ] No deletion process → **Implement data subject request workflow**

---

## SOX (Sarbanes-Oxley Act)

**Applies to:** Public companies in the US and their auditors.

**Focus areas:**

> 📚 Check the official SOX resources to understand internal control requirements:
> - [SEC Sarbanes-Oxley Act Overview](https://www.sec.gov/spotlight/sarbanes-oxley.htm)
> - [PCAOB Auditing Standards](https://pcaobus.org/oversight/standards/auditing-standards)
> - [SOX Act Full Text (Congress.gov)](https://www.congress.gov/bill/107th-congress/house-bill/3763)
>
> Once you understand the requirements, use the sample policies below.

**Snowflake implementation:**
```sql
-- Row access: Only finance team can modify financial records
CREATE ROW ACCESS POLICY sox_financial_access AS (record_type STRING)
RETURNS BOOLEAN ->
  CASE
    WHEN record_type = 'FINANCIAL' AND NOT IS_ROLE_IN_SESSION('FINANCE_TEAM') THEN FALSE
    ELSE TRUE
  END;

-- Masking: Auditors can see, but not raw access
CREATE MASKING POLICY sox_financial_mask AS (val NUMBER) RETURNS NUMBER ->
  CASE
    WHEN IS_ROLE_IN_SESSION('FINANCE_TEAM') THEN val
    WHEN IS_ROLE_IN_SESSION('AUDITOR') THEN val
    ELSE NULL
  END
  COMMENT = 'SOX: Financial data restricted to finance and auditors';
```

**Example Red flags to check:**
- [ ] Financial data modifiable by non-finance → **Restrict write access**
- [ ] No audit trail for financial changes → **Enable change tracking**
- [ ] Data retention not enforced → **Implement retention policies**

---

## FERPA (Family Educational Rights and Privacy Act)

**Applies to:** Educational institutions receiving federal funding in the US.

**Protected education records:**

> 📚 Check the official FERPA resources to identify protected education records:
> - [FERPA General Guidance (Dept. of Education)](https://studentprivacy.ed.gov/ferpa)
> - [FERPA Regulations (eCFR Title 34, Part 99)](https://www.ecfr.gov/current/title-34/subtitle-A/part-99)
> - [Student Privacy Policy Office](https://studentprivacy.ed.gov/)
>
> Once you've identified protected records, use the sample policies below.

**Snowflake implementation:**
```sql
-- Masking: Student records restricted
CREATE MASKING POLICY ferpa_student_mask AS (val STRING) RETURNS STRING ->
  CASE
    WHEN IS_ROLE_IN_SESSION('REGISTRAR') THEN val
    WHEN IS_ROLE_IN_SESSION('FACULTY') THEN val  -- For enrolled students only
    ELSE '***FERPA_PROTECTED***'
  END
  COMMENT = 'FERPA: Student education records protection';

-- Row access: Faculty only see enrolled students
CREATE ROW ACCESS POLICY ferpa_enrollment_access AS (student_id STRING, course_id STRING)
RETURNS BOOLEAN ->
  EXISTS (
    SELECT 1 FROM faculty_courses fc
    JOIN enrollments e ON fc.course_id = e.course_id
    WHERE fc.faculty_id = CURRENT_USER()
      AND e.student_id = student_id
  );
```

**Example Red flags to check:**
- [ ] Student records accessible to all staff → **Restrict to need-to-know**
- [ ] Grades shared without consent → **Implement consent tracking**
- [ ] No parental access controls → **Track student age/consent status**

---

## Quick Regulation Lookup

| If you have... | And customers in... | Check for... |
|----------------|---------------------|--------------|
| Credit card data | Anywhere | **PCI-DSS** |
| Patient health data | US | **HIPAA** |
| Personal data | EU | **GDPR** |
| Consumer data | California | **CCPA/CPRA** |
| Financial reporting data | US (public company) | **SOX** |
| Student records | US | **FERPA** |
| Employee data | EU | **GDPR** |
| Biometric data | Illinois | **BIPA** |
| Children's data (<13) | US | **COPPA** |

