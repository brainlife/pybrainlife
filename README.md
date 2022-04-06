[![Abcdspec-compliant](https://img.shields.io/badge/ABCD_Spec-v1.1-green.svg)](https://github.com/soichih/abcd-spec)

# pybrainlife
This repository contains the python package for collecting, collating, manipulating, analyzing, and visualizing MRI data generated on brainlife.io. Designed to used within the brainlife.io Analysis tab Jupyter notebooks, can be installed as a pypi package to your local machine.

### Authors
- Brad Caron (bacaron@iu.edu)

### Contributors
- Soichi Hayashi (hayashi@iu.edu)
- Franco Pestilli (franpest@indiana.edu)

### Funding
[![NSF-BCS-1734853](https://img.shields.io/badge/NSF_BCS-1734853-blue.svg)](https://nsf.gov/awardsearch/showAward?AWD_ID=1734853)
[![NSF-BCS-1636893](https://img.shields.io/badge/NSF_BCS-1636893-blue.svg)](https://nsf.gov/awardsearch/showAward?AWD_ID=1636893)

### Citations

Please cite the following articles when publishing papers that used data, code or other resources created by the brainlife.io community.

1. Avesani, P., McPherson, B., Hayashi, S. et al. The open diffusion data derivatives, brain data upcycling via integrated publishing of derivatives and reproducible open cloud services. Sci Data 6, 69 (2019). https://doi.org/10.1038/s41597-019-0073-y

### Directory structure
```
pybrainlife
├── dist
│   ├── pybrainlife-0.4.0-py3-none-any.whl
│   └── pybrainlife-0.4.0.tar.gz
├── poetry.lock
├── pybrainlife
│   ├── data
│   │   ├── collect.py
│   │   ├── manipulate.py
│   │   └── __pycache__
│   │       ├── collect.cpython-38.pyc
│   │       └── manipulate.cpython-38.pyc
│   ├── __init__.py
│   ├── __pycache__
│   │   └── __init__.cpython-38.pyc
│   └── vis
│       ├── data.py
│       ├── plots.py
│       └── __pycache__
│           ├── data.cpython-38.pyc
│           └── plots.cpython-38.pyc
├── pyproject.toml
├── README.rst
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

2022 The University of Texas at Austin
