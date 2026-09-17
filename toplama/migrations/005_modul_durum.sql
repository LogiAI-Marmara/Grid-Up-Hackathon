-- 005_modul_durum.sql — track module health per packet.
--
-- Why: integration item 1. The module packet already carries `modul_durum`
-- (`besleme`, `sinyal`, `yazilim_surumu`), but the collector only recorded
-- `yazilim_surumu` on the `gridup.modul` reference row on sight. Power source
-- (`sebeke` vs `yedek`) and signal strength (`sinyal`) were dropped on the
-- floor.
--
-- Recording them per packet (one row per packet) preserves:
--   * the exact moment a power outage starts (transition sebeke -> yedek)
--   * battery/supercap drain duration in backup mode
--   * signal attenuation trends leading up to radio drops (scenario 7)
--
-- Natural key is (modul_id, zaman), doubling as the replay deduplication key:
-- retransmitted packets are dropped cleanly by ON CONFLICT DO NOTHING.

BEGIN;

CREATE TABLE IF NOT EXISTS gridup.modul_durum (
    modul_id        TEXT        NOT NULL REFERENCES gridup.modul (modul_id) ON DELETE CASCADE,
    zaman           TIMESTAMPTZ NOT NULL,
    besleme         TEXT        NOT NULL,
    sinyal          INTEGER     NOT NULL,
    yazilim_surumu  TEXT        NOT NULL,
    alindi_zaman    TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (modul_id, zaman),
    CONSTRAINT modul_durum_besleme CHECK (besleme IN ('sebeke', 'yedek')),
    CONSTRAINT modul_durum_sinyal CHECK (sinyal BETWEEN -120 AND 0),
    CONSTRAINT modul_durum_surum CHECK (yazilim_surumu ~ '^\d+\.\d+\.\d+$')
);

COMMENT ON TABLE gridup.modul_durum IS
    'Per-packet module health log: power source (sebeke/yedek), radio signal strength, and firmware version.';

COMMENT ON COLUMN gridup.modul_durum.besleme IS
    'Power source at sample time: sebeke (mains 230 VAC) or yedek (supercapacitor / backup).';

COMMENT ON COLUMN gridup.modul_durum.sinyal IS
    'Received signal strength in dBm, integer between -120 and 0.';

CREATE INDEX IF NOT EXISTS modul_durum_zaman_idx
    ON gridup.modul_durum (zaman DESC);

INSERT INTO gridup.sema_surum (surum, ad)
VALUES (5, '005_modul_durum')
ON CONFLICT (surum) DO UPDATE SET ad = EXCLUDED.ad;

COMMIT;
