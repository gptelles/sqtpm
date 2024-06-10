#!/bin/bash

# Link .pass files into every subdirectory that has a config file.

pwd

# pass=`ls -1 *.pass`
pass="$1"

for d in */; do 
  cd "$d"

  if [[ -e 'config' ]]; then
    for l in $pass; do 
       ln -s ../$l .
    done 
  fi

  cd ..
done



