MIGRATIONS = [
    """
    CREATE TABLE listings (
      id INTEGER PRIMARY KEY,
      source TEXT NOT NULL,
      source_id TEXT NOT NULL,
      url TEXT NOT NULL,
      title TEXT,
      price INTEGER,
      beds REAL,
      baths REAL,
      sqft INTEGER,
      lat REAL,
      lng REAL,
      posted_at TIMESTAMP,
      raw_text TEXT,
      photos_json TEXT,
      first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(source, source_id)
    );
    """,
    """
    CREATE TABLE verdicts (
      listing_id INTEGER PRIMARY KEY REFERENCES listings(id),
      llm_verdict TEXT,
      llm_reasons TEXT,
      user_action TEXT NOT NULL DEFAULT 'pending',
      user_action_at TIMESTAMP
    );
    """,
    """
    CREATE TABLE notifications (
      id INTEGER PRIMARY KEY,
      listing_id INTEGER REFERENCES listings(id),
      channel TEXT,
      sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(listing_id, channel)
    );
    """,
    """
    CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
    """,
]
