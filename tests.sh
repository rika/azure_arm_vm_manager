#!/bin/bash

unit_test='test_azure.py'
main_class='TestAzure'

tests=( \
    'test_simple_provision' \
    'test_conc_provision' \
    'test_template_provision' \
)

for t in "${tests[@]}"
do
    echo $t
    python $unit_test $main_class.$t &> $t.out &
    sleep 1
done
