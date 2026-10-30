# Third-party provenance

Paths below are relative to the repository root.

| Component | Source/license | Retained notice |
| --- | --- | --- |
| Customized SGLang wheel `0.5.20.dev13+g75b9b06b02` | Baidu Unlimited-OCR `wheel/`; wheel distribution metadata declares Apache-2.0 | `vendor/SGLang-LICENSE`, also embedded in the unchanged wheel |
| `process_unlimitedOCR2.py` | Baidu Unlimited-OCR; MIT | `vendor/Unlimited-OCR-LICENSE` |
| KaTeX 0.16.22 and fonts | KaTeX; MIT | `static/katex/LICENSE`, asset URLs/hashes in `static/katex/assets-manifest.json` |

Baidu source commit: `6c5d1906ba638a7cd87bc00f14452a47fdabf16b`. Exact sources and SHA-256 are retained in `vendor/upstream-manifest.json`; the wheel SHA also matches the official Git-LFS pointer at that revision. The original local postprocessor backup had one extra final blank line; this repository retains the upstream file's original bytes, with identical functional source.

Model weights are not redistributed. The downloader selects the official Hugging Face model revision recorded in the manifest; see the [model card](https://huggingface.co/baidu/Unlimited-OCR-2) and its license. Dependencies installed during deployment retain their own licenses. The root MIT license covers the new work in this repository and does not replace these third-party licenses.
