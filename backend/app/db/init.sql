

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
    CREATE ROLE app_user LOGIN PASSWORD 'app';
  END IF;
END $$;
GRANT USAGE, CREATE ON SCHEMA public TO app_user;

CREATE OR REPLACE FUNCTION refuse_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'append-only: % on % is forbidden (21 CFR Part 11 audit trail)',
    TG_OP, TG_TABLE_NAME USING ERRCODE = 'restrict_violation';
END; $$ LANGUAGE plpgsql;

CREATE TABLE territory (
  territory_id TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  country      CHAR(2) NOT NULL DEFAULT 'IN'
);

CREATE TABLE rep (
  rep_id       TEXT PRIMARY KEY,
  full_name    TEXT NOT NULL,
  email        TEXT UNIQUE,
  territory_id TEXT NOT NULL REFERENCES territory,
  role         TEXT NOT NULL DEFAULT 'field_rep'
);

CREATE TABLE hcp (
  hcp_id                 TEXT PRIMARY KEY,
  full_name              TEXT NOT NULL,
  npi                    TEXT UNIQUE,
  specialty              TEXT NOT NULL,
  institution            TEXT,
  city                   TEXT,
  country                CHAR(2) NOT NULL DEFAULT 'IN',
  territory_id           TEXT NOT NULL REFERENCES territory,
  decile                 SMALLINT,
  state_license_status   TEXT NOT NULL CHECK (state_license_status IN ('ACTIVE','LAPSED','SUSPENDED')),
  is_licensed_prescriber BOOLEAN NOT NULL,
  sample_eligible        BOOLEAN NOT NULL DEFAULT TRUE,
  email_opt_in           BOOLEAN NOT NULL DEFAULT FALSE,
  voice_consent_on_file  BOOLEAN NOT NULL DEFAULT FALSE,
  created_via            TEXT NOT NULL CHECK (created_via IN ('MDM','MIGRATION'))

);
CREATE INDEX hcp_name_trgm ON hcp USING gin (full_name gin_trgm_ops);

CREATE TABLE product (
  product_id                 TEXT PRIMARY KEY,
  brand_name                 TEXT NOT NULL,
  molecule                   TEXT NOT NULL,
  approved_indication        TEXT NOT NULL,
  country                    CHAR(2) NOT NULL DEFAULT 'IN',
  annual_sample_limit_per_hcp INT NOT NULL DEFAULT 12
);

CREATE TABLE material (
  material_id      TEXT PRIMARY KEY,
  mlr_code         TEXT NOT NULL UNIQUE,
  title            TEXT NOT NULL,
  version          TEXT,
  product_id       TEXT REFERENCES product,
  approved_indication TEXT,
  approval_date    DATE,
  expiration_date  DATE,
  country          CHAR(2) NOT NULL DEFAULT 'IN',
  status           TEXT NOT NULL CHECK (status IN ('APPROVED','EXPIRED','WITHDRAWN')),
  allowed_channels TEXT[] NOT NULL DEFAULT '{}',
  allowed_audiences TEXT[] NOT NULL DEFAULT '{}'
);

CREATE TABLE sample_lot (
  lot_id      TEXT PRIMARY KEY,
  product_id  TEXT REFERENCES product,
  lot_number  TEXT NOT NULL,
  expiry_date DATE NOT NULL,
  strength    TEXT,
  UNIQUE (product_id, lot_number)
);

CREATE TABLE rep_inventory (
  rep_inventory_id  TEXT PRIMARY KEY,
  rep_id            TEXT REFERENCES rep,
  lot_id            TEXT REFERENCES sample_lot,
  units_on_hand     INT NOT NULL CHECK (units_on_hand >= 0),
  last_reconciled_at TIMESTAMPTZ
);

CREATE TABLE consent (
  consent_ref     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hcp_id          TEXT NOT NULL REFERENCES hcp,
  consent_type    TEXT CHECK (consent_type IN ('voice_recording','transcription_only','ai_summarization')),
  consent_method  TEXT CHECK (consent_method IN ('verbal_on_record','written','pre_existing_profile_consent')),
  jurisdiction    TEXT NOT NULL,
  captured_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  valid_until     TIMESTAMPTZ,
  allows_recording_retention BOOLEAN NOT NULL DEFAULT FALSE,
  revoked_at      TIMESTAMPTZ
);

CREATE TABLE interactions (
  interaction_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rep_id           TEXT NOT NULL REFERENCES rep,
  hcp_id           TEXT REFERENCES hcp,
  territory_id     TEXT NOT NULL REFERENCES territory,
  status           TEXT NOT NULL DEFAULT 'DRAFT'
                     CHECK (status IN ('DRAFT','PENDING_RECONCILIATION','SUBMITTED','AMENDED')),
  locked           BOOLEAN NOT NULL DEFAULT FALSE,
  current_version  INT NOT NULL DEFAULT 1,
  thread_id        TEXT,
  server_recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()

);

CREATE TABLE interaction_versions (
  version_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  interaction_id   UUID NOT NULL REFERENCES interactions ON DELETE RESTRICT,
  version          INT NOT NULL,
  snapshot         JSONB NOT NULL,
  diff             JSONB NOT NULL DEFAULT '[]',
  reason_code      TEXT,
  reason_for_change TEXT,
  actor_id         TEXT NOT NULL,
  actor_role       TEXT NOT NULL,
  requires_approval BOOLEAN NOT NULL DEFAULT FALSE,
  approved_by      TEXT,
  approved_at      TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (interaction_id, version),

  CONSTRAINT amendment_needs_reason CHECK (
    version = 1 OR (reason_for_change IS NOT NULL AND length(reason_for_change) >= 10)),

  CONSTRAINT inferred_sentiment_needs_quote CHECK (
    (snapshot->'sentiment'->>'source') IS DISTINCT FROM 'model_inferred'
    OR (snapshot->'sentiment'->>'rationale_quote') IS NOT NULL),

  CONSTRAINT voice_needs_consent CHECK (
    (snapshot->>'summary_provenance') IS DISTINCT FROM 'voice_transcript_extractive'
    OR (snapshot->>'consent_ref') IS NOT NULL)
);
CREATE TRIGGER trg_versions_append_only BEFORE UPDATE OR DELETE ON interaction_versions
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();

CREATE VIEW interaction_current AS
  SELECT i.*, v.snapshot, v.created_at AS version_created_at
  FROM interactions i
  JOIN interaction_versions v
    ON v.interaction_id = i.interaction_id AND v.version = i.current_version;

CREATE TABLE interaction_attendees (
  id             BIGSERIAL PRIMARY KEY,
  interaction_id UUID REFERENCES interactions ON DELETE CASCADE,
  version        INT NOT NULL,
  name           TEXT NOT NULL,
  hcp_id         TEXT REFERENCES hcp,
  role           TEXT,
  is_licensed_prescriber BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE interaction_materials (
  id             BIGSERIAL PRIMARY KEY,
  interaction_id UUID REFERENCES interactions ON DELETE CASCADE,
  version        INT NOT NULL,
  material_id    TEXT NOT NULL REFERENCES material,
  mlr_code_at_share TEXT NOT NULL,
  approval_status_at_share TEXT NOT NULL
);

CREATE TABLE sample_transactions (
  sample_transaction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  interaction_id  UUID REFERENCES interactions,
  hcp_id          TEXT NOT NULL REFERENCES hcp,
  rep_id          TEXT NOT NULL REFERENCES rep,
  product_id      TEXT NOT NULL REFERENCES product,
  lot_id          TEXT REFERENCES sample_lot,
  lot_number      TEXT NOT NULL,
  expiry_date     DATE NOT NULL,
  quantity        INT NOT NULL CHECK (quantity > 0),
  unit_of_measure TEXT NOT NULL DEFAULT 'units',
  delivery_method TEXT CHECK (delivery_method IN ('hand_delivered','mail_direct')),
  signature_artifact_ref TEXT,
  signature_datetime TIMESTAMPTZ,
  status          TEXT NOT NULL CHECK (status IN ('RECORDED','REJECTED','REVERSED','REVERSAL')),
  reverses_transaction_id UUID REFERENCES sample_transactions(sample_transaction_id),
  rejection_reason TEXT,
  compliance_result JSONB NOT NULL DEFAULT '{}',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_samples_write_once BEFORE UPDATE OR DELETE ON sample_transactions
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();

CREATE TABLE transfers_of_value (
  tov_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  interaction_id  UUID REFERENCES interactions,
  hcp_id          TEXT NOT NULL REFERENCES hcp,
  tov_type        TEXT NOT NULL CHECK (tov_type IN ('meal','travel','education','honoraria','gift')),
  amount          NUMERIC(12,2) NOT NULL,
  currency        CHAR(3) NOT NULL,
  per_attendee_allocation JSONB NOT NULL,
  recipient_npi   TEXT,
  reportable      BOOLEAN NOT NULL,
  reporting_year  INT
);

CREATE TABLE follow_up_actions (
  id             BIGSERIAL PRIMARY KEY,
  interaction_id UUID REFERENCES interactions ON DELETE CASCADE,
  action_type    TEXT NOT NULL CHECK (action_type IN (
    'schedule_meeting','send_approved_material','route_medical_inquiry_to_MSL',
    'add_to_event_invite_list','create_task')),
  target_ref     TEXT,
  label          TEXT NOT NULL,
  rationale_quote TEXT,
  confidence     REAL,
  origin         TEXT NOT NULL CHECK (origin IN ('ai_suggested','rep_entered')),
  decision       TEXT NOT NULL DEFAULT 'PENDING' CHECK (decision IN ('PENDING','ACCEPTED','REJECTED')),
  decided_by     TEXT,
  decided_at     TIMESTAMPTZ
);

CREATE TABLE audit_log (
  audit_id     BIGSERIAL PRIMARY KEY,
  ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor_id     TEXT NOT NULL,
  actor_type   TEXT NOT NULL CHECK (actor_type IN ('rep','agent','system','admin')),
  action       TEXT NOT NULL,
  entity_type  TEXT,
  entity_id    TEXT,
  thread_id    TEXT,
  tool_call_id TEXT,
  model_id     TEXT,
  before       JSONB,
  after        JSONB,
  reason       TEXT
);
CREATE TRIGGER trg_audit_append_only BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION refuse_mutation();

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;

GRANT TRUNCATE ON ALL TABLES IN SCHEMA public TO app_user;

REVOKE UPDATE, DELETE ON interaction_versions FROM app_user;
REVOKE UPDATE, DELETE ON sample_transactions  FROM app_user;
REVOKE UPDATE, DELETE ON audit_log            FROM app_user;
