use rusqlite::{Connection, Result};

pub fn init_db(conn: &Connection) -> Result<()> {
    conn.execute(
        "CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )",
        [],
    )?;

    conn.execute(
        "CREATE TABLE IF NOT EXISTS media (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            duration_sec REAL NOT NULL,
            format TEXT,
            fps REAL,
            resolution TEXT,
            audio_codec TEXT,
            video_codec TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )",
        [],
    )?;

    conn.execute(
        "CREATE TABLE IF NOT EXISTS editorial_data (
            project_id TEXT PRIMARY KEY,
            mode TEXT NOT NULL,
            transcript_json TEXT,
            hook_text TEXT,
            commentary_segments TEXT,
            takeaway_text TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )",
        [],
    )?;

    conn.execute(
        "CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            job_type TEXT NOT NULL,
            status TEXT NOT NULL,
            progress REAL NOT NULL,
            error_message TEXT,
            created_at INTEGER NOT NULL,
            completed_at INTEGER,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )",
        [],
    )?;

    conn.execute(
        "CREATE TABLE IF NOT EXISTS outputs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            output_type TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )",
        [],
    )?;

    Ok(())
}
