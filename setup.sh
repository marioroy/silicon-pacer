#!/bin/bash
# Setup script for SiliconPacer

# Exit immediately if a command exits with a non-zero status
set -e

# Ensure the core python script is executable
if [ -f "silicon_pacer.py" ]; then
    echo "⚙️ Setting executable permissions on silicon_pacer.py..."
    chmod +x silicon_pacer.py
else
    echo "❌ Error: silicon_pacer.py not found in the current directory!"
    exit 1
fi

echo "✅ Setup complete! Zero extra configurations or packages required."
echo "--------------------------------------------------------"
echo "To start pacing your llama-server instance, execute:"
echo "  ./silicon_pacer.py"
echo "--------------------------------------------------------"

