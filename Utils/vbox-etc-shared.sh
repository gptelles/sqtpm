#!/bin/bash

# VM-side test-case execution dispatcher for VirtualBox with shared directory.
# This file is part of sqtpm.

sharedd=/media/sf_aux

dir=$1
input=$2
cputime=$3
virtmem=$4
stkmem=$5

cd $sharedd/$dir &>/dev/null
umask 0000

tag=${input/.in/}
bash -c "ulimit -c 0 -t $cputime -v $virtmem -s $stkmem; ./elf <$input 1>$tag.run.out 2>$tag.run.err; echo \$? >$tag.run.st"
