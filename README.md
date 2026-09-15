```text
 _____ _____ _        [ _ ]            
| ____|_   _| |       / _` | _   _ _ __  
|  _|   | | | |      | (_| || | | | '_ \ 
| |___  | | | |___    \__, || |_| | |_) |
|_____| |_| |_____|   |___/  \__,_| .__/ 
                                  |_|    
             ★ g is for GUI! ★
```

# ETLgup

**ETLgup** is a desktop GUI application designed for electronics test operators and researchers working with the CERN CMS Endcap Timing Layer (ETL). It streamlines the ingestion, validation, visual inspection, and upload of module test results to the CERN ETL database via the `etlup` client package.

---

## Features

Simply point the application to a directory containing module test results. The app will automatically detect and display the available tests, allowing you to visually inspect the data and upload it to the ETL database.

Use the settings dialog to configure between the staging/production database and supply your user-specific API key.

![Data Overview](/media/Screenshot_01.png "comment")

![Module IV Preview](/media/Screenshot_02.png "comment")

---

## Installation & Requirements

### Prerequisites

- Python `>= 3.10` (tested with Python 3.14)

### Setup with `uv` (Recommended)

```bash
# Clone repository and enter directory
cd etlgup

# Install dependencies into virtual environment
uv sync
```

### Setup with `pip`

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

## How to Run

### Launching the GUI

```bash
# Using uv
uv run main.py

# Or using an activated virtual environment
python main.py
```

### Direct Folder Auto-Load

You can optionally pass the path of a test run directory on the command line to automatically load it on startup:

```bash
uv run main.py /path/to/test_run_directory
```

### Running Tests

Run the full automated test suite (parser, data models, uploader dry-run, native dialogs, and headless GUI tests):

```bash
uv run pytest
```

---

## Standalone Executable Packaging

To build a single standalone executable with PyInstaller:

```bash
# Build standalone single-file executable at dist/etlgup
uv run python build_installer.py

# Or optionally build directory bundle in dist/etlgup/
uv run python build_installer.py --onedir
```

The resulting single standalone executable will be located at `dist/etlgup`.

---

## Configuration

Credentials and environment preferences can be configured via:
1. The **⚙ Settings** button in the top bar of the application window.
2. A `.env` file located in the working directory:
   ```env
   ETL_API_TOKEN=your_cern_api_token_here
   ETL_USER=operator_username
   ETL_LOCATION=BU
   ETL_PROD=false
   ```

---

## AI Disclaimer

> **Notice**: This application was created and developed with the assistance of artificial intelligence (AI) tools and language models (Junie / LLM coding assistant). While the codebase includes automated verification and test suites, operators and researchers are advised to review and validate data transformations, test selections, and upload actions before publishing data to production databases.
