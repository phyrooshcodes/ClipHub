"""DOM selectors and locator strategies for YouTube Studio automation.

# Verified: 2026-07-20 against YouTube Studio 
"""

from __future__ import annotations

# ─── Navigation & Upload Initiation ──────────────────────────────────────────
CREATE_BUTTON_SELECTORS = (
    'button[aria-label="Create"]',
    'button.ytcpButtonShapeImplHost[aria-label="Create"]',
    'ytcp-button.ytcpAppHeaderCreateIcon button',
    'ytcp-button.ytcpAppHeaderCreateIcon',
    'button:has-text("Create")',
    "#create-icon",
    'ytcp-icon-button[id="create-icon"]',
    'ytcp-button:has-text("CREATE")',
    'ytcp-button:has-text("Create")',
    '#create-button',
    '[aria-label="Create"]',
    'ytcp-button:has(#create-icon)',
)

UPLOAD_ITEM_SELECTORS = (
    'tp-yt-paper-item:has-text("Upload videos")',
    'tp-yt-paper-item[test-id="upload"]',
    '[test-id="upload"]',
    'paper-item:has-text("Upload videos")',
    'ytcp-text-menu-item:has-text("Upload videos")',
    'ytcp-text-menu-item:has-text("Upload video")',
    '[aria-label="Upload videos"]',
    '#text-item-0',
    'tp-yt-paper-item:has-text("Upload")',
    'paper-item:has-text("Upload")',
)

DIRECT_UPLOAD_BUTTON_SELECTORS = (
    'button[aria-label="Upload videos"]',
    'button.ytcpButtonShapeImplHost[aria-label="Upload videos"]',
    'ytcp-upload-video-button button',
    'ytcp-upload-video-button',
    'ytcp-button#upload-button button',
    'ytcp-button#upload-button',
    'button:has-text("Upload videos")',
    'button:has-text("Upload")',
    "#upload-icon",
    'ytcp-icon-button[aria-label="Upload videos"]',
    'ytcp-button:has-text("Upload videos")',
    '#upload-button',
    'ytcp-icon-button[id="upload-icon"]',
    '#upload-icon-button',
)

FILE_INPUT_SELECTORS = (
    'input[type="file"][name="Filedata"]',
    'ytcp-uploads-dialog input[type="file"]',
    '#select-files-button input[type="file"]',
    'input[type="file"][accept*="video"]',
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
    'button:has-text("Schedule")',
    'button:has-text("SCHEDULE")',
    'button:has-text("Save")',
    'button:has-text("SAVE")',
    'button[aria-label="Schedule"]',
    'button[aria-label="Save"]',
    'ytcp-button#done-button button',
    '#done-button button',
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
    'a[href*="youtube.com/shorts"]',
    'a[href*="youtu.be"]',
    'a[href*="youtube.com/watch"]',
    "a.ytcp-video-info",
    "#share-url",
)
