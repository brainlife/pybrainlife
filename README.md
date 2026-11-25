<h1 align="center">pybrainlife</h1>

<p align="center">
  Collect, collate, analyse and plot the MRI derivatives in your brainlife.io project, from Python.
</p>

<p align="center">
  <a href="https://pypi.org/project/pybrainlife/"><img src="https://img.shields.io/pypi/v/pybrainlife.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/pybrainlife/"><img src="https://img.shields.io/pypi/pyversions/pybrainlife.svg" alt="Python versions"></a>
  <a href="https://brainlife.io"><img src="https://img.shields.io/badge/brainlife.io-Analysis%20tab-blue.svg" alt="brainlife.io"></a>
</p>

## 🧠 At a glance

> **pybrainlife turns the outputs of brainlife.io Apps (tract profiles, parcellation statistics, cortical measures, networks) into tidy pandas tables and publication-ready plots.**

It is built for the Jupyter notebooks in a brainlife.io project's **Analysis** tab, where your project's data are already mounted, and it also installs on your own machine.

| | |
|---|---|
| 📦 **Install** | `pip install pybrainlife` |
| 🐍 **Python** | 3.8 or newer |
| 🧩 **Modules** | `pybrainlife.data.collect` · `pybrainlife.data.manipulate` · `pybrainlife.vis.plots` |
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

## 📚 Citing

> [!TIP]
> If you use pybrainlife or data created on brainlife.io, please cite brainlife.io:

- Hayashi S, Caron BA, Heinsfeld AS, et al. brainlife.io: a decentralized and open-source cloud platform to support neuroscience research. *Nature Methods* 21:809–813 (2024). [doi:10.1038/s41592-024-02237-2](https://doi.org/10.1038/s41592-024-02237-2)

## 👥 Authors

- Brad Caron (author)

**Contributors:** Anibal Heinsfeld, Soichi Hayashi, Franco Pestilli ([@francopestilli](https://github.com/francopestilli))

## 💰 Funding

[![Wellcome-226486/Z/22/Z](https://img.shields.io/badge/Wellcome-226486%2FZ%2F22%2FZ-purple.svg)](https://wellcome.org/)
[![NIH-NINDS-U24NS140384](https://img.shields.io/badge/NIH_NINDS-U24NS140384-green.svg)](https://reporter.nih.gov/project-details/11261037)
[![NIH-NINDS-UM1NS132207](https://img.shields.io/badge/NIH_NINDS-UM1NS132207-green.svg)](https://reporter.nih.gov/project-details/11411328)
[![NIH-NIBIB-R01EB029272](https://img.shields.io/badge/NIH_NIBIB-R01EB029272-green.svg)](https://reporter.nih.gov/project-details/10262925)
[![NIH-NIBIB-R01EB030896](https://img.shields.io/badge/NIH_NIBIB-R01EB030896-green.svg)](https://reporter.nih.gov/project-details/10428625)
[![NIH-NIMH-R01MH126699](https://img.shields.io/badge/NIH_NIMH-R01MH126699-green.svg)](https://reporter.nih.gov/project-details/10460628)
[![NIH-NIDCD-R01DC020088](https://img.shields.io/badge/NIH_NIDCD-R01DC020088-green.svg)](https://reporter.nih.gov/project-details/11140284)
[![NSF-BCS-1734853](https://img.shields.io/badge/NSF_BCS-1734853-blue.svg)](https://www.nsf.gov/awardsearch/showAward?AWD_ID=1734853)
[![NSF-BCS-2203524](https://img.shields.io/badge/NSF_BCS-2203524-blue.svg)](https://www.nsf.gov/awardsearch/showAward?AWD_ID=2203524)
[![NSF-IIS-1636893](https://img.shields.io/badge/NSF_IIS-1636893-blue.svg)](https://www.nsf.gov/awardsearch/showAward?AWD_ID=1636893)
[![NSF-OAC-2148729](https://img.shields.io/badge/NSF_OAC-2148729-blue.svg)](https://www.nsf.gov/awardsearch/showAward?AWD_ID=2148729)
[![NSF-IIS-1912270](https://img.shields.io/badge/NSF_IIS-1912270-blue.svg)](https://www.nsf.gov/awardsearch/showAward?AWD_ID=1912270)
[![NSF-IIS-2148700](https://img.shields.io/badge/NSF_IIS-2148700-blue.svg)](https://www.nsf.gov/awardsearch/showAward?AWD_ID=2148700)
[![NSF-OAC-1916518](https://img.shields.io/badge/NSF_OAC-1916518-blue.svg)](https://www.nsf.gov/awardsearch/showAward?AWD_ID=1916518)

<sub>brainlife.io is publicly funded, and acknowledging that support helps keep it running. This App was developed with support from Wellcome, the U.S. National Institutes of Health (including the BRAIN Initiative BRAIN CONNECTS program: The Axonal Projectome EXchange, U24NS140384, and the Center for Mesoscale Connectomics, UM1NS132207) and the U.S. National Science Foundation.</sub>

<sub>© The University of Texas at Austin.</sub>
