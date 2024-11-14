#!/bin/bash
../../npf.py \
        local \
        --force-retest \
        --test main.npf \
        --result-path results \
        --config n_runs=1 \
        --show-cmd \
        --show-all
