# Django News PR Filter

A simple script that automates the first paragraph of the 'Updates to Django' section for https://django-news.com.

## Installation

1. This script uses the `gh` CLI to search and filter PRs. See [gh CLI installation instructions](https://github.com/cli/cli?tab=readme-ov-file#installation).


2. After installing `gh` CLI, you'll have to authenticate with a GitHub host.

```bash
gh auth login
```

3. Then you can create a `venv` and install the dependencies:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage
Running `python main.py` without any args/kwargs will pull last week's (Monday until Sunday) merged PRs and will dump the output to an `OUT.md`.

Example `OUT.md`:
```md
Updates to Django
=============

# Synopsis
Last week we had [15 pull requests](https://github.com/django/django/pulls?q=is%3Apr%20merged%3A2024-01-08..2024-01-14) merged into Django by 12 different contributors - including 3 first time contributors! Congratulations to [Waheedsys](https://github.com/Waheedsys), [evananyonga](https://github.com/evananyonga), and [dhalenok](https://github.com/dhalenok) for having their first commits merged into Django - welcome on board!  

# PRs that modified the release file
- [https://github.com/django/django/pull/17718](https://github.com/django/django/pull/17718)  
- [https://github.com/django/django/pull/17706](https://github.com/django/django/pull/17706)  
- [https://github.com/django/django/pull/17700](https://github.com/django/django/pull/17700)  

```


Help menu:
```
usage: Django News PR Filter [-h] [-s START_DATE] [-e END_DATE] [-o OUTPUT_FILE] [-v]

Pulls info about the PRs merged into 'django/django' last week.

options:
  -h, --help            show this help message and exit
  -s START_DATE, --start_date START_DATE
                        Filters merged PRs starting from `start_date`.e.g. 2024-01-28
  -e END_DATE, --end_date END_DATE
                        Filters merged PRs ending on `end_date`.e.g. 2024-01-28
  -o OUTPUT_FILE, --output_file OUTPUT_FILE
                        Specifies the location of the output .md file.
  -v, --verbose
```