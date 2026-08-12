PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tickets (
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    user TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    metadata TEXT NOT NULL,
    raw_payload TEXT,

    PRIMARY KEY (source, source_id)
);

CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,

    ticket_source TEXT NOT NULL,
    ticket_source_id TEXT NOT NULL,

    state TEXT NOT NULL,
    category TEXT,
    priority TEXT,

    FOREIGN KEY (ticket_source, ticket_source_id)
        REFERENCES tickets(source, source_id)
);