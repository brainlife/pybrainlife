# pybrainlife
This repository contains the python package for collecting, collating, manipulating, analyzing, and visualizing MRI data generated on brainlife.io. Designed to used within the brainlife.io Analysis tab Jupyter notebooks, can be installed as a pypi package to your local machine.

### Authors
- Brad Caron (bacaron@utexas.edu)

### Contributors
- Anibal Heinsfeld (anibalsolon@utexas.edu)
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
