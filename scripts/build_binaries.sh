#!/usr/bin/env bash
set -euo pipefail

echo "=========================================================="
echo "🔨 COMPILATION DES 3 BINAIRES SLACK2TCHAP (PYINSTALLER)"
echo "=========================================================="

echo "📦 1/3. Compilation de slack2tchap-core..."
uv run pyinstaller --clean --noconfirm --onefile \
    --name slack2tchap-core \
    slack2tchap-core/src/slack2tchap_core/cli.py

echo "⚡ 2/3. Compilation de slack2tchap-stateless..."
uv run pyinstaller --clean --noconfirm --onefile \
    --name slack2tchap-stateless \
    slack2tchap-stateless/src/slack2tchap_stateless/main.py

echo "🗄️  3/3. Compilation de slack2tchap (stateful)..."
uv run pyinstaller --clean --noconfirm --onefile \
    --name slack2tchap \
    slack2tchap/src/slack2tchap/main.py

echo "=========================================================="
echo "✅ SUCCÈS : Les 3 binaires sont disponibles dans dist/ :"
ls -lh dist/
echo "=========================================================="
