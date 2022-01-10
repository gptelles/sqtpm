#!/bin/bash

# Execution dispatcher at localhost.
# This file is part of sqtpm.

uid=$1
assign=$2
lang=$3
progname=$4
cputime=$5
virtmem=$6
stkmem=$7

umask 0000

userd="_${uid}_tmp_"
date=`/bin/date +%d%b%y-%H%M%S`
tmpd="/mnt/aux/$date-$$"

mkdir $tmpd 
if [[ $? -ne 0 ]]; then
  echo "$date sqtpm-etc-localhost.sh mkdir $tmpd failed" 2>&1 >>sqtpm-etc.log
  echo "uid=$1 assign=$2 lang=$3 progname=$4 cputime=$5 virtmem=$6 stkmem=$7" 2>&1 >>sqtpm-etc.log
  exit 129
fi

cd $assign 
cases=(`ls *.in`)

for case in ${cases[@]}; do
  prefix=${case%\.in}

  \cp -p $case $tmpd
  \cp -p $userd/$progname $tmpd

  if [[ -d extra-files ]]; then
    \cp -rp extra-files/* $tmpd 
  fi

  chmod -R o+rw $tmpd/*
  
  if [[ "$lang" == "Python3" ]]; then
    if [[ "$progname" == "elf.tar" ]]; then
      sudo -u sqtpm -- bash -c "cd $tmpd; tar -xf $progname; ulimit -c 0 -t $cputime; python3 -B main.py <$case 1>$prefix.run.out 2>$prefix.run.err; echo \$? >$prefix.run.st"
    else
      sudo -u sqtpm -- bash -c "cd $tmpd; ulimit -c 0 -t $cputime; python3 -B $progname <$case 1>$prefix.run.out 2>$prefix.run.err; echo \$? >$prefix.run.st"
    fi      
      
  elif [[ "$lang"  == "Octave" ]]; then  
    sudo -u sqtpm -- bash -c "cd $tmpd; ulimit -c 0 -t $cputime; octave-cli $progname <$case 1>$prefix.run.out 2>$prefix.run.err; echo \$? >$prefix.run.st"
    
  elif [[ "$lang" == "Java" ]]; then 
    sudo -u sqtpm -- bash -c "cd $tmpd; ulimit -c 0 -t $cputime; /opt/jdk/bin/java -jar $progname <$case 1>$prefix.run.out 2>$prefix.run.err; echo \$? >$prefix.run.st"
    
  else
    chmod  o+x $tmpd/elf
    sudo -u sqtpm -- bash -c "cd $tmpd; ulimit -c 0 -t $cputime -v $virtmem -s $stkmem; ./elf <$case 1>$prefix.run.out 2>$prefix.run.err; echo \$? >$prefix.run.st"
  fi

  chown www-data:www-data $tmpd/*.run.{out,err,st}
  
  \cp $tmpd/*.run.{out,err,st} $userd 
  \rm $tmpd/*.run.{out,err,st} $tmpd/$case
done

cd .. 
\rm -rf $tmpd
