#!/bin/bash
set -euo pipefail
export PATH="/usr/local/lib/hermes-agent/venv/bin:$PATH:/usr/local/bin"

OUTPUT_DIR="/root/.hermes/wickedyoda-bot/static/images/logos"
DATE=$(date +%Y%m%d_%H%M)

mkdir -p "$OUTPUT_DIR"

echo "=== WickedYoda Bot Logo Generation ($DATE) ==="

# Prompt 1: Cyberpunk server room Yoda portrait
echo "Generating logo 1/3: cyberpunk server room..."
image_generate \
  "A photorealistic digital portrait of WickedYoda, a wise green-skinned humanoid with pointed ears, wearing round wire-rimmed glasses and a long white beard. He wears a red baseball cap and an olive green button-down work shirt. Standing confidently in a cyberpunk data center server room with neon cyan and purple LED strips on black server racks. Warm golden hour lighting on the character's face, dramatic rim light. Clean composition, no text, no watermarks. Style: stylized realism, cinematic lighting, shallow depth of field." \
  --aspect_ratio square \
  --output "$OUTPUT_DIR/wickedyoda-logo-cyberpunk.png" 2>/dev/null

# Prompt 2: Modern tech workspace
echo "Generating logo 2/3: tech workspace..."
image_generate \
  "A photorealistic digital portrait of WickedYoda, a friendly elderly green-skinned humanoid with pointed ears and long white beard, wearing round glasses. He is seated at a modern wooden desk in a tech workspace. Multiple computer monitors display network graphs with pink blue and green lines. A white network switch with blue Ethernet cables sits on the desk. Warm natural lighting from a window. Clean composition, no text, no watermarks. Style: photorealistic with cinematic lighting." \
  --aspect_ratio square \
  --output "$OUTPUT_DIR/wickedyoda-logo-tech-desk.png" 2>/dev/null

# Prompt 3: Rooftop cityscape Yoda
echo "Generating logo 3/3: rooftop cityscape..."
image_generate \
  "A photorealistic digital portrait of WickedYoda, a wise green-skinned humanoid with pointed ears, wearing round wire-rimmed glasses and long white beard. He wears a red baseball cap and olive green button-down shirt. Standing on a concrete rooftop ledge at golden hour sunset. Behind him a futuristic cyberpunk cityscape with telecommunications towers, neon signs, and long-exposure traffic light trails. Warm glow on his face, cool city lights in background. Clean composition, no text, no watermarks. Style: stylized realism, cinematic lighting." \
  --aspect_ratio square \
  --output "$OUTPUT_DIR/wickedyoda-logo-rooftop.png" 2>/dev/null

echo "=== Generation complete ==="
ls -la "$OUTPUT_DIR/wickedyoda-logo-*.png" 2>&1
