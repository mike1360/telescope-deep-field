#!/usr/bin/env python3
"""
Render telescope moon viewer as a video file.
Outputs frames to ffmpeg via pipe for smooth, glitch-free playback.
"""

import subprocess
import random
import math
import glob
import os
import sys
from PIL import Image
import numpy as np

# Output
OUTPUT_FILE = "/Users/mikemurray/Desktop/telescope_moon.mp4"
SCREEN_W, SCREEN_H = 480, 480
FPS = 30

# Source images
IMAGE_DIR = "/Users/mikemurray/Desktop/Moon Images"

# Zoom range
MIN_ZOOM = 1.0
MAX_ZOOM = 5.0

# Timing (in seconds)
MOVE_DURATION_BASE = 12.0
MOVES_PER_IMAGE = 2  # zoom in, zoom out, then next image
CROSSFADE_DURATION = 2.5

# Interest map
GRID_SIZE = 16


def ease_in_out(t):
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 16 * t * t * t * t * t
    return 1 - pow(-2 * t + 2, 5) / 2


def build_interest_map(img_array):
    h, w = img_array.shape[:2]
    cell_w = w // GRID_SIZE
    cell_h = h // GRID_SIZE
    scores = []

    for gy in range(GRID_SIZE):
        for gx in range(GRID_SIZE):
            y0 = gy * cell_h
            x0 = gx * cell_w
            cell = img_array[y0:y0+cell_h, x0:x0+cell_w]
            # Luminance
            lum = cell[:,:,0] * 0.299 + cell[:,:,1] * 0.587 + cell[:,:,2] * 0.114
            variance = np.var(lum)
            brightness = np.mean(lum) / 255.0
            score = variance * (0.3 + brightness)
            scores.append((gx, gy, score))

    scores.sort(key=lambda s: s[2], reverse=True)
    top_count = max(3, len(scores) // 3)
    return scores[:top_count], cell_w, cell_h


def pick_zoom_in(img_w, img_h, interest_map, cell_w, cell_h):
    zoom = random.uniform(2.5, MAX_ZOOM)
    view_w = SCREEN_W / zoom
    view_h = SCREEN_H / zoom
    gx, gy, _ = random.choice(interest_map)
    cx = (gx + 0.5) * cell_w + random.uniform(-cell_w * 0.3, cell_w * 0.3)
    cy = (gy + 0.5) * cell_h + random.uniform(-cell_h * 0.3, cell_h * 0.3)
    margin_x = view_w / 2
    margin_y = view_h / 2
    cx = max(margin_x, min(cx, img_w - margin_x))
    cy = max(margin_y, min(cy, img_h - margin_y))
    return cx, cy, zoom


def render_frame(img, cx, cy, zoom):
    """Extract and scale a view from the image."""
    img_w, img_h = img.size
    view_w = SCREEN_W / zoom
    view_h = SCREEN_H / zoom
    x0 = cx - view_w / 2
    y0 = cy - view_h / 2
    x0 = max(0, min(x0, img_w - view_w))
    y0 = max(0, min(y0, img_h - view_h))
    box = (int(x0), int(y0), int(x0 + view_w), int(y0 + view_h))
    cropped = img.crop(box)
    return cropped.resize((SCREEN_W, SCREEN_H), Image.LANCZOS)


def blend_frames(frame_a, frame_b, t):
    """Crossfade between two PIL images."""
    return Image.blend(frame_a, frame_b, t)


def main():
    image_paths = sorted(glob.glob(os.path.join(IMAGE_DIR, "*.jpg")))
    if not image_paths:
        print("No images found!")
        sys.exit(1)
    print(f"Found {len(image_paths)} images")

    # Load all images (they're only ~2MB each)
    images = []
    interest_maps = []
    for p in image_paths:
        img = Image.open(p).convert("RGB")
        images.append(img)
        arr = np.array(img)
        imap, cw, ch = build_interest_map(arr)
        interest_maps.append((imap, cw, ch))
        print(f"  Loaded {os.path.basename(p)} ({img.size[0]}x{img.size[1]}), {len(imap)} hot regions")

    random.shuffle(list(range(len(images))))
    order = list(range(len(images)))
    random.shuffle(order)

    # Calculate total frames: each image gets MOVES_PER_IMAGE moves + crossfade
    # Go through all images twice for a nice long loop
    num_cycles = 2
    sequence = []
    for _ in range(num_cycles):
        random.shuffle(order)
        sequence.extend(order)

    total_moves = len(sequence) * MOVES_PER_IMAGE
    move_seconds = MOVE_DURATION_BASE
    crossfade_seconds = CROSSFADE_DURATION
    total_seconds = len(sequence) * (MOVES_PER_IMAGE * move_seconds + crossfade_seconds)
    total_frames = int(total_seconds * FPS)
    print(f"Rendering {total_seconds:.0f}s ({total_frames} frames) at {FPS}fps, {SCREEN_W}x{SCREEN_H}")

    # Start ffmpeg
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{SCREEN_W}x{SCREEN_H}",
        "-pix_fmt", "rgb24",
        "-r", str(FPS),
        "-i", "-",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        OUTPUT_FILE
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    frame_num = 0

    for seq_idx, img_idx in enumerate(sequence):
        img = images[img_idx]
        img_w, img_h = img.size
        imap, cw, ch = interest_maps[img_idx]
        img_name = os.path.basename(image_paths[img_idx])

        # If not first image, crossfade from previous
        if seq_idx > 0:
            prev_img = images[sequence[seq_idx - 1]]
            prev_w, prev_h = prev_img.size
            # Previous image is zoomed out at end, new image starts zoomed out
            crossfade_frames = int(CROSSFADE_DURATION * FPS)
            for cf in range(crossfade_frames):
                t = ease_in_out(cf / crossfade_frames)
                old_frame = render_frame(prev_img, prev_w / 2, prev_h / 2, MIN_ZOOM)
                new_frame = render_frame(img, img_w / 2, img_h / 2, MIN_ZOOM)
                blended = blend_frames(old_frame, new_frame, t)
                proc.stdin.write(blended.tobytes())
                frame_num += 1

        # Zoom in / zoom out moves
        cx, cy, zoom = img_w / 2, img_h / 2, MIN_ZOOM

        for move in range(MOVES_PER_IMAGE):
            start_cx, start_cy, start_zoom = cx, cy, zoom

            if move % 2 == 0:
                # Zoom in to interesting spot
                target_cx, target_cy, target_zoom = pick_zoom_in(img_w, img_h, imap, cw, ch)
            else:
                # Zoom out to full
                target_cx, target_cy, target_zoom = img_w / 2, img_h / 2, MIN_ZOOM

            duration = MOVE_DURATION_BASE + random.uniform(-2.0, 2.0)
            num_frames = int(duration * FPS)

            for f in range(num_frames):
                t = ease_in_out(f / num_frames)
                draw_cx = start_cx + (target_cx - start_cx) * t
                draw_cy = start_cy + (target_cy - start_cy) * t
                draw_zoom = start_zoom + (target_zoom - start_zoom) * t

                frame = render_frame(img, draw_cx, draw_cy, draw_zoom)
                proc.stdin.write(frame.tobytes())
                frame_num += 1

            cx, cy, zoom = target_cx, target_cy, target_zoom

        # Progress
        pct = (seq_idx + 1) / len(sequence) * 100
        print(f"  [{pct:5.1f}%] {img_name} done ({frame_num} frames)")

    proc.stdin.close()
    proc.wait()
    print(f"\nDone! {OUTPUT_FILE} ({frame_num} frames, {frame_num/FPS:.0f}s)")


if __name__ == "__main__":
    main()
