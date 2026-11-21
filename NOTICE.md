# Notice

The clip-finding approach (whole transcript as `row|time|text`, model returns row ranges, local
validation and de-duplication) and the Chinese prompt wording are adapted from
[AutoClip](https://github.com/zhouxiaoka/autoclip) `backend/pipeline/clip_finder.py`,
Copyright (c) AutoClip authors, MIT License. Code here is a rewrite; no AutoClip file is copied
verbatim. Keep this notice if you redistribute.

Optional speaker labels download two models on first use (not bundled in this repository):
the pyannote segmentation 3.0 model (MIT, license file shipped with the model) and the 3D-Speaker ERes2Net
model (the 3D-Speaker project is Apache-2.0; the terms of the pretrained weights are on their ModelScope page
and have not been verified here), both as
published in the sherpa-onnx release assets, and run them with sherpa-onnx (Apache-2.0).
