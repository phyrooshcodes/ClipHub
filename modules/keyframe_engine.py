"""
CapCut-Grade 60 FPS Keyframe Animation Engine for AI Presenter Avatars.
Provides continuous multi-channel keyframing (Position X/Y, Scale X/Y, Rotation, Opacity)
with true CapCut easing curves (Ease-Out-Back Pop, Cubic-Bezier, Elastic Spring, Continuous Respiration).
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Callable, Dict, Tuple


# ─── 1. CapCut Easing Curve Functions ──────────────────────────────────────────

def ease_linear(t: float) -> float:
    return max(0.0, min(1.0, t))

def ease_in_quad(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t

def ease_out_quad(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * (2.0 - t)

def ease_in_out_quad(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 2.0 * t * t if t < 0.5 else -1.0 + (4.0 - 2.0 * t) * t

def ease_in_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * t

def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t)) - 1.0
    return t * t * t + 1.0

def ease_in_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 4.0 * t * t * t if t < 0.5 else (t - 1.0) * (2.0 * t - 2.0) * (2.0 * t - 2.0) + 1.0

def ease_out_expo(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 if t >= 1.0 else 1.0 - math.pow(2.0, -10.0 * t)

def ease_out_back(t: float, s: float = 1.70158) -> float:
    """
    Signature CapCut Pop-In Overshoot Easing.
    Element zooms/moves past 100% target and gracefully snaps into rest.
    """
    t = max(0.0, min(1.0, t)) - 1.0
    return t * t * ((s + 1.0) * t + s) + 1.0

def ease_in_back(t: float, s: float = 1.70158) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * ((s + 1.0) * t - s)

def ease_spring_bounce(t: float, damping: float = 6.0, freq: float = 14.0) -> float:
    """
    Physical damped harmonic spring oscillator.
    """
    t = max(0.0, min(1.0, t))
    if t >= 1.0:
        return 1.0
    return 1.0 - math.exp(-damping * t) * math.cos(freq * t)


EASING_MAP: Dict[str, Callable[[float], float]] = {
    "linear": ease_linear,
    "ease_in_quad": ease_in_quad,
    "ease_out_quad": ease_out_quad,
    "ease_in_out_quad": ease_in_out_quad,
    "ease_in_cubic": ease_in_cubic,
    "ease_out_cubic": ease_out_cubic,
    "ease_in_out_cubic": ease_in_out_cubic,
    "ease_out_expo": ease_out_expo,
    "ease_out_back": ease_out_back,
    "ease_in_back": ease_in_back,
    "spring": ease_spring_bounce,
    "bounce": ease_spring_bounce,
}


# ─── 2. Keyframe Data Structures ──────────────────────────────────────────────

@dataclass
class KeyframeState:
    x: float             # Horizontal offset in pixels
    y: float             # Vertical offset in pixels
    scale_x: float       # Scale multiplier X
    scale_y: float       # Scale multiplier Y
    rotation: float      # Degrees (positive = clockwise)
    opacity: float       # 0.0 to 1.0

    @property
    def scale(self) -> float:
        return (self.scale_x + self.scale_y) / 2.0


@dataclass
class Keyframe:
    time_s: float
    x: float = 0.0
    y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation: float = 0.0
    opacity: float = 1.0
    easing: str = "ease_out_cubic"


# ─── 3. Keyframe Track & Continuous 60 FPS Evaluator ─────────────────────────

class KeyframeTrack:
    def __init__(
        self,
        keyframes: Optional[List[Keyframe]] = None,
        enable_respiration: bool = True,
        respiration_intensity: float = 1.0
    ):
        self.keyframes = sorted(keyframes or [], key=lambda k: k.time_s)
        self.enable_respiration = enable_respiration
        self.respiration_intensity = respiration_intensity

    def add_keyframe(self, kf: Keyframe):
        self.keyframes.append(kf)
        self.keyframes.sort(key=lambda k: k.time_s)

    def evaluate(self, t: float) -> KeyframeState:
        """
        Evaluates the exact subpixel state at continuous timestamp t (seconds).
        """
        if not self.keyframes:
            return KeyframeState(x=0.0, y=0.0, scale_x=1.0, scale_y=1.0, rotation=0.0, opacity=1.0)

        # Before first keyframe
        if t <= self.keyframes[0].time_s:
            first = self.keyframes[0]
            base_state = KeyframeState(
                x=first.x, y=first.y,
                scale_x=first.scale_x, scale_y=first.scale_y,
                rotation=first.rotation, opacity=first.opacity
            )
            return self._apply_respiration(base_state, t)

        # After last keyframe
        if t >= self.keyframes[-1].time_s:
            last = self.keyframes[-1]
            base_state = KeyframeState(
                x=last.x, y=last.y,
                scale_x=last.scale_x, scale_y=last.scale_y,
                rotation=last.rotation, opacity=last.opacity
            )
            return self._apply_respiration(base_state, t)

        # Find bounding interval [k0, k1]
        k0 = self.keyframes[0]
        k1 = self.keyframes[-1]
        for i in range(len(self.keyframes) - 1):
            if self.keyframes[i].time_s <= t <= self.keyframes[i + 1].time_s:
                k0 = self.keyframes[i]
                k1 = self.keyframes[i + 1]
                break

        interval_dur = k1.time_s - k0.time_s
        if interval_dur <= 1e-6:
            progress = 1.0
        else:
            progress = (t - k0.time_s) / interval_dur

        # Apply easing function
        ease_fn = EASING_MAP.get(k0.easing, ease_out_cubic)
        e = ease_fn(progress)

        # Interpolate all transformation channels
        interp_x = k0.x + (k1.x - k0.x) * e
        interp_y = k0.y + (k1.y - k0.y) * e
        interp_sx = k0.scale_x + (k1.scale_x - k0.scale_x) * e
        interp_sy = k0.scale_y + (k1.scale_y - k0.scale_y) * e
        interp_rot = k0.rotation + (k1.rotation - k0.rotation) * e
        interp_op = max(0.0, min(1.0, k0.opacity + (k1.opacity - k0.opacity) * e))

        base_state = KeyframeState(
            x=interp_x,
            y=interp_y,
            scale_x=interp_sx,
            scale_y=interp_sy,
            rotation=interp_rot,
            opacity=interp_op
        )
        return self._apply_respiration(base_state, t)

    def _apply_respiration(self, state: KeyframeState, t: float) -> KeyframeState:
        """
        Adds 60 FPS organic multi-frequency breathing & subtle speaking bob.
        Eliminates robotic freeze while keeping avatar stable and grounded.
        """
        if not self.enable_respiration or state.opacity < 0.1:
            return state

        intensity = self.respiration_intensity
        # Multi-harmonic Lissajous curves
        bob_x = (5.5 * math.sin(0.85 * t) + 2.8 * math.cos(0.52 * t)) * intensity
        bob_y = (4.5 * math.sin(0.72 * t) + 2.2 * math.sin(1.35 * t + 0.5)) * intensity
        breath_scale = 1.0 + (0.012 * math.sin(0.95 * t)) * intensity
        tilt = (0.55 * math.sin(0.65 * t)) * intensity

        return KeyframeState(
            x=state.x + bob_x,
            y=state.y + bob_y,
            scale_x=state.scale_x * breath_scale,
            scale_y=state.scale_y * breath_scale,
            rotation=state.rotation + tilt,
            opacity=state.opacity
        )


# ─── 4. CapCut Animation Presets ──────────────────────────────────────────────

def build_capcut_intro_track(
    duration: float,
    w_canvas: int = 1080,
    h_canvas: int = 1920,
    w_av: int = 932,
    h_av: int = 1400
) -> KeyframeTrack:
    """
    Preset: CapCut Bouncy Pop-In & Focus (Intro Hook).
    - Frame 0 (0.00s): Visible on-screen for perfect thumbnail representation with punchy entry.
    - 0.00s -> 0.38s: Elastic overshoot bounce (Scale 0.88 -> 1.035 -> 1.00, Y rest settled).
    - 0.38s -> duration - 0.40s: 60 FPS natural speaking presence with organic respiration.
    - duration - 0.40s -> duration: Smooth CapCut Ease-In slide down & exit.
    """
    t_pop_end = min(0.40, duration * 0.25)
    t_exit_start = max(t_pop_end + 0.2, duration - 0.40)
    t_end = duration

    travel_y = 650.0 # Slide down distance on exit

    keyframes = [
        # Frame 0: Energetic entry pose (Slight scale pop & dynamic tilt)
        Keyframe(time_s=0.0, x=0.0, y=35.0, scale_x=0.90, scale_y=0.90, rotation=-1.8, opacity=1.0, easing="ease_out_back"),
        # Overshoot settle
        Keyframe(time_s=t_pop_end, x=0.0, y=0.0, scale_x=1.0, scale_y=1.0, rotation=0.0, opacity=1.0, easing="ease_in_out_quad"),
        # Hold / Presenting body
        Keyframe(time_s=t_exit_start, x=0.0, y=0.0, scale_x=1.0, scale_y=1.0, rotation=0.0, opacity=1.0, easing="ease_in_cubic"),
        # Exit slide down
        Keyframe(time_s=t_end, x=0.0, y=travel_y, scale_x=0.96, scale_y=0.96, rotation=1.2, opacity=0.0, easing="linear"),
    ]
    return KeyframeTrack(keyframes=keyframes, enable_respiration=True, respiration_intensity=1.0)


def build_capcut_outro_track(
    duration: float,
    w_canvas: int = 1080,
    h_canvas: int = 1920,
    w_av: int = 932,
    h_av: int = 1400
) -> KeyframeTrack:
    """
    Preset: CapCut Smooth Slide-Up & Direct Delivery (Closing Explanation).
    - 0.00s -> 0.45s: Smooth slide up from bottom with subtle scale expansion and settle.
    - 0.45s -> duration: Grounded explanatory presence with continuous 60fps micro-motion.
    """
    t_in_end = min(0.48, duration * 0.25)
    travel_y = 550.0

    keyframes = [
        # Start just beneath visible baseline
        Keyframe(time_s=0.0, x=0.0, y=travel_y, scale_x=0.92, scale_y=0.92, rotation=-1.2, opacity=0.0, easing="ease_out_cubic"),
        # Settle gracefully at center
        Keyframe(time_s=t_in_end, x=0.0, y=0.0, scale_x=1.0, scale_y=1.0, rotation=0.0, opacity=1.0, easing="ease_in_out_quad"),
        # Stay solid through final takeaway
        Keyframe(time_s=duration, x=0.0, y=0.0, scale_x=1.0, scale_y=1.0, rotation=0.0, opacity=1.0, easing="linear"),
    ]
    return KeyframeTrack(keyframes=keyframes, enable_respiration=True, respiration_intensity=0.85)
