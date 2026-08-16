pub mod schema;

use rusqlite::{Connection, Result};
use crate::models::{Project, ProjectStatus};

pub fn get_connection() -> Result<Connection> {
    // For tests, use an in-memory DB.
    let conn = Connection::open_in_memory()?;
    schema::init_db(&conn)?;
    Ok(conn)
}

pub fn create_project(conn: &Connection, project: &Project) -> Result<()> {
    conn.execute(
        "INSERT INTO projects (id, name, status, created_at, updated_at) VALUES (?1, ?2, ?3, ?4, ?5)",
        (
            &project.id,
            &project.name,
            &project.status.to_string(),
            &project.created_at,
            &project.updated_at,
        ),
    )?;
    Ok(())
}

pub fn get_project(conn: &Connection, id: &str) -> Result<Project> {
    let mut stmt = conn.prepare("SELECT id, name, status, created_at, updated_at FROM projects WHERE id = ?1")?;
    let mut rows = stmt.query([id])?;

    if let Some(row) = rows.next()? {
        let status_str: String = row.get(2)?;
        Ok(Project {
            id: row.get(0)?,
            name: row.get(1)?,
            status: ProjectStatus::from(status_str.as_str()),
            created_at: row.get(3)?,
            updated_at: row.get(4)?,
        })
    } else {
        Err(rusqlite::Error::QueryReturnedNoRows)
    }
}
