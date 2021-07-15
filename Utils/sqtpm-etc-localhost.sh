#!/bin/bash

# Execution dispatcher at localhost.
# This file is part of sqtpm.

uid=$1
assign=$2
lang=$3
cputime=$4
virtmem=$5
stkmem=$6

umask 0000

userd="_${uid}_tmp_"
date=`/bin/date +%d%b%y-%H%M%S`
tmpd="$date-$$"

mkdir $assign/$userd/$tmpd 
if [[ $? -ne 0 ]]; then
  echo "$date sqtpm-etc-localhost.sh mkdir $assign/$userd/$tmpd failed." >>sqtpm-etc.log
  exit 129
fi

cd $assign &>/dev/null
cases=(`ls *.in`)

\cp -p *.in $userd/$tmpd

if [[ -d extra-files ]]; then
  \cp -rp extra-files/* $userd/$tmpd 
fi

cd $userd &>/dev/null

\cp -p elf $tmpd

cd $tmpd &>/dev/null

for case in ${cases[@]}; do
  prefix=${case%\.in}

  if [[ "$lang" == "Python3" ]]; then 
    bash -c "ulimit -c 0 -t $cputime; python3 ./elf <$case 1>$prefix.run.out 2>$prefix.run.err; echo \$? >$prefix.run.st"
  elif [[ "$lang" == "Java" ]]; then 
    bash -c "ulimit -c 0 -t $cputime; java -jar ./elf <$case 1>$prefix.run.out 2>$prefix.run.err; echo \$? >$prefix.run.st"
  else
    bash -c "ulimit -c 0 -t $cputime -v $virtmem -s $stkmem; ./elf <$case 1>$prefix.run.out 2>$prefix.run.err; echo \$? >$prefix.run.st"
  fi
done

\mv *.run.{out,err,st} ..

cd .. &>/dev/null
\rm -rf $tmpd
