# Aegis Notebooks

These are standalone academic notebooks for the INFO 7390 graduate assignment.
They are independent of the main FastAPI backend in `../backend/` and can be run
directly with Jupyter after installing `requirements_notebooks.txt`.

## Setup

```bash
pip install -r requirements_notebooks.txt
jupyter lab
```

## Contents

| Directory / File       | Purpose                                      |
|------------------------|----------------------------------------------|
| `verify_apis.py`       | Checks that all three LLM API keys work      |
| `data/`                | Input datasets and intermediate artifacts    |
| `figures/`             | Saved plots and visualisations               |

## API Keys

Keys are loaded from `../backend/.env`. Copy that file or set the environment
variables before running any notebook.
