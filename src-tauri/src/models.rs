use serde::{Serialize, Deserialize};
use serde_json::Value;

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub enum ProjectStatus {
    Empty,
    Loading,
    Active,
    Review,
    Rendering,
    Complete,
    Error,
}

impl ToString for ProjectStatus {
    fn to_string(&self) -> String {
        match self {
            ProjectStatus::Empty => "Empty".to_string(),
            ProjectStatus::Loading => "Loading".to_string(),
            ProjectStatus::Active => "Active".to_string(),
            ProjectStatus::Review => "Review".to_string(),
            ProjectStatus::Rendering => "Rendering".to_string(),
            ProjectStatus::Complete => "Complete".to_string(),
            ProjectStatus::Error => "Error".to_string(),
        }
    }
}

impl From<&str> for ProjectStatus {
    fn from(s: &str) -> Self {
        match s {
            "Loading" => ProjectStatus::Loading,
            "Active" => ProjectStatus::Active,
            "Review" => ProjectStatus::Review,
            "Rendering" => ProjectStatus::Rendering,
            "Complete" => ProjectStatus::Complete,
            "Error" => ProjectStatus::Error,
            _ => ProjectStatus::Empty,
        }
    }
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Project {
    pub id: String,
    pub name: String,
    pub status: ProjectStatus,
    pub created_at: i64,
    pub updated_at: i64,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Media {
    pub id: String,
    pub project_id: String,
    pub file_path: String,
    pub duration_sec: f64,
    pub format: Option<String>,
    pub fps: Option<f64>,
    pub resolution: Option<String>,
    pub audio_codec: Option<String>,
    pub video_codec: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct CommentarySegment {
    pub timestamp_start: f64,
    pub timestamp_end: f64,
    pub text: String,
    pub source_reference: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct EditorialData {
    pub project_id: String,
    pub mode: String, // e.g. "hook_only", "hook_commentary", "full"
    pub transcript_json: Option<Value>,
    pub hook_text: Option<String>,
    pub commentary_segments: Option<Vec<CommentarySegment>>,
    pub takeaway_text: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub enum JobStatus {
    Pending,
    Running,
    Success,
    Failed,
}

impl ToString for JobStatus {
    fn to_string(&self) -> String {
        match self {
            JobStatus::Pending => "Pending".to_string(),
            JobStatus::Running => "Running".to_string(),
            JobStatus::Success => "Success".to_string(),
            JobStatus::Failed => "Failed".to_string(),
        }
    }
}

impl From<&str> for JobStatus {
    fn from(s: &str) -> Self {
        match s {
            "Running" => JobStatus::Running,
            "Success" => JobStatus::Success,
            "Failed" => JobStatus::Failed,
            _ => JobStatus::Pending,
        }
    }
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Job {
    pub id: String,
    pub project_id: String,
    pub job_type: String, // e.g. "Transcribe", "AI_Editorial", "TTS", "Render"
    pub status: JobStatus,
    pub progress: f64,
    pub error_message: Option<String>,
    pub created_at: i64,
    pub completed_at: Option<i64>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Output {
    pub id: String,
    pub project_id: String,
    pub file_path: String,
    pub output_type: String, // "Clip", "Audio", "Subtitles"
    pub created_at: i64,
}
