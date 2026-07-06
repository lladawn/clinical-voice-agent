# STT eval clips

Drop pre-recorded (or synthesized) audio clips of clinical terms here, each with
a matching reference transcript:

```
veralixumab_subcutaneous.wav
veralixumab_subcutaneous.txt     ->  "veralixumab one fifty milligrams subcutaneous"
dosing_schedule.wav
dosing_schedule.txt              ->  "subcutaneous injection every two weeks"
```

The eval (`python -m evals.run --stt`) transcribes each `.wav` with Deepgram
Nova-3 Medical and reports Word Error Rate against the `.txt` reference. WER ≤ 10%
counts as a pass.

Requires `DEEPGRAM_API_KEY` in the environment and the `deepgram-sdk` package
(installed transitively via `livekit-plugins-deepgram`).

Tip for a strong demo: record the same clips and also run them through a general
model (e.g. nova-2) to show Nova-3 Medical's lower WER on clinical terminology.
