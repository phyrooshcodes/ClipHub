# Music library

Drop instrumental audio files here (`.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`, or `.ogg`). Obscura rescans this folder every time it makes clips, so no import step is needed.

For self-improvement clips, filename words help the automatic selector. Good examples: `calm-focus`, `soft-ambient`, `warm-piano`, `uplifting-corporate`, `gentle-momentum`. Tracks with words such as `dark`, `mystery`, `drama`, `sad`, `intense`, `horror`, or `phonk` are deliberately excluded by default.

## Optional precise tags

When the library grows, create `music_library.json` here to override a track's automatic tags:

```json
{
  "artist-track.mp3": {
    "moods": ["calm_focus", "warm_reflection"],
    "tags": ["ambient", "gentle", "instrumental"],
    "start_offset_s": 4.0,
    "enabled": true
  }
}
```

Allowed moods are `warm_reflection`, `calm_focus`, and `measured_momentum`. Set `enabled` to `false` to keep a track in the folder but temporarily stop it from being selected.
