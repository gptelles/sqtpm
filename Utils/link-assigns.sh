#!/bin/bash

# Links .pass files into every subdirectory that has a config file.

pass=`ls -1 *.pass`

for d in `find . -mindepth 1 -maxdepth 1 -type d`; do 
  cd $d; 
  if [[ -e 'config' ]]; then
    for l in $pass; do 
      ln -s ../$l .
    done 
  fi
  cd ..
done



