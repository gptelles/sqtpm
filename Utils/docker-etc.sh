#!/bin/bash

# Container-side executor for docker.
# This file is part of sqtpm.

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

pid=$$
tpid=0  # Timer PID
cpid=0
timeout=$((cputime+3))


the_timeout () {
    trap - SIGALRM
    pkill -9 -P $cpid
    pkill -9 -P $tpid
    echo "152" >$tag.run.st
    exit 1
}


trap "the_timeout" SIGALRM


if [[ $lang  == "Python3" && $progname == "elf.tar" ]]; then
  tar -xf elf.tar
fi


(sleep $timeout; kill -SIGALRM $pid) &
tpid=$!


if [[ $lang  == "Python3" ]]; then 
  if [[ $progname == "elf.tar" ]]; then
    (ulimit -c 0 -t $cputime; python3 -B main.py <$input 1>$tag.run.out 2>$tag.run.err; echo $? >$tag.run.st) &
  else
    (ulimit -c 0 -t $cputime; python3 -B $progname <$input 1>$tag.run.out 2>$tag.run.err; echo $? >$tag.run.st) &
  fi      

elif [[ $lang  == "Octave" ]]; then  
  (ulimit -c 0 -t $cputime; octave-cli $progname <$input 1>$tag.run.out 2>$tag.run.err; echo $? >$tag.run.st) &

elif [[ $lang  == "Java" ]]; then 
  (ulimit -c 0 -t $cputime; java -jar $progname <$input 1>$tag.run.out 2>$tag.run.err; echo $? >$tag.run.st) &

else
  (ulimit -c 0 -t $cputime -v $virtmem -s $stkmem; ./elf <$input 1>$tag.run.out 2>$tag.run.err; echo $? >$tag.run.st) &
fi

cpid=$!

wait $cpid
trap - SIGALRM
pkill -9 -P $tpid

exit 0
