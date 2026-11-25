# pybrainlife
This repository contains the python package for collecting, collating, manipulating, analyzing, and visualizing MRI data generated on brainlife.io. Designed to used within the brainlife.io Analysis tab Jupyter notebooks, can be installed as a pypi package to your local machine.

### Authors
- Brad Caron (bacaron@utexas.edu)

### Contributors
- Anibal Heinsfeld (anibalsolon@utexas.edu)
- Gabriele Amorosino (gabriele.amorosino@utexas.edu)
- Soichi Hayashi (hayashi@utexas.edu)
- Franco Pestilli (pestilli@utexas.edu)

### Funding
[![NSF-BCS-1734853](https://img.shields.io/badge/NSF_BCS-1734853-blue.svg)](https://nsf.gov/awardsearch/showAward?AWD_ID=1734853)
[![NSF-BCS-1636893](https://img.shields.io/badge/NSF_BCS-1636893-blue.svg)](https://nsf.gov/awardsearch/showAward?AWD_ID=1636893)

### Citations

Please cite the following articles when publishing papers that used data, code or other resources created by the brainlife.io community.

1. Hayashi, S., Caron, B., et al. **In review**

### Directory structure
```
pybrainlife
├── dist
│   ├── pybrainlife-1.0.0-py3-none-any.whl
│   └── pybrainlife-1.0.0.tar.gz
├── poetry.lock
├── pybrainlife
│   ├── data
│   │   ├── collect.py
│   │   └── manipulate.py
│   ├── __init__.py
│   └── vis
│       ├── plots.py
│       └── __pycache__
│           ├── data.cpython-38.pyc
│           └── plots.cpython-38.pyc
├── pyproject.toml
├── README.md
└── tests
    ├── __init__.py
    └── test_pybrainlife.py
```

### Installing locally
This package can be installed locally via PyPi using the following command:

```
pip install pybrainlife
```

### bl aimport

`bl aimport` imports a folder of DICOM, NIfTI, EEG/MEG or microscopy files from your computer into an existing brainlife.io project. It runs the [aimport engine](https://github.com/brainlife/ezbids/tree/master/aimport) in Docker, shows its plan in the terminal, converts to BIDS, de-identifies, defaces, validates, and only then uploads. The raw data never leaves your computer.

Install (until the next release):

```
pip install "git+https://github.com/brainlife/pybrainlife@enh/cli"
bl login
```

You also need Docker. The engine image is `brainlife/aimport:dev` (change it with `--image`); it is not published yet, so build it from the ezBIDS repository: `docker build --platform linux/amd64 -t brainlife/aimport:dev -f aimport/Dockerfile .`. On Colima (macOS) the input, work and keys folders must be under your home folder.

```
bl aimport <folder> --project <id> [options]
```

| Flag | Meaning |
| --- | --- |
| `-p, --project <id>` | project to upload to (required; it must exist) |
| `--target bids\|datatypes` | also show each object's brainlife datatype in the plan (default `bids`) |
| `--deface pydeface\|quickshear` | defacing method (default `pydeface`) |
| `--work <dir>` | work folder (default `~/.cache/brainlife/aimport/<project id>/work`) |
| `--keys <dir>` | pseudonym key folder (default `~/.config/brainlife/aimport/keys`); keep it safe, it is never uploaded |
| `--image <ref>` | engine image |
| `-y, --yes` | approve the plan without asking |
| `-t, --tag <tag>` | tag every uploaded object (repeatable) |
| `--qa` | after validation, open the engine's local QA viewer and ask `Upload this dataset? [y/N/v(iewer link again)]` |
| `--remote <url>` | a remote microscopy source (`https://` or `s3://`, repeatable; never printed) |
| `--no-upload` | stop after validation |
| `--ui` | review on brainlife.io (not available yet; exits 2) |

At the plan, answer `y` to approve, `N` to stop with nothing written, or `e` to edit it through the engine's `PATCH /plan` (the command prints the address, a session token and an example `curl`). The engine is stopped once the output is validated, before the upload, and on Ctrl-C, `SIGTERM` or `SIGHUP`.

What goes up, only from a `validated` output: each image as an object of its brainlife datatype, after its datatype validator has accepted it on your computer (objects already in the project are skipped); EEG/MEG objects keep their `channels.tsv` (with bad channels marked in the QA viewer); the participants table; the other metadata files as project files under `bids/`. Microscopy reference datasets are streamed chunk by chunk from where they are (the input folder or an https URL) into their objects; nothing is copied to disk. Never uploaded: the input folder, the pseudonym key, the chunk map, `sourcedata/`, and a failed or invalid output.

Worked examples (MRI, EEG, microscopy): [ezBIDS aimport/EXAMPLES.md](https://github.com/brainlife/ezbids/blob/master/aimport/EXAMPLES.md).

### Dependencies

This package requires the following libraries.
  - python = "3.8"
  - numpy = "^1.9.3"
  - bctpy = "^0.5.2"
  - seaborn = "^0.11.2"
  - jgf = "^0.2.2"
  - scikit-learn = "^1.0.2"
  - pandas = "^1.4.2"
  - scipy = "^1.8.0"
  - requests = "^2.27.1"

Library of Modules for Loading Data and Analyzing Data from brainlife.io

2023 The University of Texas at Austin
