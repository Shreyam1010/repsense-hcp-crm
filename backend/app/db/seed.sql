

TRUNCATE
  transfers_of_value, follow_up_actions, audit_log,
  sample_transactions, interaction_materials, interaction_attendees,
  interaction_versions, interactions,
  consent, rep_inventory, sample_lot, material, product, hcp, rep, territory
  CASCADE;

INSERT INTO territory (territory_id, name, country) VALUES
  ('IN-South-02', 'India — South 2 (Chennai)', 'IN'),
  ('IN-North-01', 'India — North 1 (Delhi)',   'IN'),
  ('US-NE-05',    'US — Northeast 5',           'US');

INSERT INTO rep (rep_id, full_name, email, territory_id, role) VALUES
  ('REP-001', 'Aarav Menon', 'aarav.menon@repsense.example', 'IN-South-02', 'field_rep');

INSERT INTO hcp (hcp_id, full_name, npi, specialty, institution, city, country,
                 territory_id, decile, state_license_status, is_licensed_prescriber,
                 sample_eligible, email_opt_in, voice_consent_on_file, created_via) VALUES

  ('HCP-001','Dr. Priya Sharma','1487500011','Medical Oncology','Apollo Cancer Centre','Chennai','IN',
   'IN-South-02', 9,'ACTIVE',  true,  true,  true,  true,  'MDM'),

  ('HCP-002','Dr. Anil Sharma','1487500022','Cardiology','Fortis Malar','Chennai','IN',
   'IN-South-02', 6,'ACTIVE',  true,  true,  false, false, 'MDM'),

  ('HCP-003','Dr. Rajesh Iyer','1487500033','Hematology-Oncology','Tata Memorial Hospital','Mumbai','IN',
   'IN-South-02', 8,'ACTIVE',  true,  true,  true,  false, 'MDM'),

  ('HCP-004','Dr. Vikram Rao','1487500044','Medical Oncology','AIIMS Delhi','Delhi','IN',
   'IN-North-01', 7,'ACTIVE',  true,  true,  false, false, 'MDM'),

  ('HCP-005','Ms. Latha R','1487500055','Practice Manager','Apollo Cancer Centre','Chennai','IN',
   'IN-South-02', NULL,'ACTIVE', false, false, false, false, 'MDM'),

  ('HCP-006','Dr. Michael Chen','1902500066','Medical Oncology','Valley Cancer Associates','Boston','US',
   'US-NE-05', 8,'ACTIVE',  true,  true,  false, false, 'MDM');

INSERT INTO product (product_id, brand_name, molecule, approved_indication, country,
                     annual_sample_limit_per_hcp) VALUES
  ('PRD-ONC','OncoBoost','ribocretinib',
   'Second-line (2L) HER2-positive metastatic breast cancer in adults','IN', 12),
  ('PRD-CAR','CardiaSure','velasartan',
   'Hypertension in adults','IN', 12);

INSERT INTO material (material_id, mlr_code, title, version, product_id, approved_indication,
                      approval_date, expiration_date, country, status,
                      allowed_channels, allowed_audiences) VALUES

  ('MAT-0142','MLR-2026-ONC-0142','OncoBoost Phase III OASIS Trial Reprint','v1','PRD-ONC',
   '2L HER2+ mBC','2026-01-15','2027-03-31','IN','APPROVED',
   '{in_person,email,remote}','{oncologist,hemonc}'),

  ('MAT-0155','MLR-2026-ONC-0155','OncoBoost Dosing & Administration Guide','v2','PRD-ONC',
   '2L HER2+ mBC','2026-02-01','2027-06-30','IN','APPROVED',
   '{in_person,email}','{oncologist,hemonc,nurse}'),

  ('MAT-0098','MLR-2025-ONC-0098','OncoBoost Core Visual Aid','v2','PRD-ONC',
   '2L HER2+ mBC','2025-01-10','2026-06-30','IN','EXPIRED',
   '{in_person}','{oncologist}'),

  ('MAT-0161','MLR-2026-ONC-0161','OncoBoost Pediatric Data Deck','v1','PRD-ONC',
   'pediatric (investigational)','2026-03-01','2027-03-01','IN','WITHDRAWN',
   '{in_person}','{oncologist}'),

  ('MAT-0201','MLR-2026-ONC-0201','OncoBoost US Prescribing Information','v1','PRD-ONC',
   '2L HER2+ mBC','2026-01-20','2027-01-20','US','APPROVED',
   '{in_person,email}','{oncologist}'),
  ('MAT-0310','MLR-2026-CAR-0310','CardiaSure Patient Starter Brochure','v1','PRD-CAR',
   'hypertension','2026-02-10','2027-02-10','IN','APPROVED',
   '{in_person,email}','{cardiologist,gp}');

INSERT INTO sample_lot (lot_id, product_id, lot_number, expiry_date, strength) VALUES
  ('LOT-OB-A','PRD-ONC','OB-2410-A','2027-08-31','150mg'),
  ('LOT-OB-B','PRD-ONC','OB-2308-B','2026-05-31','150mg'),
  ('LOT-CS-A','PRD-CAR','CS-2405-A','2027-12-31','40mg');

INSERT INTO rep_inventory (rep_inventory_id, rep_id, lot_id, units_on_hand, last_reconciled_at) VALUES
  ('INV-1','REP-001','LOT-OB-A', 24, now() - interval '2 days'),
  ('INV-2','REP-001','LOT-OB-B',  6, now() - interval '2 days'),
  ('INV-3','REP-001','LOT-CS-A', 40, now() - interval '2 days');

INSERT INTO consent (consent_ref, hcp_id, consent_type, consent_method, jurisdiction,
                     valid_until, allows_recording_retention) VALUES
  ('a0000000-0000-0000-0000-0000000000c1','HCP-001','voice_recording','pre_existing_profile_consent',
   'IN', now() + interval '180 days', false);

INSERT INTO interactions (interaction_id, rep_id, hcp_id, territory_id, status, locked,
                          current_version, server_recorded_at) VALUES
  ('aaaa1111-0000-0000-0000-000000000001','REP-001','HCP-001','IN-South-02','SUBMITTED',true,1, now() - interval '60 days'),
  ('aaaa1111-0000-0000-0000-000000000002','REP-001','HCP-001','IN-South-02','SUBMITTED',true,1, now() - interval '30 days'),
  ('aaaa1111-0000-0000-0000-000000000003','REP-001','HCP-001','IN-South-02','SUBMITTED',true,1, now() - interval '12 days');

INSERT INTO interaction_versions (interaction_id, version, snapshot, actor_id, actor_role, created_at) VALUES
  ('aaaa1111-0000-0000-0000-000000000001',1,
   '{"interaction_type":"face_to_face","summary_text":"Intro call. Discussed OASIS Phase III design.","sentiment":{"label":"neutral","source":"rep_stated","rationale_quote":"open to data"},"topics_discussed":[{"product_id":"PRD-ONC","key_message":"OASIS design"}]}',
   'REP-001','field_rep', now() - interval '60 days'),
  ('aaaa1111-0000-0000-0000-000000000002',1,
   '{"interaction_type":"face_to_face","summary_text":"Reviewed efficacy subgroup data. Positive engagement.","sentiment":{"label":"positive","source":"rep_stated","rationale_quote":"impressed by ORR"},"topics_discussed":[{"product_id":"PRD-ONC","key_message":"subgroup efficacy"}]}',
   'REP-001','field_rep', now() - interval '30 days'),
  ('aaaa1111-0000-0000-0000-000000000003',1,
   '{"interaction_type":"face_to_face","summary_text":"Raised access. OncoBoost not yet on Apollo formulary.","sentiment":{"label":"negative","barrier_code":"formulary_not_listed","source":"rep_stated","rationale_quote":"cannot prescribe until formulary adds it"},"topics_discussed":[{"product_id":"PRD-ONC","key_message":"access / formulary"}]}',
   'REP-001','field_rep', now() - interval '12 days');

INSERT INTO follow_up_actions (interaction_id, action_type, target_ref, label, origin, decision) VALUES
  ('aaaa1111-0000-0000-0000-000000000003','create_task',NULL,
   'Share formulary dossier with Apollo P&T committee','rep_entered','ACCEPTED');
