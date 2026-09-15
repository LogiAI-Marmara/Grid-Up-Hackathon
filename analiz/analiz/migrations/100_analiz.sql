-- 100 — track B's own tables: the anomaly event, its journal, and the scan cursor.
--
-- Numbered from 100 so track A can keep adding 004, 005 ... without either
-- track having to ask the other what number is free.
--
-- Fields follow section 7.2 of the track B decision record, which amends
-- contract 3: `zaman` is replaced by the pair `ilk_gorulme` / `son_gorulme`,
-- `maks_seviye` is added, and `seviye` now carries the *current* value rather
-- than a value fixed at creation. That amendment has the lead's approval; the
-- schema file on track A's branch has not caught up yet, which is recorded in
-- the track B README under "Contract mismatches".

SET search_path TO gridup, public;

-- ---------------------------------------------------------------------------
-- anomali — one row per *episode*, not per detection. Decision K3.
-- ---------------------------------------------------------------------------
--
-- The volume argument, from section 6.2: a loose terminal fault lasts three
-- days, which at a 10 s scan period is 25,920 turns. One row per turn would be
-- 25,920 rows for one loose screw, and `durum` would become meaningless —
-- there would be nothing for an operator to acknowledge. So a turn that finds
-- the same condition again *updates* the open episode instead of inserting.

CREATE SEQUENCE IF NOT EXISTS gridup.anomali_sira;

CREATE TABLE IF NOT EXISTS gridup.anomali (
    -- Monotonic ordering, section 7.2: the alarm service reads "everything after
    -- the last id I handled" and must not be able to miss an episode. A sequence
    -- rather than a timestamp because two episodes can open in the same turn.
    sira          BIGINT      NOT NULL DEFAULT nextval('gridup.anomali_sira'),

    id            TEXT        PRIMARY KEY,
    modul_id      TEXT        NOT NULL REFERENCES gridup.modul (modul_id) ON DELETE CASCADE,
    tip           TEXT        NOT NULL,

    -- Current severity, and the worst this episode has ever reached. Both are
    -- needed: an operator triaging a queue sorts by what it got to, a dashboard
    -- showing live state shows what it is now.
    seviye        TEXT        NOT NULL,
    maks_seviye   TEXT        NOT NULL,
    skor          DOUBLE PRECISION NOT NULL,

    -- The episode's span in *measurement* time, not detector time. Lead time
    -- (section 2.5) is computed from ilk_gorulme, so it has to be the moment the
    -- grid misbehaved, not the moment a scan turn noticed.
    ilk_gorulme   TIMESTAMPTZ NOT NULL,
    son_gorulme   TIMESTAMPTZ NOT NULL,

    -- When the detector last confirmed this condition, in DETECTOR time.
    --
    -- Distinct from son_gorulme, and the distinction is not pedantry. son_gorulme
    -- is a measurement time: it belongs to the contract, and lead time is computed
    -- from its partner ilk_gorulme, so it must stay the moment the grid misbehaved.
    -- Hysteresis asks a different question — "how long since we last saw this?" —
    -- and that is about the detector's clock.
    --
    -- Conflating them breaks latched conditions. An arc that tripped 40 minutes
    -- ago is still in the evaluation window and still being found every turn, but
    -- its son_gorulme is already older than the 30-minute hysteresis, so the
    -- episode would close on the same turn that opened it and re-open on the next
    -- one, forever: one anomaly row per turn for a single arc, which is precisely
    -- the failure decision K3 exists to prevent.
    son_dogrulama TIMESTAMPTZ NOT NULL DEFAULT now(),

    durum         TEXT        NOT NULL DEFAULT 'acik',
    gerekce       TEXT        NOT NULL,
    kanit         JSONB,

    -- Which detector layer produced the current justification. Not part of the
    -- contract; kept because "which layer fired" is the first question asked of
    -- a false positive, and reconstructing it afterwards is guesswork.
    katman        SMALLINT,

    kapanma_zaman TIMESTAMPTZ,
    olusturma     TIMESTAMPTZ NOT NULL DEFAULT now(),
    guncelleme    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT anomali_id_bicim CHECK (id ~ '^[A-Za-z0-9_-]{1,64}$'),

    CONSTRAINT anomali_tip_gecerli CHECK (tip IN (
        'sicak_nokta', 'akim_sicaklik_sapmasi', 'faz_dengesizligi',
        'nem_yuksek', 'ortam_sicaklik_yuksek', 'ark',
        'sensor_arizasi', 'modul_saglik'
    )),

    -- 'normal' is deliberately not allowed: a normal reading produces no row at
    -- all (section 2.4), so a row claiming seviye 'normal' is a bug.
    CONSTRAINT anomali_seviye_gecerli CHECK (seviye IN ('izle', 'uyari', 'kritik')),
    CONSTRAINT anomali_maks_seviye_gecerli CHECK (maks_seviye IN ('izle', 'uyari', 'kritik')),
    CONSTRAINT anomali_durum_gecerli CHECK (durum IN ('acik', 'onaylandi', 'kapandi')),
    CONSTRAINT anomali_skor_araligi CHECK (skor BETWEEN 0 AND 1),
    CONSTRAINT anomali_gerekce_dolu CHECK (length(btrim(gerekce)) > 0),
    CONSTRAINT anomali_span CHECK (son_gorulme >= ilk_gorulme),
    CONSTRAINT anomali_kapanma_tutarli
        CHECK ((durum = 'kapandi') = (kapanma_zaman IS NOT NULL))
);

COMMENT ON TABLE gridup.anomali IS
    'Contract 3, as an episode. One row per (modul_id, tip) occurrence, opened once and updated, never re-inserted per scan turn.';
COMMENT ON COLUMN gridup.anomali.sira IS
    'Monotonic sequence so the alarm service can read "after the last one I saw" without missing an episode.';
COMMENT ON COLUMN gridup.anomali.ilk_gorulme IS
    'Measurement time of the first triggering sample. Lead time is measured from here.';
COMMENT ON COLUMN gridup.anomali.son_dogrulama IS
    'When the detector last confirmed the condition, in detector time. Hysteresis runs off this, not off son_gorulme.';
COMMENT ON COLUMN gridup.anomali.maks_seviye IS
    'Worst severity reached. seviye may fall back; this does not.';

-- Episode identity, section 6.5: same modul_id + same tip + not yet closed is
-- the *same* episode. A partial unique index is what makes that a database
-- guarantee rather than an intention — two concurrent turns cannot both open it.
CREATE UNIQUE INDEX IF NOT EXISTS anomali_acik_tekil
    ON gridup.anomali (modul_id, tip)
    WHERE durum <> 'kapandi';

CREATE UNIQUE INDEX IF NOT EXISTS anomali_sira_idx ON gridup.anomali (sira);

CREATE INDEX IF NOT EXISTS anomali_modul_idx      ON gridup.anomali (modul_id, son_gorulme DESC);
CREATE INDEX IF NOT EXISTS anomali_son_gorulme_idx ON gridup.anomali (son_gorulme DESC);

-- "Which episodes are still open?" runs every turn, once for the hysteresis
-- sweep and once per module for the layer 2 poisoning guard.
CREATE INDEX IF NOT EXISTS anomali_acik_idx
    ON gridup.anomali (modul_id, tip) WHERE durum <> 'kapandi';

-- ---------------------------------------------------------------------------
-- anomali_gecis — the journal. Section 6.4.
-- ---------------------------------------------------------------------------
--
-- ISA-18.2 models an alarm as a state machine, and SCADA products split it in
-- two: a status table holding what is active now, and a journal holding every
-- transition, permanently. `anomali` above is the status table; this is the
-- journal. The reason for keeping them apart is not display, it is the audit
-- trail — "when did this alarm come in, who saw it, when did it clear" is a
-- regulatory question in electricity distribution.

CREATE TABLE IF NOT EXISTS gridup.anomali_gecis (
    id          BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    anomali_id  TEXT        NOT NULL REFERENCES gridup.anomali (id) ON DELETE CASCADE,
    zaman       TIMESTAMPTZ NOT NULL,

    -- Which axis moved. The decision record's table says onceki/yeni is "a state
    -- or a severity change"; without this column a reader cannot tell which of
    -- the two vocabularies to interpret the values in.
    alan        TEXT        NOT NULL,
    onceki      TEXT,
    yeni        TEXT        NOT NULL,

    -- 'sistem' for anything the detector did; an operator identity for an
    -- acknowledgement. An acknowledgement is a transition too and carries
    -- who/when, which is half of what the audit trail is for.
    aktor       TEXT        NOT NULL DEFAULT 'sistem',
    aciklama    TEXT,
    olusturma   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT gecis_alan_gecerli CHECK (alan IN ('durum', 'seviye')),
    CONSTRAINT gecis_durum_degeri CHECK (
        alan <> 'durum' OR (
            (onceki IS NULL OR onceki IN ('acik', 'onaylandi', 'kapandi'))
            AND yeni IN ('acik', 'onaylandi', 'kapandi')
        )
    ),
    CONSTRAINT gecis_seviye_degeri CHECK (
        alan <> 'seviye' OR (
            (onceki IS NULL OR onceki IN ('normal', 'izle', 'uyari', 'kritik'))
            AND yeni IN ('normal', 'izle', 'uyari', 'kritik')
        )
    ),
    -- A transition from a value to itself is not a transition. Section 6.5: a
    -- score moving 0.81 -> 0.83 inside `uyari` is not an event the alarm service
    -- should ever hear about.
    CONSTRAINT gecis_gercek CHECK (onceki IS DISTINCT FROM yeni)
);

COMMENT ON TABLE gridup.anomali_gecis IS
    'Alarm journal: one permanent row per state or severity transition. The audit trail behind every episode.';

CREATE INDEX IF NOT EXISTS gecis_anomali_idx ON gridup.anomali_gecis (anomali_id, zaman);
CREATE INDEX IF NOT EXISTS gecis_zaman_idx   ON gridup.anomali_gecis (zaman DESC);

-- ---------------------------------------------------------------------------
-- tarama_imleci — the scan cursor. Decision K1, section 3.7.
-- ---------------------------------------------------------------------------
--
-- One row per named cursor. Named, not singular, because section 3.4's first
-- argument for polling over push is that history can be re-scanned when the
-- algorithm changes: a second cursor re-walks last week while `varsayilan`
-- keeps up with live data, and neither moves the other.
--
-- `son_islenen` holds an `alindi_zaman` (arrival), not a `zaman` (measurement
-- time). See TaramaAyari.imlec_alani for why: a module that goes quiet and then
-- dumps a backlog stamps those rows with old measurement times, and a cursor on
-- measurement time would have already passed them.

CREATE TABLE IF NOT EXISTS gridup.tarama_imleci (
    ad            TEXT        PRIMARY KEY,
    son_islenen   TIMESTAMPTZ NOT NULL,
    son_tur       TIMESTAMPTZ,
    son_tur_satir INTEGER     NOT NULL DEFAULT 0,
    son_tur_modul INTEGER     NOT NULL DEFAULT 0,
    tur_sayisi    BIGINT      NOT NULL DEFAULT 0,
    guncelleme    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT imlec_ad_dolu CHECK (length(btrim(ad)) > 0)
);

COMMENT ON TABLE gridup.tarama_imleci IS
    'Scan cursor. Persisted so a restart resumes where it stopped, and rewindable by hand so history can be re-scanned after an algorithm change.';
COMMENT ON COLUMN gridup.tarama_imleci.son_islenen IS
    'Last processed alindi_zaman (arrival time), exclusive lower bound of the next turn''s range.';

INSERT INTO gridup.sema_surum (surum, ad)
VALUES (100, '100_analiz')
ON CONFLICT (surum) DO NOTHING;
