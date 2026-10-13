# do_it

do_it is an open-source terminal agent that uses your signed-in ChatGPT tab and local tools to work with files and run commands.

## Requirements

- Python 3.10 or newer
- Git
- Chrome or Edge with a ChatGPT account

## Install

Clone the repository and install the Python dependencies:

```sh
git clone https://github.com/kni1514/do_it.git
cd do_it
python -m pip install -r requirements.txt
```

In Chrome or Edge, sign in to ChatGPT. Open `chrome://extensions` or `edge://extensions`, enable Developer mode, choose **Load unpacked**, and select the `ext` folder in the cloned repository. Keep the ChatGPT tab open.

## Run

Start an interactive session from the repository folder:

```sh
python do_it.py
```

To send one prompt:

```sh
python do_it.py "list files in this project"
```

On Windows, use `py` instead of `python` if needed. The local bridge starts automatically with do_it and closes when the process exits. No separate API key or manual server start is required.

## Update

From the cloned repository, run:

```sh
git pull
python -m pip install -r requirements.txt
```

The browser extension communicates with the ChatGPT tab. Prompts and relevant tool results are sent through that session. File and shell tools run on your computer.
