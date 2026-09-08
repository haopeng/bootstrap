"""ventures: a portfolio of small, legitimate AI-powered services.

Each sub-package is one product with the same shape:

    <product>/engine.py   -- deterministic rules layer (always runs)
    <product>/llm.py      -- Claude layer (runs when a key is present)
    <product>/pipeline.py -- end-to-end: input -> findings -> deliverable

Run everything on sample data with:  python -m ventures demo
Serve everything with:               python -m ventures serve
"""
__version__ = "0.1.0"
