-- Reference schema (the server also creates this automatically on startup via db.js init()).

CREATE TABLE IF NOT EXISTS visitors (
  id         TEXT PRIMARY KEY,        -- short code (e.g. "7F3KM9AC")
  name       TEXT NOT NULL,
  email      TEXT NOT NULL DEFAULT '',
  age        INTEGER NOT NULL DEFAULT 0,
  image_url  TEXT NOT NULL DEFAULT '', -- direct image URL, copied from the roster on claim
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Model B: kiosk-initiated sessions. The kiosk shows a QR of <site>/?session=<token>;
-- the phone registers against it; the kiosk polls until the session is "claimed".
CREATE TABLE IF NOT EXISTS sessions (
  token      TEXT PRIMARY KEY,        -- URL-safe random token shown in the kiosk QR
  status     TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'claimed'
  visitor_id TEXT,                     -- set when claimed
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  claimed_at TIMESTAMPTZ
);

-- Admin-loaded roster. An admin uploads a sheet (Name / Role / Aadhar / Email Id /
-- Image); each row becomes a person with a unique "token". That token is their
-- personal login link (<site>/p/<token>). Opening it and scanning the kiosk QR
-- claims a session for this pre-known identity. Aadhaar/email are sensitive and
-- are never exposed by the public /api/people/:token endpoint.
CREATE TABLE IF NOT EXISTS people (
  token      TEXT PRIMARY KEY,        -- unguessable per-person URL token
  name       TEXT NOT NULL,
  role       TEXT NOT NULL DEFAULT '',
  aadhar     TEXT NOT NULL DEFAULT '',
  email      TEXT NOT NULL DEFAULT '',
  image_url  TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
