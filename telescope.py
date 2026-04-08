#!/usr/bin/env python3
"""
Telescope Deep Field Viewer
Smoothly zooms and pans across the Hubble eXtreme Deep Field image,
simulating looking through a telescope and adjusting magnification.
"""

import pygame
import random
import math
import os
import sys
import urllib.request

# Configuration
IMAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hubble_xdf.png')
IMAGE_URL = 'https://svs.gsfc.nasa.gov/vis/a030000/a030900/a030946/hudf-hst-6200x6200.png'

# Zoom range (1.0 = full image fits screen, higher = more zoomed in)
MIN_ZOOM = 1.5
MAX_ZOOM = 6.0

# Speed controls - lower = slower/smoother
TRANSITION_SPEED = 0.003   # How fast we move between targets
LINGER_MIN = 3.0           # Minimum seconds to linger at a target
LINGER_MAX = 10.0          # Maximum seconds to linger at a target
FPS = 30


def ease_in_out(t):
    """Smooth ease-in-out curve (hermite interpolation)."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def download_image():
    """Download the Hubble XDF image if not present."""
    if os.path.exists(IMAGE_PATH):
        return
    print(f'Downloading Hubble XDF image to {IMAGE_PATH}...')
    urllib.request.urlretrieve(IMAGE_URL, IMAGE_PATH)
    print('Download complete.')


def pick_target(img_w, img_h, screen_w, screen_h, current_zoom=None):
    """Pick a new random zoom level and pan position."""
    # Pick zoom, biased away from current to ensure visible movement
    if current_zoom is not None:
        # Move at least 30% of the range away from current
        min_delta = (MAX_ZOOM - MIN_ZOOM) * 0.3
        for _ in range(20):
            zoom = random.uniform(MIN_ZOOM, MAX_ZOOM)
            if abs(zoom - current_zoom) >= min_delta:
                break
    else:
        zoom = random.uniform(MIN_ZOOM, MAX_ZOOM)

    # Calculate the visible area at this zoom level
    view_w = screen_w / zoom
    view_h = screen_h / zoom

    # Pick a center point that keeps the view within the image
    margin_x = view_w / 2
    margin_y = view_h / 2
    cx = random.uniform(margin_x, img_w - margin_x)
    cy = random.uniform(margin_y, img_h - margin_y)

    return cx, cy, zoom


def main():
    download_image()

    # Hide cursor and initialize pygame
    os.environ['SDL_VIDEO_CURSOR_HIDDEN'] = '1'
    pygame.init()

    # Get display info for fullscreen
    info = pygame.display.Info()
    screen_w, screen_h = info.current_w, info.current_h
    screen = pygame.display.set_mode((screen_w, screen_h), pygame.FULLSCREEN | pygame.NOFRAME)
    pygame.display.set_caption('')
    pygame.mouse.set_visible(False)

    # Load the full-resolution image
    print(f'Loading image ({IMAGE_PATH})...')
    full_image = pygame.image.load(IMAGE_PATH).convert()
    img_w, img_h = full_image.get_size()
    print(f'Image loaded: {img_w}x{img_h}, Screen: {screen_w}x{screen_h}')

    clock = pygame.time.Clock()

    # Initial state
    current_cx, current_cy, current_zoom = img_w / 2, img_h / 2, MIN_ZOOM
    target_cx, target_cy, target_zoom = pick_target(img_w, img_h, screen_w, screen_h)

    progress = 0.0       # 0 to 1: how far along the transition
    lingering = False
    linger_timer = 0.0

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False

        if lingering:
            # Wait at current position
            linger_timer -= dt
            if linger_timer <= 0:
                lingering = False
                # Pick new target
                target_cx, target_cy, target_zoom = pick_target(
                    img_w, img_h, screen_w, screen_h, current_zoom
                )
                progress = 0.0
        else:
            # Advance transition
            # Vary speed slightly based on zoom distance for organic feel
            zoom_dist = abs(target_zoom - current_zoom)
            speed_mod = TRANSITION_SPEED * (0.7 + 0.6 * (zoom_dist / (MAX_ZOOM - MIN_ZOOM)))
            progress += speed_mod

            if progress >= 1.0:
                progress = 1.0
                # Arrived at target — start lingering
                lingering = True
                linger_timer = random.uniform(LINGER_MIN, LINGER_MAX)
                current_cx, current_cy, current_zoom = target_cx, target_cy, target_zoom

        # Interpolate with easing
        t = ease_in_out(progress)
        if not lingering:
            start_cx = current_cx
            start_cy = current_cy
            start_zoom = current_zoom
            draw_cx = start_cx + (target_cx - start_cx) * t
            draw_cy = start_cy + (target_cy - start_cy) * t
            draw_zoom = start_zoom + (target_zoom - start_zoom) * t
        else:
            draw_cx, draw_cy, draw_zoom = current_cx, current_cy, current_zoom

        # Calculate source rect (the area of the big image we want to show)
        view_w = screen_w / draw_zoom
        view_h = screen_h / draw_zoom
        src_x = int(draw_cx - view_w / 2)
        src_y = int(draw_cy - view_h / 2)
        src_w = int(view_w)
        src_h = int(view_h)

        # Clamp to image bounds
        src_x = max(0, min(src_x, img_w - src_w))
        src_y = max(0, min(src_y, img_h - src_h))

        # Extract and scale to screen
        src_rect = pygame.Rect(src_x, src_y, src_w, src_h)
        sub = full_image.subsurface(src_rect)
        scaled = pygame.transform.smoothscale(sub, (screen_w, screen_h))
        screen.blit(scaled, (0, 0))
        pygame.display.flip()

    pygame.quit()


if __name__ == '__main__':
    main()
