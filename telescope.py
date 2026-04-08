#!/usr/bin/env python3
"""
Telescope Moon Viewer
Smoothly zooms and pans across Artemis mission moon photographs,
simulating looking through a telescope scanning the lunar surface.
Cycles through all images with smooth crossfade transitions.
"""

import pygame
import random
import glob
import os
import sys

# Configuration
APP_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_GLOB = os.path.join(APP_DIR, '*.jpg')

# Zoom range
MIN_ZOOM = 1.2
MAX_ZOOM = 4.0

# Timing
TRANSITION_SPEED = 0.002    # Pan/zoom speed (lower = slower)
LINGER_MIN = 3.0            # Seconds to pause at a spot
LINGER_MAX = 8.0
MOVES_PER_IMAGE = 3         # Zoom/pan moves before switching image
CROSSFADE_DURATION = 2.0    # Seconds for crossfade between images
FPS = 30


def ease_in_out(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def pick_target(img_w, img_h, screen_w, screen_h, current_zoom=None):
    if current_zoom is not None:
        min_delta = (MAX_ZOOM - MIN_ZOOM) * 0.25
        for _ in range(20):
            zoom = random.uniform(MIN_ZOOM, MAX_ZOOM)
            if abs(zoom - current_zoom) >= min_delta:
                break
    else:
        zoom = random.uniform(MIN_ZOOM, MAX_ZOOM)

    view_w = screen_w / zoom
    view_h = screen_h / zoom
    margin_x = view_w / 2
    margin_y = view_h / 2
    cx = random.uniform(margin_x, img_w - margin_x)
    cy = random.uniform(margin_y, img_h - margin_y)
    return cx, cy, zoom


def get_view_surface(image, cx, cy, zoom, screen_w, screen_h):
    img_w, img_h = image.get_size()
    view_w = screen_w / zoom
    view_h = screen_h / zoom
    src_x = int(cx - view_w / 2)
    src_y = int(cy - view_h / 2)
    src_w = int(view_w)
    src_h = int(view_h)
    src_x = max(0, min(src_x, img_w - src_w))
    src_y = max(0, min(src_y, img_h - src_h))
    src_rect = pygame.Rect(src_x, src_y, src_w, src_h)
    sub = image.subsurface(src_rect)
    return pygame.transform.smoothscale(sub, (screen_w, screen_h))


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

    clock = pygame.time.Clock()

    # Load first image
    random.shuffle(image_paths)
    img_index = 0
    current_image = pygame.image.load(image_paths[img_index]).convert()
    next_image = None
    img_w, img_h = current_image.get_size()
    print(f'Loaded: {os.path.basename(image_paths[img_index])} ({img_w}x{img_h})')

    # State
    start_cx, start_cy, start_zoom = img_w / 2, img_h / 2, MIN_ZOOM
    current_cx, current_cy, current_zoom = start_cx, start_cy, start_zoom
    target_cx, target_cy, target_zoom = pick_target(img_w, img_h, screen_w, screen_h)
    progress = 0.0
    lingering = False
    linger_timer = 0.0
    move_count = 0

    # Crossfade state
    crossfading = False
    crossfade_progress = 0.0
    crossfade_surface = None

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False

        # Crossfade logic
        if crossfading:
            crossfade_progress += dt / CROSSFADE_DURATION
            if crossfade_progress >= 1.0:
                crossfading = False
                crossfade_progress = 0.0
                current_image = next_image
                next_image = None
                img_w, img_h = current_image.get_size()
                # Reset navigation for new image
                current_cx, current_cy = img_w / 2, img_h / 2
                current_zoom = MIN_ZOOM
                start_cx, start_cy, start_zoom = current_cx, current_cy, current_zoom
                target_cx, target_cy, target_zoom = pick_target(img_w, img_h, screen_w, screen_h)
                progress = 0.0
                lingering = False
                move_count = 0

            # Render crossfade
            t = ease_in_out(crossfade_progress)
            old_surf = get_view_surface(current_image, current_cx, current_cy, current_zoom, screen_w, screen_h)

            # Start new image zoomed out at center
            ni_w, ni_h = next_image.get_size()
            new_surf = get_view_surface(next_image, ni_w / 2, ni_h / 2, MIN_ZOOM, screen_w, screen_h)

            old_surf.set_alpha(int(255 * (1.0 - t)))
            screen.fill((0, 0, 0))
            screen.blit(old_surf, (0, 0))
            new_surf.set_alpha(int(255 * t))
            screen.blit(new_surf, (0, 0))
            pygame.display.flip()
            continue

        # Pan/zoom logic
        if lingering:
            linger_timer -= dt
            if linger_timer <= 0:
                lingering = False
                move_count += 1

                # Time to switch images?
                if move_count >= MOVES_PER_IMAGE:
                    img_index = (img_index + 1) % len(image_paths)
                    print(f'Crossfading to: {os.path.basename(image_paths[img_index])}')
                    next_image = pygame.image.load(image_paths[img_index]).convert()
                    crossfading = True
                    crossfade_progress = 0.0
                    # Reshuffle when we've gone through all
                    if img_index == 0:
                        random.shuffle(image_paths)
                    continue

                target_cx, target_cy, target_zoom = pick_target(
                    img_w, img_h, screen_w, screen_h, current_zoom
                )
                start_cx, start_cy, start_zoom = current_cx, current_cy, current_zoom
                progress = 0.0
        else:
            zoom_dist = abs(target_zoom - start_zoom) / (MAX_ZOOM - MIN_ZOOM)
            speed = TRANSITION_SPEED * (0.6 + 0.8 * zoom_dist)
            progress += speed

            if progress >= 1.0:
                progress = 1.0
                current_cx, current_cy, current_zoom = target_cx, target_cy, target_zoom
                start_cx, start_cy, start_zoom = current_cx, current_cy, current_zoom
                lingering = True
                linger_timer = random.uniform(LINGER_MIN, LINGER_MAX)

        # Interpolate
        t = ease_in_out(progress)
        draw_cx = start_cx + (target_cx - start_cx) * t
        draw_cy = start_cy + (target_cy - start_cy) * t
        draw_zoom = start_zoom + (target_zoom - start_zoom) * t

        # Render
        surf = get_view_surface(current_image, draw_cx, draw_cy, draw_zoom, screen_w, screen_h)
        screen.blit(surf, (0, 0))
        pygame.display.flip()

    pygame.quit()


if __name__ == '__main__':
    main()
