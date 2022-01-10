#!/bin/bash

# VM-side executor for VirtualBox with a shared directory.
# This file is part of sqtpm.

export PATH=/opt/jdk/bin:$PATH

sharedd=/mnt/aux

dir=$1
input=$2
lang=$3
progname=$4
cputime=$5
virtmem=$6
stkmem=$7

cd $sharedd/$dir &>/dev/null
umask 0000

tag=${input/.in/}

if [[ "$lang"  == "Python3" ]]; then 
  if [[ "$progname" == "elf.tar" ]]; then
    tar -xf $progname
    bash -c "ulimit -c 0 -t $cputime; python3 -B main.py <$input 1>$tag.run.out 2>$tag.run.err; echo \$? >$tag.run.st"
  else
    bash -c "ulimit -c 0 -t $cputime; python3 -B elf <$input 1>$tag.run.out 2>$tag.run.err; echo \$? >$tag.run.st"
  fi      

elif [[ "$lang"  == "Octave" ]]; then  
  bash -c "ulimit -c 0 -t $cputime; octave-cli $progname <$input 1>$tag.run.out 2>$tag.run.err; echo \$? >$tag.run.st"

elif [[ "$lang"  == "Java" ]]; then 
  bash -c "ulimit -c 0 -t $cputime; java -jar $progname <$input 1>$tag.run.out 2>$tag.run.err; echo \$? >$tag.run.st"

else
  bash -c "ulimit -c 0 -t $cputime -v $virtmem -s $stkmem; ./elf <$input 1>$tag.run.out 2>$tag.run.err; echo \$? >$tag.run.st"
fi
