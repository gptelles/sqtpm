#!/bin/bash

# Execution dispatcher for localhost.
# This file is part of sqtpm.



uid=$1
assign=$2
cputime=$3
virtmem=$4
stkmem=$5

umask 0000

date=`/bin/date +%d%b%y-%H%M%S`
tmpd="$date-$$"
mkdir $assign/$uid/$tmpd

cd $assign &>/dev/null
cases=(`ls *.in`)

\cp -p *.in $uid/$tmpd

if [[ -d extra-files ]]; then
  \cp -rp extra-files/* $uid/$tmpd
fi

cd $uid &>/dev/null

\cp -p elf $tmpd

cd $tmpd &>/dev/null

for case in ${cases[@]}; do
  prefix=${case%\.in}
  bash -c "ulimit -c 0 -t $cputime -v $virtmem -s $stkmem; ./elf <$case 1>$prefix.run.out 2>$prefix.run.err; echo \$? >$prefix.run.st"
done

\mv *.run.{out,err,st} ..

cd .. &>/dev/null
\rm -rf $tmpd
