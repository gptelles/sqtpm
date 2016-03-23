#!/bin/bash

dir=$1
cputime=$2
virtmem=$3
stkmem=$4

cd $dir &>/dev/null
umask 0000

chmod u+x elf

for case in `ls *.in`; do
  tag=${case/.in/}
  bash -c "ulimit -c 0 -t $cputime -v $virtmem -s $stkmem; ./elf <$case 1>$tag.run.out 2>$tag.run.err; echo \$? >$tag.run.st"
done


