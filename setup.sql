CREATE DATABASE radar_demo;

CREATE USER myuser WITH ENCRYPTED PASSWORD 'postgres';

GRANT ALL PRIVILEGES ON DATABASE radar_demo TO myuser;

\c radar_demo

CREATE TABLE conversations (
    id UUID PRIMARY KEY,
    url TEXT NOT NULL,
    media_type TEXT NOT NULL,
    user_insight TEXT NOT NULL,
    ai_analysis TEXT NOT NULL
);

CREATE TABLE messages (
    id UUID PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE webhooks (
    id UUID PRIMARY KEY,
    url TEXT NOT NULL,
    secret TEXT NOT NULL,
    events TEXT[] NOT NULL
);

ALTER TABLE conversations ADD COLUMN world_model JSONB;
