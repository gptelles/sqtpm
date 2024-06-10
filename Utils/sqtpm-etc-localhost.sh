#!/bin/bash

# Execution dispatcher at localhost.
# This file is part of sqtpm.

sharedd='/fs/sqtpm'

uid=$1; shift
assign=$1; shift
lang=$1; shift
prog=$1; shift
cputime=$1; shift
virtmem=$1; shift
stkmem=$1; shift

# Put test-case specific arguments in L, if any:
L=("$@") 
l=${#L[@]}

umask 0000
date=`/bin/date +%d%b%y-%H%M%S`
userd="_${uid}_tmp_"
tmpd="$sharedd/$date-$$"

mkdir $tmpd 2>/dev/null
if [[ $? -ne 0 ]]; then
  echo "$date sqtpm-etc-localhost.sh mkdir $tmpd failed" &>>sqtpm-etc.log
  exit 129
fi


# Some globals:
gi=-1
pid=$$
cpid=0
tpid=0  # Timer PID
case=""
tag=""
timeout=$((cputime+3))

the_loop () {
  
  while (( gi < ${#cases[@]}-1 )); do

    ((gi++))
    
    case=${cases[$gi]}
    tag=${case%.in}

    ctime=$cputime
    vmem=$virtmem
    smem=$stkmem
    
    for (( j=0; j<$l; j+=4 )); do
      if [[ $tag == ${L[$j]} ]]; then
	ctime=${L[$j+1]}
	vmem=${L[$j+2]}
	smem=${L[$j+3]}
      fi
    done
    
    \cp -p $case $tmpd
    \cp -p $userd/$prog $tmpd
    
    if [[ -d extra-files ]]; then
      \cp -rp extra-files/* $tmpd 
    fi
    
    chmod -R o+rw $tmpd/*
    chmod -R og+rwx $tmpd/$prog

    (sleep $timeout; kill -SIGUSR1 $pid) &
    tpid=$!
    
    if [[ $lang == "Python3" ]]; then
      if [[ $prog == "elf.tar" ]]; then
	bash -c "cd $tmpd; tar -xf elf.tar; ulimit -c 0 -t $ctime; python3 -B main.py <$case 1>$tag.run.out 2>$tag.run.err; echo \$? >$tag.run.st"
      else
	bash -c "cd $tmpd; ulimit -c 0 -t $ctime; python3 -B $prog <$case 1>$tag.run.out 2>$tag.run.err; echo \$? >$tag.run.st"
      fi      
      
    elif [[ $lang  == "Octave" ]]; then  
      bash -c "cd $tmpd; ulimit -c 0 -t $ctime; octave-cli $prog <$case 1>$tag.run.out 2>$tag.run.err; echo \$? >$tag.run.st"
      
    elif [[ $lang == "Java" ]]; then 
      bash -c "cd $tmpd; ulimit -c 0 -t $ctime; /opt/jdk/bin/java -jar $prog <$case 1>$tag.run.out 2>$tag.run.err; echo \$? >$tag.run.st"
      
    else    
      chmod o+x $tmpd/elf
      (cd $tmpd; ulimit -c 0 -t $ctime -v $vmem -s $smem; ./elf <$case 1>$tag.run.out 2>$tag.run.err; echo $? >$tag.run.st) &
    fi

    cpid=$!
    wait $cpid
    kill -9 $tpid
    
    \cp $tmpd/*.run.{out,err,st} $userd 
    \rm -rf $tmpd/*
  done
}


the_timeout () {
  trap - SIGUSR1
  pkill -9 -P $cpid
  kill -9 $tpid
  echo "152" >$tmpd/$tag.run.st
  \cp $tmpd/*.run.{out,err,st} $userd 
  \rm -rf $tmpd/*
  the_loop
}


cd $assign
cases=(`ls *.in`)

trap "the_timeout" SIGUSR1
the_loop
trap - SIGUSR1

pkill -9 -P $$

exit 0
