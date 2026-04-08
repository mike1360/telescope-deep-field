#!/usr/bin/env python3
"""
Telescope Moon Viewer
Continuously zooms and pans across Artemis mission moon photographs.
"""

import pygame
import random
import glob
import os
import sys
import threading

APP_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_GLOB = os.path.join(APP_DIR, '*.jpg')

MIN_ZOOM = 1.0
MAX_ZOOM = 5.0
BASE_DURATION = 12.0
MOVES_PER_IMAGE = 2
CROSSFADE_DURATION = 2.5
FPS = 30
GRID_SIZE = 16


def ease_in_out(t):
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 16 * t * t * t * t * t
    return 1 - pow(-2 * t + 2, 5) / 2


def build_interest_map(image):
    img_w, img_h = image.get_size()
    cell_w = img_w // GRID_SIZE
    cell_h = img_h // GRID_SIZE
    scores = []
    for gy in range(GRID_SIZE):
        for gx in range(GRID_SIZE):
            x = gx * cell_w
            y = gy * cell_h
            samples = []
            step = max(1, cell_w // 8)
            for sy in range(y, min(y + cell_h, img_h), step):
                for sx in range(x, min(x + cell_w, img_w), step):
                    r, g, b, *_ = image.get_at((sx, sy))
                    samples.append(r * 0.299 + g * 0.587 + b * 0.114)
            if not samples:
                scores.append((gx, gy, 0))
                continue
            mean = sum(samples) / len(samples)
            variance = sum((s - mean) ** 2 for s in samples) / len(samples)
            brightness = mean / 255.0
            score = variance * (0.3 + brightness)
            scores.append((gx, gy, score))
    scores.sort(key=lambda s: s[2], reverse=True)
    top_count = max(3, len(scores) // 3)
    return scores[:top_count], cell_w, cell_h


def pick_zoom_in(img_w, img_h, screen_w, screen_h, interest_map, cell_w, cell_h):
    zoom = random.uniform(2.5, MAX_ZOOM)
    view_w = screen_w / zoom
    view_h = screen_h / zoom
    gx, gy, _ = random.choice(interest_map)
    cx = (gx + 0.5) * cell_w + random.uniform(-cell_w * 0.3, cell_w * 0.3)
    cy = (gy + 0.5) * cell_h + random.uniform(-cell_h * 0.3, cell_h * 0.3)
    margin_x = view_w / 2
    margin_y = view_h / 2
    cx = max(margin_x, min(cx, img_w - margin_x))
    cy = max(margin_y, min(cy, img_h - margin_y))
    return cx, cy, zoom


def render_view(image, cx, cy, zoom, screen_w, screen_h, dest_surface):
    img_w, img_h = image.get_size()
    view_w = screen_w / zoom
    view_h = screen_h / zoom
    src_x = int(cx - view_w / 2)
    src_y = int(cy - view_h / 2)
    src_w = max(1, int(view_w))
    src_h = max(1, int(view_h))
    src_x = max(0, min(src_x, img_w - src_w))
    src_y = max(0, min(src_y, img_h - src_h))
    src_rect = pygame.Rect(src_x, src_y, src_w, src_h)
    sub = image.subsurface(src_rect)
    pygame.transform.smoothscale(sub, (screen_w, screen_h), dest_surface)


# Background image loader
_preloaded = {}
_preload_lock = threading.Lock()

def preload_image(path):
    # Load raw bytes in thread (convert must happen on main thread)
    with open(path, 'rb') as f:
        data = f.read()
    with _preload_lock:
        _preloaded[path] = data

def get_preloaded(path):
    with _preload_lock:
        data = _preloaded.pop(path, None)
    if data:
        import io
        return pygame.image.load(io.BytesIO(data)).convert()
    return pygame.image.load(path).convert()


def main():
    image_paths = sorted(glob.glob(IMAGE_GLOB))
    if not image_paths:
        print(f'No .jpg images found in {APP_DIR}')
        sys.exit(1)
    print(f'Found {len(image_paths)} images')

    os.environ['SDL_VIDEO_CURSOR_HIDDEN'] = '1'
    pygame.init()

    info = pygame.display.Info()
    screen_w, screen_h = info.current_w, info.current_h
    screen = pygame.display.set_mode((screen_w, screen_h), pygame.FULLSCREEN | pygame.NOFRAME)
    pygame.display.set_caption('')
    pygame.mouse.set_visible(False)

    # Offscreen buffer — we only ever blit this complete frame to screen
    buffer = pygame.Surface((screen_w, screen_h))
    fade_buffer = pygame.Surface((screen_w, screen_h))

    clock = pygame.time.Clock()

    random.shuffle(image_paths)
    img_index = 0
    current_image = pygame.image.load(image_paths[img_index]).convert()
    img_w, img_h = current_image.get_size()
    print(f'Loaded: {os.path.basename(image_paths[img_index])} ({img_w}x{img_h})')

    interest_map, cell_w, cell_h = build_interest_map(current_image)

    # Preload next
    next_idx = (img_index + 1) % len(image_paths)
    threading.Thread(target=preload_image, args=(image_paths[next_idx],), daemon=True).start()

    # State
    start_cx, start_cy, start_zoom = img_w / 2, img_h / 2, MIN_ZOOM
    current_cx, current_cy, current_zoom = start_cx, start_cy, start_zoom
    target_cx, target_cy, target_zoom = pick_zoom_in(img_w, img_h, screen_w, screen_h, interest_map, cell_w, cell_h)

    move_count = 0
    move_duration = BASE_DURATION + random.uniform(-2.0, 2.0)
    elapsed = 0.0

    crossfading = False
    crossfade_progress = 0.0
    next_image = None

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False

        if crossfading:
            crossfade_progress += dt / CROSSFADE_DURATION
            if crossfade_progress >= 1.0:
                crossfading = False
                current_image = next_image
                next_image = None
                img_w, img_h = current_image.get_size()
                interest_map, cell_w, cell_h = build_interest_map(current_image)
                current_cx, current_cy, current_zoom = img_w / 2, img_h / 2, MIN_ZOOM
                start_cx, start_cy, start_zoom = current_cx, current_cy, current_zoom
                target_cx, target_cy, target_zoom = pick_zoom_in(img_w, img_h, screen_w, screen_h, interest_map, cell_w, cell_h)
                elapsed = 0.0
                move_duration = BASE_DURATION + random.uniform(-2.0, 2.0)
                move_count = 0
                next_idx = (img_index + 1) % len(image_paths)
                threading.Thread(target=preload_image, args=(image_paths[next_idx],), daemon=True).start()
                # Render current position to buffer
                render_view(current_image, current_cx, current_cy, current_zoom, screen_w, screen_h, buffer)
            else:
                t = ease_in_out(crossfade_progress)
                # Old image into buffer at full opacity
                render_view(current_image, current_cx, current_cy, current_zoom, screen_w, screen_h, buffer)
                # New image into fade_buffer, then alpha-blend onto buffer
                ni_w, ni_h = next_image.get_size()
                render_view(next_image, ni_w / 2, ni_h / 2, MIN_ZOOM, screen_w, screen_h, fade_buffer)
                fade_buffer.set_alpha(int(255 * t))
                buffer.blit(fade_buffer, (0, 0))
        else:
            elapsed += dt
            progress = min(1.0, elapsed / move_duration)

            if progress >= 1.0:
                current_cx, current_cy, current_zoom = target_cx, target_cy, target_zoom
                start_cx, start_cy, start_zoom = current_cx, current_cy, current_zoom
                move_count += 1

                if move_count >= MOVES_PER_IMAGE and move_count % 2 == 0:
                    img_index = (img_index + 1) % len(image_paths)
                    if img_index == 0:
                        random.shuffle(image_paths)
                    print(f'Crossfading to: {os.path.basename(image_paths[img_index])}')
                    next_image = get_preloaded(image_paths[img_index])
                    crossfading = True
                    crossfade_progress = 0.0
                    render_view(current_image, current_cx, current_cy, current_zoom, screen_w, screen_h, buffer)
                    screen.blit(buffer, (0, 0))
                    pygame.display.update()
                    continue

                if move_count % 2 == 0:
                    target_cx, target_cy, target_zoom = pick_zoom_in(img_w, img_h, screen_w, screen_h, interest_map, cell_w, cell_h)
                else:
                    target_cx, target_cy, target_zoom = img_w / 2, img_h / 2, MIN_ZOOM

                move_duration = BASE_DURATION + random.uniform(-2.0, 2.0)
                elapsed = 0.0
                progress = 0.0

            t = ease_in_out(progress)
            draw_cx = start_cx + (target_cx - start_cx) * t
            draw_cy = start_cy + (target_cy - start_cy) * t
            draw_zoom = start_zoom + (target_zoom - start_zoom) * t

            render_view(current_image, draw_cx, draw_cy, draw_zoom, screen_w, screen_h, buffer)

        # Always blit complete buffer to screen
        screen.blit(buffer, (0, 0))
        pygame.display.update()

    pygame.quit()


if __name__ == '__main__':
    main()
