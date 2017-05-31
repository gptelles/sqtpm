#!/bin/bash

# Execution dispatcher at localhost.
# This file is part of sqtpm.

uid=$1
assign=$2
cputime=$3
virtmem=$4
stkmem=$5

umask 0000

date=`/bin/date +%d%b%y-%H%M%S`
tmpd="$date-$$"
userd="_${uid}_tmp_"
mkdir $assign/$userd/$tmpd

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
  bash -c "ulimit -c 0 -t $cputime -v $virtmem -s $stkmem; ./elf <$case 1>$prefix.run.out 2>$prefix.run.err; echo \$? >$prefix.run.st"
done

\mv *.run.{out,err,st} ..

cd .. &>/dev/null
\rm -rf $tmpd
