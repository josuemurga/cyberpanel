#! /bin/bash

if hash python 2>/dev/null; then
    PYTHON=python
elif hash python3 2>/dev/null; then
    PYTHON=python3
else
    PYTHON=python2
fi
$PYTHON "$(dirname $0)/installation.py" $@
