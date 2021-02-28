#!/bin/bash

# VM-side executor for VirtualBox without a shared directory.
# This file is part of sqtpm.

dir=$1
lang=$2
cputime=$3
virtmem=$4
stkmem=$5

cd $dir &>/dev/null
umask 0000

chmod u+x elf

for case in `ls *.in`; do
  tag=${case/.in/}
  if [[ "$lang"  == "Python3" ]]; then 
    bash -c "ulimit -c 0 -t $cputime; python3 ./elf <$case 1>$tag.run.out 2>$tag.run.err; echo \$? >$tag.run.st"
  elif [[ "$lang"  == "Java" ]]; then 
    bash -c "ulimit -c 0 -t $cputime; java -jar ./elf <$case 1>$tag.run.out 2>$tag.run.err; echo \$? >$tag.run.st"
  else
    bash -c "ulimit -c 0 -t $cputime -v $virtmem -s $stkmem; ./elf <$case 1>$tag.run.out 2>$tag.run.err; echo \$? >$tag.run.st"
  fi    
done


