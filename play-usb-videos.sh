#!/bin/bash
# Wait for desktop to be ready
sleep 5

VIDEO="/home/telescope/Videos for Telescope/telescope_moon.mp4"

while true; do
    cvlc --fullscreen --loop --no-osd --no-video-title-show          --no-mouse-events --mouse-hide-timeout=0          "$VIDEO" 2>/dev/null
    sleep 1
done
