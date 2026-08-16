pub mod db;
pub mod models;

use uuid::Uuid;
use chrono::Utc;
use models::{Project, ProjectStatus};

fn main() {
    println!("ClipHub Rust Core Initialized.");
}

#[cfg(test)]
mod tests {
    use super::*;
    use db::{get_connection, create_project, get_project};
    use rusqlite::Result;

    #[test]
    fn test_db_initialization() -> Result<()> {
        let conn = get_connection()?;
        // Test that table exists by doing a simple query
        let mut stmt = conn.prepare("SELECT count(*) FROM projects")?;
        let count: i32 = stmt.query_row([], |row| row.get(0))?;
        assert_eq!(count, 0);
        Ok(())
    }

    #[test]
    fn test_project_crud() -> Result<()> {
        let conn = get_connection()?;
        
        let new_project = Project {
            id: Uuid::new_v4().to_string(),
            name: "Test Project".to_string(),
            status: ProjectStatus::Empty,
            created_at: Utc::now().timestamp(),
            updated_at: Utc::now().timestamp(),
        };

        create_project(&conn, &new_project)?;

        let retrieved = get_project(&conn, &new_project.id)?;
        assert_eq!(retrieved.id, new_project.id);
        assert_eq!(retrieved.name, new_project.name);
        assert_eq!(retrieved.status, ProjectStatus::Empty);

        Ok(())
    }
}
