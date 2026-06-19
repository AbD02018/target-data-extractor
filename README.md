<div align="center">

# 🎯 target-data-extractor

### *Pipeline-ready target data extraction for bug bounty automation.*

[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Output](https://img.shields.io/badge/output-JSON%2FYAML%2FCSV-success?style=flat-square)](#-output-formats)
[![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)

</div>

---

## 🎯 What

`target-data-extractor` is the data-collection layer for automated bug bounty pipelines. It pulls program metadata, in-scope assets, contract addresses, and audit history into a normalized format that downstream tools (recon-cli, foundry templates, PoC generators) can consume.

Use it to:
- Build a local index of every active program you hunt
- Detect scope changes
- Generate per-target PoC boilerplate
- Power dashboards / analytics

---

## ⚡ Quick Start

```bash
pip install target-data-extractor
```

### From source

```bash
git clone https://github.com/AbD02018/target-data-extractor
cd target-data-extractor
pip install -e .
```

---

## 🚀 Usage

```bash
# Extract all programs
target-data-extractor extract --all --output programs.json

# Extract one platform
target-data-extractor extract --platform immunefi --output immunefi.json

# Extract one program
target-data-extractor extract --platform immunefi --program templar-protocol

# Detect changes since last run
target-data-extractor diff --since yesterday
```

---

## 📦 Output Schema

```yaml
program:
  id: "templar-protocol"
  platform: "immunefi"
  url: "https://immunefi.com/bug-bounty/templar-protocol"
  status: "live"
  tvl_usd: 8_500_000          # when available
  max_bounty_usd: 250_000
  audit:
    - auditor: "Trail of Bits"
      date: "2026-04-12"
      report_url: "..."
  kyc_required: true
  scope:
    - type: "smart-contract"
      chain: "near"
      address: "v1.tmplr.near"
      asset: "Templar Market"
  tags: [defi, lending, near]
  extracted_at: "2026-06-19T14:00:00Z"
```

---

## 🏢 Supported Platforms

| Platform | Coverage |
|---|---|
| Immunefi | Full (incl. TVL, audit history) |
| HackerOne | Public programs only |
| Cantina | Active audits + competitions |
| Bugcrowd | Public programs only |
| YesWeHack | Public programs only |
| Bugrap | Public programs |
| HackenProof | Public programs |

---

## 🤝 Contributing

PRs welcome for:
- New platform integrations
- Schema extensions
- Caching layer
- Output format improvements

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 📄 License

MIT — see [LICENSE](LICENSE).

---

<div align="center">
  <sub>Built by <a href="https://github.com/AbD02018">@AbD02018</a> · Smart contract security researcher</sub>
</div>
