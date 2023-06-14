#!/bin/bash
../../npf_compare.py \
        local \
        --force-retest \
        --test main.npf \
        --result-path results \
        --config n_runs=1 \
        --show-cmd \
        --show-all
