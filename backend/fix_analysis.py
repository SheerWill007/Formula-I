#!/usr/bin/env python3
"""Remove duplicate endpoints from analysis.py"""

file_path = "src/backend/api/v1/analysis.py"

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Keep only first 2886 lines (before the duplicate additions)
with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines[:2886])

print(f"Fixed {file_path} - removed {len(lines) - 2886} duplicate lines")
