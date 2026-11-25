<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/brand/brainlife-mark-on-dark.svg">
    <img src=".github/brand/brainlife-mark-on-light.svg" alt="brainlife.io" width="140">
  </picture>
</p>

<h1 align="center">pybrainlife</h1>

<p align="center">
  Collect, collate, analyse and plot the derivatives in your brainlife.io project, from Python.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Status-active-brightgreen.svg" alt="Status: active">
  <a href="https://brainlife.io"><img src="https://img.shields.io/badge/brainlife.io-site-3b9fd0.svg" alt="brainlife.io"></a>
  <a href="https://brainlife.io/docs"><img src="https://img.shields.io/badge/Docs-brainlife.io%2Fdocs-005981.svg" alt="Documentation"></a>
  <a href="https://doi.org/10.1038/s41592-024-02237-2"><img src="https://img.shields.io/badge/DOI-10.1038%2Fs41592--024--02237--2-e57536.svg" alt="Nature Methods paper"></a>
  <a href="https://pypi.org/project/pybrainlife/"><img src="https://img.shields.io/pypi/v/pybrainlife.svg" alt="PyPI"></a>
</p>

## 🧠 At a glance

| | |
|---|---|
| 🧭 **What** | Turns the outputs of brainlife.io Apps (tract profiles, parcellation statistics, cortical measures, networks) into tidy pandas tables and publication-ready plots |
| 📦 **Install** | `pip install pybrainlife` (Python 3.8 or newer) |
| 🧩 **Modules** | `pybrainlife.data.collect` · `pybrainlife.data.manipulate` · `pybrainlife.vis.plots` |
| ⌨️ **CLI** | The Python command-line tool `bl` (login, data, datatypes, `bl aimport`) is on branch [`enh/cli`](https://github.com/brainlife/pybrainlife/tree/enh/cli); it replaces the unsupported Node [brainlife/cli](https://github.com/brainlife/cli) |
| 🔗 **Built on** | pandas, NumPy, SciPy, scikit-learn, seaborn, Brain Connectivity Toolbox (bctpy), igraph, jgf |

## 🚀 Getting started

### ☁️ In a brainlife.io Analysis notebook

Open your project on [brainlife.io](https://brainlife.io/projects), go to the **Analysis** tab and start a notebook. The notebook knows your project through the `PROJECT_ID` environment variable, so you can collect every dataset of a datatype in one call:

```python
from pybrainlife.data import collect

# all tract-profile outputs in this project, one row per subject/session/structure/node
profiles = collect.collect_data(
    datatype="neuro/tractmeasures",
    datatype_tags=[],          # e.g. ["profiles"]; prefix a tag with "!" to exclude it
    tags=[],                   # dataset tags, same "!" rule
    filename="output_FiberStats.csv",
    outPath="data/tractmeasures.csv",   # cached here; pass overwrite=True to rebuild
)

subjects = collect.collect_subject_data("data/")   # participants table from input/participants.json
```

### 💻 On your own machine

```bash
pip install pybrainlife
```

Set `PROJECT_ID` to your brainlife.io project ID before calling `collect_data`, or work from CSV files you have already downloaded.

## 🧩 What's inside

| Module | What it does | Key functions |
|---|---|---|
| `pybrainlife.data.collect` | Finds the datasets of a datatype in a project (filtering by tags and datatype tags, handling duplicates) and compiles them into one DataFrame | `collect_data`, `collect_subject_data`, `create_color_dictionary` |
| `pybrainlife.data.manipulate` | Cleans and transforms the compiled data: node cutting and averaging of tract profiles, distance-based outlier detection, profile flip checks, reference datasets, connectivity matrices and network measures | `cut_nodes`, `compute_mean_data`, `outlier_detection`, `profile_flip_check`, `build_reference_data`, `build_connectivity_matrix`, `parse_networks`, `threshold_matrices`, `compute_mean_network` |
| `pybrainlife.vis.plots` | Plots: scatter plots with trend lines and colour-coded distance, faceted relational plots, and tract profiles with error bands | `singleplot_scatter`, `relplot_scatter`, `plot_profiles` |

## ⌨️ Python CLI (`bl`, branch `enh/cli`)

The [`enh/cli`](https://github.com/brainlife/pybrainlife/tree/enh/cli) branch adds a `brainlife` package with an API client and the `bl` command (`bl login`, `bl data`, `bl datatype`, `bl aimport`). It is not on PyPI yet:

```bash
pip install "git+https://github.com/brainlife/pybrainlife@enh/cli"
bl login
bl aimport <folder> --project <id>      # convert to BIDS, de-identify, validate, then upload
```

`bl aimport` runs the [aimport engine](https://github.com/brainlife/ezbids/tree/master/aimport) from ezBIDS in Docker, shows its plan in the terminal and uploads only after you approve it; the raw data never leaves your computer. See the branch README and the [aimport documentation](https://brainlife.io/docs/using_aimport/) for all options.

## 🔗 Related repositories

| Repository | Role |
|---|---|
| [ezbids](https://github.com/brainlife/ezbids) | Neuroscience data to BIDS, from instruments to shared datasets (and the aimport engine) |
| [warehouse-next](https://github.com/brainlife/warehouse-next) | The API pybrainlife and `bl` talk to |
| [docs](https://github.com/brainlife/docs) | User documentation |
| [cli](https://github.com/brainlife/cli) | Former Node.js CLI (no longer supported) |

## 👥 Authors

Brad Caron (author). Contributors: Anibal Heinsfeld, Gabriele Amorosino, Soichi Hayashi, Franco Pestilli.

## 📚 Citing

If you use brainlife.io in your work, please cite:

> Hayashi S, Caron BA, Heinsfeld AS, et al. brainlife.io: a decentralized and open-source cloud platform to support neuroscience research. *Nature Methods* 21:809–813 (2024). [doi:10.1038/s41592-024-02237-2](https://doi.org/10.1038/s41592-024-02237-2)

## 💰 Funding

brainlife.io is developed by the Pestilli Lab at The University of Texas at Austin and is publicly funded; acknowledging that support helps keep it running.

<details>
<summary>Grants (verified list, from <a href="https://github.com/brainlife/ezbids/blob/master/CREDITS.md#funding">ezbids CREDITS.md</a>)</summary>

| Funder | Award | Title |
|---|---|---|
| NIH NINDS | [U24NS140384](https://reporter.nih.gov/project-details/U24NS140384) | BRAIN CONNECTS: The Axonal Projectome EXchange (APEX) |
| NIH NIMH | [R01MH126699](https://reporter.nih.gov/project-details/R01MH126699) | Community-driven development of BIDS |
| NIH NIBIB | [R01EB030896](https://reporter.nih.gov/project-details/R01EB030896) | CRCNS US-France: open science and cloud computing of MEEG |
| NIH NIBIB | [R01EB029272](https://reporter.nih.gov/project-details/R01EB029272) | CRCNS US-France: lowering the barrier of entry to network neuroscience |
| NSF | [BCS-1636893](https://www.nsf.gov/awardsearch/showAward?AWD_ID=1636893), [2148729](https://www.nsf.gov/awardsearch/showAward?AWD_ID=2148729) | BD Spokes: Advanced Computational Neuroscience Network |
| NSF | [BCS-1734853](https://www.nsf.gov/awardsearch/showAward?AWD_ID=1734853), [2203524](https://www.nsf.gov/awardsearch/showAward?AWD_ID=2203524) | NCS-FO: Connectome mapping algorithms |
| NSF | [IIS-1912270](https://www.nsf.gov/awardsearch/showAward?AWD_ID=1912270), [2148700](https://www.nsf.gov/awardsearch/showAward?AWD_ID=2148700) | CRCNS US-German: DataLad |
| NSF | [ACI-1916518](https://www.nsf.gov/awardsearch/showAward?AWD_ID=1916518) | BD Hubs: Midwest Big Data Hub |
| Wellcome Trust | [226486](https://grantnav.threesixtygiving.org/grant/360G-Wellcome-226486_Z_22_Z) | Developing an international governance framework to advance global brain and mental health data equity and innovation |

</details>

## 🤝 Contributing

Issues and pull requests are welcome in this repository. For help using brainlife.io, see the [documentation](https://brainlife.io/docs).

## ⚖️ License

This repository does not include a license file yet.

<p align="center"><sub>brainlife.io · Brain data across scales. One place to analyze, share and publish it. · The University of Texas at Austin</sub></p>
