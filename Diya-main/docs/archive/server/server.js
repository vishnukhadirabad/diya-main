// Diya Meditation — visitor registration API (Model B: phone-scans-kiosk).
//
// Flow:
//   1. Kiosk:  POST /api/sessions            -> { token }
//      Kiosk shows a QR of  <site>/?session=<token>
//   2. Phone:  opens that URL, fills the form, submits:
//              POST /api/visitors { name, email, age, session } -> { id, linked }
//      (linked=true means the session was matched and claimed)
//   3. Kiosk:  polls GET /api/sessions/:token
//              -> { status:"pending" }                     (waiting)
//              -> { status:"claimed", visitor:{...} }       (done -> kiosk advances)
//
// Legacy/fallback still supported:
//   GET /api/visitors/:id   -> look up a standalone pass by id
//
// Also serves the static registration website from ../registration.

const path = require('path');
const crypto = require('crypto');
const express = require('express');
const cors = require('cors');
const { pool, init } = require('./db');

const app = express();
app.use(cors());
app.use(express.json({ limit: '4mb' })); // roster uploads can carry a few hundred rows

app.use(express.static(path.join(__dirname, '..', 'registration')));

// Admin key used to protect roster upload. Set ADMIN_KEY in the environment.
// If it is not set, admin endpoints are refused (fail closed) rather than open.
const ADMIN_KEY = process.env.ADMIN_KEY || '';
function requireAdmin(req, res, next) {
  if (!ADMIN_KEY) {
    return res.status(503).json({ error: 'admin disabled: set ADMIN_KEY on the server' });
  }
  const provided = req.get('x-admin-key') || '';
  if (provided !== ADMIN_KEY) {
    return res.status(401).json({ error: 'invalid admin key' });
  }
  return next();
}

// Short, human-friendly visitor id. Excludes ambiguous chars (0/O/1/I/L).
const ID_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
function makeId(len = 8) {
  const bytes = crypto.randomBytes(len);
  let out = '';
  for (let i = 0; i < len; i++) out += ID_ALPHABET[bytes[i] % ID_ALPHABET.length];
  return out;
}

// URL-safe random session token (hard to guess).
function makeToken() {
  return crypto.randomBytes(9).toString('base64url'); // ~12 chars
}

// Longer URL-safe token for a person's permanent login link.
function makePersonToken() {
  return crypto.randomBytes(16).toString('base64url'); // ~22 chars
}

app.get('/api/health', (_req, res) => res.json({ ok: true }));

// Nicer URLs for the two extra pages (the files are also served statically).
app.get('/admin', (_req, res) =>
  res.sendFile(path.join(__dirname, '..', 'registration', 'admin.html')));
app.get('/p/:token', (_req, res) =>
  res.sendFile(path.join(__dirname, '..', 'registration', 'scan.html')));

// ---- Sessions (Model B) -------------------------------------------------

// Kiosk starts a session and shows its token as a QR.
app.post('/api/sessions', async (_req, res) => {
  try {
    for (let attempt = 0; attempt < 5; attempt++) {
      const token = makeToken();
      try {
        await pool.query('INSERT INTO sessions (token) VALUES ($1)', [token]);
        return res.status(201).json({ token });
      } catch (err) {
        if (err.code === '23505') continue; // collision -> retry
        throw err;
      }
    }
    return res.status(500).json({ error: 'could not allocate a session' });
  } catch (err) {
    console.error('POST /api/sessions failed:', err);
    return res.status(500).json({ error: 'internal error' });
  }
});

// Kiosk polls this until the visitor registers on their phone.
app.get('/api/sessions/:token', async (req, res) => {
  try {
    const token = String(req.params.token || '');
    const { rows } = await pool.query(
      `SELECT s.status, v.id, v.name, v.email, v.age, v.image_url
         FROM sessions s
         LEFT JOIN visitors v ON v.id = s.visitor_id
        WHERE s.token = $1`,
      [token]
    );
    if (rows.length === 0) return res.status(404).json({ status: 'not_found' });

    const r = rows[0];
    if (r.status === 'claimed' && r.id) {
      return res.json({
        status: 'claimed',
        visitor: { id: r.id, name: r.name, email: r.email, age: r.age, image_url: r.image_url || '' },
      });
    }
    return res.json({ status: 'pending', visitor: null });
  } catch (err) {
    console.error('GET /api/sessions/:token failed:', err);
    return res.status(500).json({ error: 'internal error' });
  }
});

// ---- Visitors -----------------------------------------------------------

// Register a visitor. If a session token is supplied (phone opened the kiosk's
// QR link), claim that session and link it to the new visitor.
app.post('/api/visitors', async (req, res) => {
  try {
    const name = String(req.body?.name ?? '').trim();
    const email = String(req.body?.email ?? '').trim();
    let age = Number.parseInt(req.body?.age, 10);
    if (!Number.isFinite(age) || age < 0) age = 0;
    const session = req.body?.session ? String(req.body.session) : null;

    if (!name) return res.status(400).json({ error: 'name is required' });

    let id = null;
    for (let attempt = 0; attempt < 5; attempt++) {
      const candidate = makeId(8);
      try {
        await pool.query(
          'INSERT INTO visitors (id, name, email, age) VALUES ($1, $2, $3, $4)',
          [candidate, name, email, age]
        );
        id = candidate;
        break;
      } catch (err) {
        if (err.code === '23505') continue; // unique_violation -> new id
        throw err;
      }
    }
    if (!id) return res.status(500).json({ error: 'could not allocate a unique id' });

    let linked = false;
    if (session) {
      const upd = await pool.query(
        `UPDATE sessions
            SET visitor_id = $1, status = 'claimed', claimed_at = now()
          WHERE token = $2 AND status = 'pending'`,
        [id, session]
      );
      linked = upd.rowCount > 0;
    }

    return res.status(201).json({ id, linked });
  } catch (err) {
    console.error('POST /api/visitors failed:', err);
    return res.status(500).json({ error: 'internal error' });
  }
});

// Legacy: look up a standalone pass by id.
app.get('/api/visitors/:id', async (req, res) => {
  try {
    const id = String(req.params.id || '').trim().toUpperCase();
    const { rows } = await pool.query(
      'SELECT id, name, email, age FROM visitors WHERE id = $1',
      [id]
    );
    if (rows.length === 0) return res.status(404).json({ error: 'not found' });
    return res.json(rows[0]);
  } catch (err) {
    console.error('GET /api/visitors/:id failed:', err);
    return res.status(500).json({ error: 'internal error' });
  }
});

// ---- Roster (admin-loaded) + reverse-scan claim -------------------------

// Map arbitrary sheet headers onto canonical fields. The admin page parses the
// XLSX in the browser (SheetJS) and posts plain JSON rows keyed by the sheet's
// own header text, e.g. { "Name": "...", "Email Id": "...", "Image": "..." }.
function normalizePerson(row) {
  const pick = (...wanted) => {
    for (const key of Object.keys(row)) {
      const norm = key.trim().toLowerCase().replace(/\s+/g, '');
      // Substring match so real-world headers like "Image Link (Gdrive ...)"
      // or "Email Id" still map correctly.
      if (wanted.some((w) => norm.includes(w))) {
        const v = row[key];
        return v == null ? '' : String(v).trim();
      }
    }
    return '';
  };
  return {
    name: pick('name', 'fullname'),
    role: pick('role', 'designation'),
    aadhar: pick('aadhar', 'aadhaar', 'aadharno', 'aadhaarnumber', 'aadharnumber'),
    email: pick('emailid', 'email', 'emailaddress'),
    image: pick('image', 'imageurl', 'photo', 'picture'),
  };
}

// Admin uploads a parsed roster: { people: [ { Name, Role, Aadhar, "Email Id", Image }, ... ] }.
// Each valid row becomes a person with a unique token; returns their login links.
app.post('/api/admin/upload', requireAdmin, async (req, res) => {
  try {
    const rows = Array.isArray(req.body?.people) ? req.body.people : null;
    if (!rows) return res.status(400).json({ error: 'expected { people: [...] }' });

    const created = [];
    const skipped = [];
    for (let i = 0; i < rows.length; i++) {
      const p = normalizePerson(rows[i] || {});
      if (!p.name) { skipped.push({ row: i + 1, reason: 'missing name' }); continue; }

      let token = null;
      for (let attempt = 0; attempt < 5 && !token; attempt++) {
        const candidate = makePersonToken();
        try {
          await pool.query(
            `INSERT INTO people (token, name, role, aadhar, email, image_url)
             VALUES ($1, $2, $3, $4, $5, $6)`,
            [candidate, p.name, p.role, p.aadhar, p.email, p.image]
          );
          token = candidate;
        } catch (err) {
          if (err.code === '23505') continue; // token collision -> retry
          throw err;
        }
      }
      if (!token) { skipped.push({ row: i + 1, reason: 'could not allocate token' }); continue; }

      created.push({ token, name: p.name, role: p.role, path: `/p/${token}` });
    }

    return res.status(201).json({ created, skipped, count: created.length });
  } catch (err) {
    console.error('POST /api/admin/upload failed:', err);
    return res.status(500).json({ error: 'internal error' });
  }
});

// Public: the scan page fetches this to greet the person by name.
// Returns ONLY name + role — never the Aadhaar or email.
app.get('/api/people/:token', async (req, res) => {
  try {
    const token = String(req.params.token || '');
    const { rows } = await pool.query(
      'SELECT name, role FROM people WHERE token = $1',
      [token]
    );
    if (rows.length === 0) return res.status(404).json({ error: 'not found' });
    return res.json({ name: rows[0].name, role: rows[0].role });
  } catch (err) {
    console.error('GET /api/people/:token failed:', err);
    return res.status(500).json({ error: 'internal error' });
  }
});

// The person's phone scanned the kiosk's QR. Link this pre-known person to the
// session so the polling kiosk advances. We reuse the existing claim mechanic:
// materialise a visitor row from the person, then claim the session — so the
// C# kiosk needs no changes at all.
app.post('/api/claim', async (req, res) => {
  try {
    const personToken = String(req.body?.person ?? '').trim();
    const sessionToken = String(req.body?.session ?? '').trim();
    if (!personToken || !sessionToken) {
      return res.status(400).json({ error: 'person and session are required' });
    }

    const people = await pool.query(
      'SELECT name, email, image_url FROM people WHERE token = $1',
      [personToken]
    );
    if (people.rows.length === 0) {
      return res.status(404).json({ error: 'unknown person link' });
    }
    const person = people.rows[0];

    const sess = await pool.query('SELECT status FROM sessions WHERE token = $1', [sessionToken]);
    if (sess.rows.length === 0) {
      return res.status(404).json({ error: 'unknown session — scan the kiosk code again' });
    }
    if (sess.rows[0].status !== 'pending') {
      return res.status(409).json({ error: 'this kiosk code was already used' });
    }

    // Materialise a visitor from the person (age isn't in the roster -> 0).
    let visitorId = null;
    for (let attempt = 0; attempt < 5 && !visitorId; attempt++) {
      const candidate = makeId(8);
      try {
        await pool.query(
          'INSERT INTO visitors (id, name, email, age, image_url) VALUES ($1, $2, $3, 0, $4)',
          [candidate, person.name, person.email, person.image_url || '']
        );
        visitorId = candidate;
      } catch (err) {
        if (err.code === '23505') continue;
        throw err;
      }
    }
    if (!visitorId) return res.status(500).json({ error: 'could not allocate a visitor id' });

    const upd = await pool.query(
      `UPDATE sessions
          SET visitor_id = $1, status = 'claimed', claimed_at = now()
        WHERE token = $2 AND status = 'pending'`,
      [visitorId, sessionToken]
    );
    if (upd.rowCount === 0) {
      return res.status(409).json({ error: 'this kiosk code was already used' });
    }

    return res.json({ ok: true, name: person.name });
  } catch (err) {
    console.error('POST /api/claim failed:', err);
    return res.status(500).json({ error: 'internal error' });
  }
});

const PORT = process.env.PORT || 3000;
init()
  .then(() => app.listen(PORT, () => console.log(`Diya registration server listening on :${PORT}`)))
  .catch((err) => {
    console.error('DB init failed:', err);
    process.exit(1);
  });
