# AI Chatbot Cookie Tracking Research

A Python-based research project investigating cookie tracking, consent management, and third-party data collection associated with AI chatbots embedded in websites.

The project uses Playwright and Google Chrome to discover chatbot implementations, collect browser cookies and network requests, and analyze tracking behavior under different consent conditions.

The research also aims to compare chatbot providers, website industries, and hosting infrastructure to better understand differences in privacy and tracking practices.

---


## Installation and Setup

These instructions explain how to install and run the AI Chatbot Cookie Tracking Research tools.

### Prerequisites

Before starting, make sure the following software is installed:

- Python 3.10 or newer (dependency compatibility may vary)
- Git
- Google Chrome
- pip (Python package manager)
- Python virtual environment support (`venv`)

**Note:** The project was developed and tested on Kubuntu Linux. Windows and macOS compatibility has not yet been verified.

### 1. Clone the Repository

Open a terminal and run:

```bash
git clone https://github.com/Jsfili01/ai-chatbot-cookie-tracking.git
cd ai-chatbot-cookie-tracking
```

### 2. Create a Virtual Environment

On Linux/macOS:

```bash
python3 -m venv venv
source venv/bin/activate
```

On Windows PowerShell:

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Python Dependencies

Install the required Python packages:

```bash
python -m pip install -r requirements.txt
```

The project uses libraries including Playwright, HTTPX, and tldextract.

### 4. Install Google Chrome

The crawler currently uses Google Chrome through Playwright:

```python
p.chromium.launch(channel="chrome")
```

Google Chrome must be installed on the machine.

A graphical desktop environment is required for interactive browser experiments.

---

## Running the Research Tools

The project consists of three primary scripts:

- `discover.py` — Identifies websites containing chatbot-related evidence.
- `capture.py` — Records cookies and network requests during chatbot interactions.
- `analyze.py` — Analyzes collected cookies and potential tracking behavior.

### 1. Discover Websites with Chatbots

(venv) jordan@jordan-asuslaptopq530vj:~/chatbot-crawler$ cat README.md
## Installation and Setup

These instructions explain how to install and run the AI Chatbot Cookie Tracking Research tools.

### Prerequisites

Before starting, make sure the following software is installed:

- Python 3.10 or newer (dependency compatibility may vary)
- Git
- Google Chrome
- pip (Python package manager)
- Python virtual environment support (`venv`)

**Note:** The project was developed and tested on Kubuntu Linux. Windows and macOS compatibility has not yet been verified.

### 1. Clone the Repository

Open a terminal and run:

```bash
git clone https://github.com/Jsfili01/ai-chatbot-cookie-tracking.git
cd ai-chatbot-cookie-tracking
```

### 2. Create a Virtual Environment

On Linux/macOS:

```bash
python3 -m venv venv
source venv/bin/activate
```

On Windows PowerShell:

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Python Dependencies

Install the required Python packages:

```bash
python -m pip install -r requirements.txt
```

The project uses libraries including Playwright, HTTPX, and tldextract.

### 4. Install Google Chrome

The crawler currently uses Google Chrome through Playwright:

```python
p.chromium.launch(channel="chrome")
```

Google Chrome must be installed on the machine.

A graphical desktop environment is required for interactive browser experiments.

---

## Running the Research Tools

The project consists of three primary scripts:

- `discover.py` — Identifies websites containing chatbot-related evidence.
- `capture.py` — Records cookies and network requests during chatbot interactions.
- `analyze.py` — Analyzes collected cookies and potential tracking behavior.

### 1. Discover Websites with Chatbots

Create a text file named `sites.txt` containing one website URL per line.

Example:

```text
https://example.com/
https://example.org/
```

Replace these placeholder URLs with websites you want to investigate.


Run the discovery crawler:

```bash
python discover.py sites.txt --db discover.db --out queue.csv --deep
```

The crawler examines websites using HTML signatures, JavaScript variables, DOM elements, and network requests.

Results are saved to a SQLite database and exported to a CSV file.

**Note:** The database records completed tests. To perform a completely fresh discovery scan, use a new database filename.

### 2. Capture Cookies and Network Activity

Run a capture experiment:

```bash
python capture.py https://example.com/ --country US --consent none --scenario general
```

The browser will open and guide the researcher through the experiment.

The available consent conditions are:

| Condition | Description |
|---|---|
| `none` | Do not interact with the cookie consent banner |
| `accept` | Attempt to accept cookies |
| `reject` | Attempt to reject optional cookies |

For example, to test the Reject All condition:

```bash
python capture.py https://www.example.com/ --country US --consent reject --scenario general
```

The script records cookies and network activity at four stages:

1. **Page Load:** Records cookies after the website loads.
2. **Consent:** Records cookies after the selected consent action.
3. **Chat Open:** Records cookies after opening the chatbot.
4. **Chat Sent:** Records cookies after sending a synthetic message.

Synthetic identities are used instead of real personal information.

Capture results are saved as JSON files in the `captures/` directory.

**Important:** The `--country` argument changes browser locale, timezone, and geolocation settings. It does not change the public IP address. Geographic testing requires a verified country-specific network connection or proxy.

### 3. Analyze Captured Data

After completing an experiment, run:

```bash
python analyze.py captures/<capture_filename>.json
```

Replace `<capture_filename>` with the name of the generated JSON file.

For example:

```bash
python analyze.py captures/<capture_filename>.json
```

The analyzer reports:

- Total cookies collected at each stage
- First-party and third-party cookie classifications
- Analytics, marketing, functional, and unknown cookies
- Cookies first observed during chatbot interaction
- Third-party network activity
- Synthetic information detected in outgoing requests
- Preliminary consent-related findings

Analysis results are exported to the `analysis/` directory.

---

## Research Methodology

The research investigates how embedded AI chatbots interact with website cookies, third-party tracking services, and consent management systems.

The methodology compares cookie behavior across three consent conditions:

1. No consent interaction
2. Accept All
3. Reject All

Each experiment uses a fresh browser context to reduce interference from previously stored cookies.

The research also aims to classify websites according to their industry, chatbot provider, web-server technology, hosting infrastructure, and consent management platform.

## Privacy and Ethical Considerations

- Synthetic personal information is used for chatbot testing.
- Raw cookie captures and session identifiers are excluded from the GitHub repository.
- Websites are tested using controlled browser sessions.
- Cookie classifications are preliminary and require validation.
- Observed tracking behavior does not automatically establish a legal or regulatory violation.
- Researchers should respect website access restrictions and applicable research policies.

## Current Limitations

- Not all chatbot implementations are automatically detected.
- Some websites may restrict automated browsers.
- Chatbot-related network activity does not necessarily prove that a chatbot is AI-powered.
- Some cookie classifications require manual verification.
- Consent-button clicks and recorded consent states should be verified.
- Cross-country comparisons require verified geographic network locations.
- The project has primarily been tested on Kubuntu Linux.
Create a text file named `sites.txt` containing one website URL per line.

Example:

```text
https://example.com/
https://example.org/
```

Replace these placeholder URLs with websites you want to investigate.


Run the discovery crawler:

```bash
python discover.py sites.txt --db discover.db --out queue.csv --deep
```

The crawler examines websites using HTML signatures, JavaScript variables, DOM elements, and network requests.

Results are saved to a SQLite database and exported to a CSV file.

**Note:** The database records completed tests. To perform a completely fresh discovery scan, use a new database filename.

### 2. Capture Cookies and Network Activity

Run a capture experiment:

```bash
python capture.py https://example.com/ --country US --consent none --scenario general
```

The browser will open and guide the researcher through the experiment.

The available consent conditions are:

| Condition | Description |
|---|---|
| `none` | Do not interact with the cookie consent banner |
| `accept` | Attempt to accept cookies |
| `reject` | Attempt to reject optional cookies |

For example, to test the Reject All condition:

```bash
python capture.py https://www.example.com/ --country US --consent reject --scenario general
```

The script records cookies and network activity at four stages:

1. **Page Load:** Records cookies after the website loads.
2. **Consent:** Records cookies after the selected consent action.
3. **Chat Open:** Records cookies after opening the chatbot.
4. **Chat Sent:** Records cookies after sending a synthetic message.

Synthetic identities are used instead of real personal information.

Capture results are saved as JSON files in the `captures/` directory.

**Important:** The `--country` argument changes browser locale, timezone, and geolocation settings. It does not change the public IP address. Geographic testing requires a verified country-specific network connection or proxy.

### 3. Analyze Captured Data

After completing an experiment, run:

```bash
python analyze.py captures/<capture_filename>.json
```

Replace <capture_filename> with the name of the JSON file generated by capture.py


The analyzer reports:

- Total cookies collected at each stage
- First-party and third-party cookie classifications
- Analytics, marketing, functional, and unknown cookies
- Cookies first observed during chatbot interaction
- Third-party network activity
- Synthetic information detected in outgoing requests
- Preliminary consent-related findings

Analysis results are exported to the `analysis/` directory.

---

## Research Methodology

The research investigates how embedded AI chatbots interact with website cookies, third-party tracking services, and consent management systems.

The methodology compares cookie behavior across three consent conditions:

1. No consent interaction
2. Accept All
3. Reject All

Each experiment uses a fresh browser context to reduce interference from previously stored cookies.

The research also aims to classify websites according to their industry, chatbot provider, web-server technology, hosting infrastructure, and consent management platform.

## Privacy and Ethical Considerations

- Synthetic personal information is used for chatbot testing.
- Raw cookie captures and session identifiers are excluded from the GitHub repository.
- Websites are tested using controlled browser sessions.
- Cookie classifications are preliminary and require validation.
- Observed tracking behavior does not automatically establish a legal or regulatory violation.
- Researchers should respect website access restrictions and applicable research policies.

## Current Limitations

- Not all chatbot implementations are automatically detected.
- Some websites may restrict automated browsers.
- Chatbot-related network activity does not necessarily prove that a chatbot is AI-powered.
- Some cookie classifications require manual verification.
- Consent-button clicks and recorded consent states should be verified.
- Cross-country comparisons require verified geographic network locations.
- The project has primarily been tested on Kubuntu Linux.
