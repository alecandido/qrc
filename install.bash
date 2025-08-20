#!/usr/bin/env bash

inst='poetry run pip install'

$inst qibolab-qm qibolab-qblox
$inst -e ./qibocal
$inst -e ./qibolab
$inst -e ./qibo
# qcodes still requirs NumPy 1
$inst 'numpy<2'
