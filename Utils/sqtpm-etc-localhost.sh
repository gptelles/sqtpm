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

A=("$@") 
L=("${A[@]:7}")
l=${#L[@]}

umask 0000
tmpd="/data/p2/$date-$$"
userd="_${uid}_tmp_"
date=`/bin/date +%d%b%y-%H%M%S`

mkdir $tmpd 
if [[ $? -ne 0 ]]; then
  echo "$date sqtpm-etc-localhost.sh mkdir $tmpd failed" &>>sqtpm-etc.log
  exit 129
fi

cd $assign 
cases=(`ls *.in`)

for case in ${cases[@]}; do
  tag=${case%\.in}

  thecputime=$cputime
  thevirtmem=$virtmem
  thestkmem=$stkmem
  
  for (( j=0; j<$l; j+=4 )); do
    if [[ $tag == ${L[$j]} ]]; then
      thecputime=${L[$j+1]}
      thevirtmem=${L[$j+2]}
      thestkmem=${L[$j+3]}
    fi
  done
  
  \cp -p $case $tmpd
  \cp -p $userd/$progname $tmpd
  
  if [[ -d extra-files ]]; then
    \cp -rp extra-files/* $tmpd 
  fi
  
  chmod -R o+rw $tmpd/*
  chmod -R og+rwx $tmpd/$progname
  
  if [[ $lang == "Python3" ]]; then
    if [[ $progname == "elf.tar" ]]; then
      bash -c "cd $tmpd; tar -xf elf.tar; ulimit -c 0 -t $thecputime; python3 -B main.py <$case 1>$tag.run.out 2>$tag.run.err; echo \$? >$tag.run.st"
    else
      bash -c "cd $tmpd; ulimit -c 0 -t $thecputime; python3 -B $progname <$case 1>$tag.run.out 2>$tag.run.err; echo \$? >$tag.run.st"
    fi      
      
  elif [[ $lang  == "Octave" ]]; then  
    bash -c "cd $tmpd; ulimit -c 0 -t $thecputime; octave-cli $progname <$case 1>$tag.run.out 2>$tag.run.err; echo \$? >$tag.run.st"
    
  elif [[ $lang == "Java" ]]; then 
    bash -c "cd $tmpd; ulimit -c 0 -t $thecputime; /opt/jdk/bin/java -jar $progname <$case 1>$tag.run.out 2>$tag.run.err; echo \$? >$tag.run.st"
    
  else
    chmod o+x $tmpd/elf
    bash -c "cd $tmpd; ulimit -c 0 -t $thecputime -v $thevirtmem -s $thestkmem; ./elf <$case 1>$tag.run.out 2>$tag.run.err; echo \$? >$tag.run.st"
  fi
  
  \cp $tmpd/*.run.{out,err,st} $userd 
  \rm -rf $tmpd/*
done

\rm -rf $tmpd
exit 0
