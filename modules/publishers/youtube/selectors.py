"""DOM selectors and locator strategies for YouTube Studio automation.

# Verified: 2026-07-20 against YouTube Studio 
"""

from __future__ import annotations

# ─── Navigation & Upload Initiation ──────────────────────────────────────────
CREATE_BUTTON_SELECTORS = (
    "#create-icon",
    'button[aria-label="Create"]',
    'ytcp-button:has-text("CREATE")',
    'ytcp-icon-button[id="create-icon"]',
    'button:has-text("Create")',
)

UPLOAD_ITEM_SELECTORS = (
    'tp-yt-paper-item:has-text("Upload videos")',
    'paper-item:has-text("Upload videos")',
    'ytcp-text-menu-item:has-text("Upload videos")',
    '[aria-label="Upload videos"]',
)

DIRECT_UPLOAD_BUTTON_SELECTORS = (
    "#upload-icon",
    'ytcp-icon-button[aria-label="Upload videos"]',
    'ytcp-button:has-text("Upload videos")',
    'ytcp-upload-video-button',
)

FILE_INPUT_SELECTORS = (
    'input[type="file"][name="Filedata"]',
    'ytcp-uploads-dialog input[type="file"]',
    'input[type="file"]',
)

# ─── Metadata Step ────────────────────────────────────────────────────────────
TITLE_TEXTBOX_SELECTORS = (
    'ytcp-social-suggestions-textbox[aria-label*="title" i] #textbox',
    "#title-textarea #textbox",
    '#textbox[aria-label*="title" i]',
    '[role="dialog"] #title-textarea [contenteditable="true"]',
)

DESCRIPTION_TEXTBOX_SELECTORS = (
    'ytcp-social-suggestions-textbox[aria-label*="description" i] #textbox',
    "#description-textarea #textbox",
    '#textbox[aria-label*="description" i]',
    '[role="dialog"] #description-textarea [contenteditable="true"]',
)

THUMBNAIL_INPUT_SELECTORS = (
    'input[type="file"]#file-with-fallback',
    'ytcp-thumbnail-uploader input[type="file"]',
    'input[type="file"][accept*="image"]',
)

NOT_MADE_FOR_KIDS_SELECTORS = (
    'tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]',
    'ytkc-made-for-kids-select tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]',
    'tp-yt-paper-radio-button:has-text("No, it\'s not made for kids")',
    '[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]',
)

SHOW_MORE_BUTTON_SELECTORS = (
    "#toggle-button",
    'ytcp-button:has-text("SHOW MORE")',
    'ytcp-button:has-text("Show more")',
)

TAGS_INPUT_SELECTORS = (
    "#tags-container input",
    'ytcp-form-input-container[id="tags-container"] input',
    'input[aria-label="Tags"]',
)

# ─── Wizard Steps Navigation ──────────────────────────────────────────────────
NEXT_BUTTON_SELECTORS = (
    "#next-button",
    'ytcp-button[id="next-button"]',
    'ytcp-button:has-text("NEXT")',
    'button:has-text("Next")',
)

# ─── Visibility & Scheduling ──────────────────────────────────────────────────
SCHEDULE_RADIO_SELECTORS = (
    'tp-yt-paper-radio-button[name="SCHEDULE"]',
    '#second-container tp-yt-paper-radio-button[name="SCHEDULE"]',
    'tp-yt-paper-radio-button:has-text("Schedule")',
    "#schedule-radio-button",
)

DATE_INPUT_SELECTORS = (
    "#datepicker-trigger input",
    'ytcp-datepicker input',
    "#datepicker-trigger",
    'ytcp-text-dropdown-trigger[id="datepicker-trigger"]',
    "#date-select input",
)

TIME_INPUT_SELECTORS = (
    "#time-of-day-trigger input",
    'ytcp-time-of-day-picker input',
    "#time-of-day-trigger",
    'ytcp-text-dropdown-trigger[id="time-of-day-trigger"]',
    'input[aria-label*="Time" i]',
)

SAVE_SCHEDULE_BUTTON_SELECTORS = (
    "#done-button",
    'ytcp-button[id="done-button"]',
    'ytcp-button:has-text("SCHEDULE")',
    'ytcp-button:has-text("Schedule")',
    'ytcp-button:has-text("SAVE")',
)

# ─── Verification & Result ───────────────────────────────────────────────────
VERIFICATION_MODAL_SELECTORS = (
    "ytcp-uploads-dialog",
    "ytcp-video-share-dialog",
    "ytcp-post-share-dialog",
)

VIDEO_URL_SELECTORS = (
    "a.ytcp-video-info",
    'a[href*="youtu.be"]',
    'a[href*="youtube.com/watch"]',
    "#share-url",
)
