# Third-party notices

## YouTube Card Reader

- Source: https://github.com/chang416/youtube-card-reader
- Upstream commit at import: 7196505e91765059ba9fcda7c859de89d5a5ce04
- License: MIT. The original copyright and license are retained in [LICENSE](LICENSE).
- AstraTube modifications: Codespaces development setup, development documentation, Traditional Chinese defaults, Vite proxy and safer CLI execution default.
- Source import preserves code and tests, but not the upstream Git commit graph. Upstream README is saved at [docs/UPSTREAM_README.md](docs/UPSTREAM_README.md).
- Five upstream documentation-only media files (PNG/GIF/MP4) are not included; links to upstream public assets remain in the archived README.

## Other projects

Video Digest AI (https://github.com/ocean-8848/video-digest-ai) and VideoToNo (https://github.com/like-attract/video-to-note) were considered during planning. **No source code from those projects has been incorporated yet.** If that changes, update this notice and preserve their relevant license notices.

## Local speech-to-text

AstraTube can download these on request; the model is not included in the program:

- SenseVoiceSmall (https://github.com/FunAudioLLM/SenseVoice), by FunASR / Alibaba Group, converted to ONNX by the sherpa-onnx project. Model weights are under the FunASR Model License 1.1 (https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE).
- Silero VAD (https://github.com/snakers4/silero-vad), MIT.

The desktop backend bundles sherpa-onnx (https://github.com/k2-fsa/sherpa-onnx, Apache-2.0) and PyAV (https://github.com/PyAV-Org/PyAV, BSD-3-Clause), which includes FFmpeg libraries under their own licenses.

## Watch-along capture

The desktop backend bundles windows-capture (https://github.com/NiiightmareXD/windows-capture, MIT) and comtypes (https://github.com/enthought/comtypes, MIT) to capture the AstraTube window and its own audio on Windows.

## Dependencies

Node.js and Python dependencies remain governed by their respective package licenses. Before redistributing a packaged product, review the complete dependency and media license inventory.
