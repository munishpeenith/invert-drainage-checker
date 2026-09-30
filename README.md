# Invert

> ALL DIMENSIONS IN MILLIMETERS UNLESS NOTED AND NOT TO BE SCALED FROM DRAWINGS

A rule-driven checker for UK drainage drawings. It reads the manhole and pipe
schedules out of a drawing PDF, checks every pipe run against Approved Document H
and the Water UK adoption guidance, and produces a check sheet plus a long
section with failing runs marked.

Status: the rule loader, the network model and the check engine are built and
tested. Extraction, parsing and reporting are still scaffold.

## Running it

```
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pytest
```

Do not name the virtual environment `.venv` on macOS. A venv directory whose
name begins with a dot is created with the `UF_HIDDEN` flag, files written
inside it inherit the flag, and Python's `site` module skips hidden `.pth`
files. The editable install then silently fails to register and every import of
a project module raises `ModuleNotFoundError`. `chflags -R nohidden` clears it,
but naming the directory `venv` avoids it outright.

## What it does

## The feasibility call

What the model does, what it deliberately does not, and why.

## Results

- Extraction accuracy, field level
- Abstention rate
- False positives on checks, confirmed against a human read
- Cost per drawing, cold and cached
- Latency, cold and cached

## How it fails

## Data handling

## What production would need

## Scope
