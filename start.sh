#!/bin/bash
cd /home/mood-organ/mood-organ || exit 1
timeout 20 git pull origin main || echo "pull failed, running existing version"
exec python3 mood-organ.py
