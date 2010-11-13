#!/bin/bash

export PATH=$PATH:/usr/local/bin

ulimit -v 300000
ulimit -m 300000

./import-and-analyse.py
