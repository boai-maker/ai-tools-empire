#!/bin/bash
cd /Users/kennethbonnet/ai-tools-empire
exec /Users/kennethbonnet/ai-tools-empire/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
